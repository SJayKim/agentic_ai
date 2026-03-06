"""
LightRAG Manager — Knowledge Graph 엔진 초기화, 문서 인제스트, 쿼리

하이브리드 인제스트 파이프라인:
  원본 문서 → document_converter (텍스트 추출)
           → document_summarizer (LLM 구조화 요약 — 노이즈 제거)
           → LightRAG (엔티티/관계 자동 추출)

개선 사항:
  - LLM 구조화 요약으로 OCR 노이즈, URL, 보일러플레이트 자동 제거
  - 요약에 핵심 엔티티/관계가 명시적으로 포함되어 KG 품질 향상
  - 파일명 메타데이터 헤더로 문서 추적 가능
"""

import os
import numpy as np
import asyncio
from lightrag import LightRAG, QueryParam
from lightrag.utils import EmbeddingFunc
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.messages import HumanMessage, SystemMessage

from src.rag.document_converter import convert_all_documents, convert_document, SUPPORTED_EXTENSIONS
from src.rag.document_summarizer import summarize_documents, summarize_document
from src.rag.summary_store import save_summary, save_summaries_batch

WORKING_DIR = os.getenv("RAG_DIR", "./data/rag_storage")
if not os.path.exists(WORKING_DIR):
    os.makedirs(WORKING_DIR)

# ═══════════════════════════════════════════════════════
#  커스텀 엔티티 타입 — 다양한 문서 유형에 대응
# ═══════════════════════════════════════════════════════
CUSTOM_ENTITY_TYPES = [
    # 기본 엔티티 (LightRAG 기본 + 확장)
    "Person",           # 사람, 저자, 연구원
    "Organization",     # 회사, 팀, 부서, 기관
    "Location",         # 장소, 국가, 도시
    "Event",            # 이벤트, 회의, 릴리즈
    "Concept",          # 추상 개념, 이론, 원리

    # 기술 & 소프트웨어 (기술 스택, 개발 계획 문서용)
    "Technology",       # 프로그래밍 언어, 프레임워크, 라이브러리, 플랫폼
    "Software",         # 소프트웨어 제품, 서비스, 애플리케이션
    "System",           # 시스템, 아키텍처, 인프라

    # 프로젝트 & 업무 (개발 계획, 업무 문서용)
    "Project",          # 프로젝트명, 과제, 태스크
    "Team",             # 팀, 부서, 파트, 그룹
    "Skill",            # 기술 역량, 자격증, 레벨

    # 측정 & 데이터 (BLEU Score, 성능 지표 등)
    "Metric",           # 평가 지표, 점수, KPI
    "Dataset",          # 데이터셋, 코퍼스, 훈련 데이터

    # 금융 & 거래 (영수증, 결제 문서용)
    "Product",          # 상품, 서비스, 구독 플랜
    "Transaction",      # 결제, 거래, 구독

    # 문서 메타 (파일 추적용)
    "Document",         # 문서 자체 (파일명이 엔티티로 추출됨)

    # 기타
    "Method",           # 방법론, 알고리즘, 프로세스
    "Data",             # 데이터 포인트, 수치
    "Artifact",         # 산출물, 결과물
]

# ═══════════════════════════════════════════════════════
#  LLM & Embedding 함수
# ═══════════════════════════════════════════════════════

import concurrent.futures
_llm_executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)

async def gemini_llm_func(prompt: str, system_prompt: str = None, **kwargs) -> str:
    """
    LightRAG용 Gemini LLM 함수.
    
    전용 스레드 풀(_llm_executor)에서 동기 호출하여
    이벤트 루프 블로킹을 방지.
    """
    def _sync_call(p: str, sp: str):
        llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.1)
        messages = []
        if sp:
            messages.append(SystemMessage(content=sp))
        messages.append(HumanMessage(content=p))
        print(f"[GEMINI-RAG] Calling Gemini ({len(p)} chars)...")
        try:
            res = llm.invoke(messages).content
            print(f"[GEMINI-RAG] Response received ({len(res)} chars)")
            return res
        except Exception as e:
            print(f"[GEMINI-RAG] LLM invoke failed: {e}")
            return f"LLM Error: {str(e)}"
        
    try:
        loop = asyncio.get_running_loop()
        response_content = await loop.run_in_executor(_llm_executor, _sync_call, prompt, system_prompt)
        return response_content
    except Exception as e:
        print(f"[GEMINI-RAG] Executor error: {e}")
        return f"LLM Error: {str(e)}"

hf_embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

async def local_embedding_func(texts: list[str]) -> np.ndarray:
    embeddings = await hf_embeddings.aembed_documents(texts)
    return np.array(embeddings)

# ═══════════════════════════════════════════════════════
#  LightRAG 인스턴스 초기화 (커스텀 entity_types 적용)
# ═══════════════════════════════════════════════════════

rag = LightRAG(
    working_dir=WORKING_DIR,
    llm_model_func=gemini_llm_func,
    embedding_func=EmbeddingFunc(
        embedding_dim=384,
        max_token_size=256,
        func=local_embedding_func
    ),
    addon_params={"entity_types": CUSTOM_ENTITY_TYPES},
    # 청킹 설정 — 큰 문서(xlsx 62K chars 등)에 대응
    chunk_token_size=1200,
    chunk_overlap_token_size=100,
    entity_extract_max_gleaning=2,  # 2회 반복 추출로 엔티티 누락 최소화
)

