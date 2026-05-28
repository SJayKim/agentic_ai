"""
Document Summarizer — LLM 기반 구조화 요약기

인제스트 파이프라인:
  원본 문서 → document_converter (텍스트 추출)
           → document_summarizer (구조화 요약)  ← 이 모듈
           → LightRAG (엔티티/관계 추출)

목적:
  - OCR 노이즈, URL, 보일러플레이트 등 불필요한 텍스트 제거
  - 문서별 핵심 엔티티/관계를 명시적으로 구조화
  - LightRAG가 깨끗한 입력으로 고품질 KG를 구축하도록 지원
"""

import concurrent.futures
from dataclasses import dataclass
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage

from src.llm.provider import get_node_llm

# 요약 전용 스레드 풀 (동기 LLM 호출용)
_summarizer_executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)

# settings.yaml `llm.summarizer` 기반으로 1회 생성 — 매 호출 인스턴스화 비용 제거.
_summarizer_llm = get_node_llm("summarizer")

STRUCTURED_SUMMARY_SYSTEM_PROMPT = """\
당신은 Knowledge Graph 구축을 위한 문서 분석 전문가입니다.

주어진 문서를 분석하여 아래 형식으로 **구조화된 요약**을 생성하세요.
이 요약은 Knowledge Graph의 노드(엔티티)와 엣지(관계) 추출에 직접 사용됩니다.

═══ 출력 형식 ═══

## 문서 개요
- 문서명: (파일명)
- 문서 유형: (영수증/개발계획/기술문서/연구결과/기사/프레젠테이션 등)
- 작성 일자: (알 수 있으면)
- 핵심 주제: (1~2문장)

## 핵심 엔티티
각 엔티티를 아래 형식으로 나열하세요:
- [엔티티명] (타입: Person/Organization/Technology/Project/Product/Metric/Document 등): 설명

## 핵심 관계
엔티티 간 관계를 아래 형식으로 나열하세요:
- [엔티티A] → (관계) → [엔티티B]: 설명

## 주요 내용 요약
문서의 핵심 내용을 3~10개 항목으로 정리하세요.

═══ 규칙 ═══
1. URL, 연락처, 문의처 안내 등 보일러플레이트 텍스트는 무시하세요.
2. OCR 깨진 글자, 의미 없는 기호, 페이지 번호 등은 무시하세요.
3. 외국어(일본어 등)가 섞인 경우, 핵심 의미만 한국어로 정리하세요.
4. 엔티티명은 일관되게 작성하세요 (같은 대상에 여러 이름 쓰지 않기).
5. 문서에 실제로 있는 정보만 추출하세요. 추론이나 외부 지식을 추가하지 마세요.
6. 금액, 날짜, 수치 등 정량적 데이터는 반드시 포함하세요.
"""


@dataclass
class StructuredSummary:
    """구조화 요약 결과."""
    filename: str
    original_chars: int
    summary: str
    summary_chars: int
    error: Optional[str] = None


def _call_llm_sync(document_text: str) -> str:
    """요약용 LLM 동기 호출 (스레드 내 실행용)."""
    messages = [
        SystemMessage(content=STRUCTURED_SUMMARY_SYSTEM_PROMPT),
        HumanMessage(content=f"다음 문서를 분석하여 구조화된 요약을 생성하세요:\n\n{document_text}"),
    ]
    return _summarizer_llm.invoke(messages).content


def summarize_document_sync(filename: str, content: str) -> StructuredSummary:
    """
    단일 문서를 구조화 요약 (동기 버전).
    
    Args:
        filename: 원본 파일명
        content: document_converter에서 추출된 텍스트 (메타데이터 헤더 포함)
    
    Returns:
        StructuredSummary 결과
    """
    if not content.strip():
        return StructuredSummary(
            filename=filename,
            original_chars=0,
            summary="",
            summary_chars=0,
            error="Empty content"
        )

    try:
        print(f"[SUMMARIZER] 📝 Summarizing {filename} ({len(content):,} chars)...", flush=True)
        summary = _call_llm_sync(content)
        print(f"[SUMMARIZER] ✅ {filename}: {len(content):,} → {len(summary):,} chars", flush=True)

        # 요약 결과에 문서 메타데이터 헤더 추가 (LightRAG가 파일명을 엔티티로 추출할 수 있도록)
        structured_output = f"[Document: {filename}]\n\n{summary}"

        return StructuredSummary(
            filename=filename,
            original_chars=len(content),
            summary=structured_output,
            summary_chars=len(structured_output),
        )
    except Exception as e:
        print(f"[SUMMARIZER] ❌ {filename}: {e}", flush=True)
        return StructuredSummary(
            filename=filename,
            original_chars=len(content),
            summary="",
            summary_chars=0,
            error=str(e)
        )


async def summarize_document(filename: str, content: str) -> StructuredSummary:
    """
    단일 문서를 구조화 요약 (비동기 래퍼).
    ThreadPoolExecutor에서 동기 LLM 호출을 실행.
    """
    import asyncio
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _summarizer_executor,
        summarize_document_sync,
        filename,
        content,
    )


async def summarize_documents(docs: list) -> list[StructuredSummary]:
    """
    여러 문서를 병렬 구조화 요약.
    
    Args:
        docs: ConvertedDocument 리스트 (document_converter 출력)
    
    Returns:
        StructuredSummary 리스트
    """
    import asyncio

    tasks = [
        summarize_document(doc.filename, doc.content)
        for doc in docs
        if not doc.error and doc.content.strip()
    ]

    if not tasks:
        return []

    print(f"[SUMMARIZER] 🔄 {len(tasks)}개 문서 구조화 요약 시작...", flush=True)
    results = await asyncio.gather(*tasks)
    
    success = [r for r in results if not r.error]
    failed = [r for r in results if r.error]
    
    print(f"[SUMMARIZER] 완료: {len(success)} 성공, {len(failed)} 실패", flush=True)
    
    return list(results)