# ═══════════════════════════════════════════════════════
#  문서 인제스트 (하이브리드: converter → summarizer → LightRAG)
# ═══════════════════════════════════════════════════════

async def ingest_documents(docs_dir: str = "./data/documents") -> dict:
    """
    docs_dir 내 모든 지원 문서를 변환 → 구조화 요약 → LightRAG 인제스트.
    
    파이프라인:
      1. document_converter: 원본 파일 → 텍스트 추출
      2. document_summarizer: LLM 구조화 요약 (노이즈 제거 + 엔티티/관계 명시)
      3. LightRAG ainsert: 요약 텍스트 → KG 엔티티/관계 자동 추출
    """
    if not os.path.exists(docs_dir):
        os.makedirs(docs_dir)
        return {"status": "success", "message": "Directory created, but no documents found."}
    
    # Step 1: 문서 변환
    converted = convert_all_documents(os.path.abspath(docs_dir))
    
    if not converted:
        return {"status": "success", "message": "No supported documents found."}
    
    success_docs = [d for d in converted if not d.error and d.content.strip()]
    failed_docs = [d for d in converted if d.error]
    
    if failed_docs:
        for d in failed_docs:
            print(f"[INGEST] ⚠ Convert skipped {d.filename}: {d.error}")
    
    if not success_docs:
        return {
            "status": "error", 
            "message": f"All {len(converted)} documents failed to convert.",
            "errors": [{"file": d.filename, "error": d.error} for d in failed_docs]
        }
    
    # Step 2: LLM 구조화 요약
    print(f"[INGEST] Step 1/2: {len(success_docs)}개 문서 변환 완료, 구조화 요약 시작...")
    summaries = await summarize_documents(success_docs)
    
    success_summaries = [s for s in summaries if not s.error and s.summary.strip()]
    failed_summaries = [s for s in summaries if s.error]
    
    if failed_summaries:
        for s in failed_summaries:
            print(f"[INGEST] ⚠ Summary skipped {s.filename}: {s.error}")
    
    if not success_summaries:
        return {
            "status": "error",
            "message": "All documents failed to summarize.",
            "errors": [{"file": s.filename, "error": s.error} for s in failed_summaries]
        }
    
    # Step 2.5: 요약 영구 캐시 저장
    save_summaries_batch(success_summaries)
    
    # Step 3: LightRAG 인제스트 (요약 텍스트)
    contents = [s.summary for s in success_summaries]
    
    print(f"[INGEST] Step 2/2: {len(contents)}개 구조화 요약 → KG 인제스트...")
    for s in success_summaries:
        print(f"  📄 {s.filename} (원본 {s.original_chars:,} → 요약 {s.summary_chars:,} chars)")
    
    await rag.initialize_storages()
    await rag.ainsert(contents)
    
    result = {
        "status": "success",
        "message": f"Successfully ingested {len(success_summaries)} documents (via structured summary).",
        "documents": [
            {
                "filename": s.filename,
                "original_chars": s.original_chars,
                "summary_chars": s.summary_chars,
                "compression": f"{s.summary_chars / s.original_chars * 100:.0f}%" if s.original_chars > 0 else "N/A",
            }
            for s in success_summaries
        ],
    }
    
    all_failures = (
        [{"file": d.filename, "stage": "convert", "error": d.error} for d in failed_docs] +
        [{"file": s.filename, "stage": "summarize", "error": s.error} for s in failed_summaries]
    )
    if all_failures:
        result["warnings"] = all_failures
    
    return result


async def ingest_single_document(file_path: str) -> dict:
    """
    단일 문서를 변환 → 구조화 요약 → KG 인제스트.
    /api/upload에서 사용.
    """
    # Step 1: 변환
    doc = convert_document(os.path.abspath(file_path))
    
    if doc.error:
        return {"status": "error", "message": f"Convert failed: {doc.filename}: {doc.error}"}
    
    if not doc.content.strip():
        return {"status": "error", "message": f"No text extracted from {doc.filename}"}
    
    # Step 2: 구조화 요약
    summary = await summarize_document(doc.filename, doc.content)
    
    if summary.error:
        return {"status": "error", "message": f"Summary failed: {doc.filename}: {summary.error}"}
    
    if not summary.summary.strip():
        return {"status": "error", "message": f"Empty summary for {doc.filename}"}
    
    # Step 2.5: 요약 영구 캐시 저장
    save_summary(summary.filename, summary.summary, summary.original_chars, summary.summary_chars)
    
    # Step 3: KG 인제스트
    print(f"[INGEST] Single doc: {doc.filename} (원본 {summary.original_chars:,} → 요약 {summary.summary_chars:,} chars)")
    
    await rag.initialize_storages()
    await rag.ainsert([summary.summary])
    
    return {
        "status": "success",
        "message": f"Successfully ingested {doc.filename}",
        "document": {
            "filename": doc.filename,
            "original_chars": summary.original_chars,
            "summary_chars": summary.summary_chars,
        }
    }


async def query_knowledge_graph(query: str, mode: str = "hybrid") -> str:
    """Queries the LightRAG knowledge graph."""
    if mode not in ["naive", "local", "global", "hybrid"]:
        mode = "hybrid"
    return await rag.aquery(query, param=QueryParam(mode=mode))

