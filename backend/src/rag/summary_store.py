"""
Document Summary Store — 문서별 구조화 요약 영구 캐시

인제스트 파이프라인에서 생성된 구조화 요약을 JSON 파일로 저장합니다.
에이전트가 KG 쿼리 없이 밀리초 단위로 문서 요약을 조회할 수 있습니다.

저장 위치: data/rag_storage/document_summaries.json
구조:
  {
    "파일명": {
      "filename": str,
      "summary": str,          # 구조화 요약 전문
      "doc_type": str,         # 문서 유형
      "key_topic": str,        # 핵심 주제 (1~2문장)
      "original_chars": int,
      "summary_chars": int,
      "indexed_at": str        # 인덱싱 시각 (ISO 형식)
    },
    ...
  }
"""

import json
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List


_STORE_PATH = Path(__file__).parent.parent.parent / "data" / "rag_storage" / "document_summaries.json"


def _load_store() -> Dict[str, Any]:
    """저장소 파일을 로드합니다."""
    if _STORE_PATH.exists():
        with open(_STORE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_store(store: Dict[str, Any]) -> None:
    """저장소 파일을 저장합니다."""
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_STORE_PATH, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)


def _extract_metadata(summary_text: str) -> Dict[str, str]:
    """구조화 요약에서 문서 유형, 핵심 주제 등 메타데이터를 추출합니다."""
    metadata = {
        "doc_type": "",
        "key_topic": "",
    }

    # '문서 유형:' 패턴 추출
    doc_type_match = re.search(r'문서\s*유형[:\s]*(.+)', summary_text)
    if doc_type_match:
        metadata["doc_type"] = doc_type_match.group(1).strip().rstrip('.')

    # '핵심 주제:' 패턴 추출
    topic_match = re.search(r'핵심\s*주제[:\s]*(.+?)(?:\n|$)', summary_text)
    if topic_match:
        metadata["key_topic"] = topic_match.group(1).strip().rstrip('.')

    return metadata


def save_summary(filename: str, summary: str, original_chars: int, summary_chars: int) -> None:
    """
    단일 문서 요약을 저장합니다.

    Args:
        filename: 원본 파일명
        summary: 구조화 요약 전문 (document_summarizer 출력)
        original_chars: 원본 텍스트 글자 수
        summary_chars: 요약 텍스트 글자 수
    """
    store = _load_store()

    metadata = _extract_metadata(summary)

    store[filename] = {
        "filename": filename,
        "summary": summary,
        "doc_type": metadata["doc_type"],
        "key_topic": metadata["key_topic"],
        "original_chars": original_chars,
        "summary_chars": summary_chars,
        "indexed_at": datetime.now().isoformat(),
    }

    _save_store(store)
    print(f"[SUMMARY STORE] 💾 Saved summary for '{filename}'")


def save_summaries_batch(summaries: list) -> int:
    """
    여러 문서 요약을 일괄 저장합니다.

    Args:
        summaries: StructuredSummary 리스트 (document_summarizer 출력)

    Returns:
        저장된 문서 수
    """
    store = _load_store()
    saved_count = 0

    for s in summaries:
        if s.error or not s.summary.strip():
            continue

        metadata = _extract_metadata(s.summary)

        store[s.filename] = {
            "filename": s.filename,
            "summary": s.summary,
            "doc_type": metadata["doc_type"],
            "key_topic": metadata["key_topic"],
            "original_chars": s.original_chars,
            "summary_chars": s.summary_chars,
            "indexed_at": datetime.now().isoformat(),
        }
        saved_count += 1

    _save_store(store)
    print(f"[SUMMARY STORE] 💾 Batch saved {saved_count} summaries")
    return saved_count


def get_summary(filename: str) -> Optional[Dict[str, Any]]:
    """
    특정 문서의 요약을 조회합니다.
    정확한 파일명 매칭 후, 실패 시 부분 매칭을 시도합니다.
    """
    store = _load_store()

    # 정확한 매칭
    if filename in store:
        return store[filename]

    # 부분 매칭 (대소문자 무시)
    filename_lower = filename.lower()
    matches = {k: v for k, v in store.items() if filename_lower in k.lower()}

    if len(matches) == 1:
        return list(matches.values())[0]
    elif len(matches) > 1:
        return {
            "error": "multiple_matches",
            "matches": list(matches.keys()),
        }

    return None


def get_all_summaries_brief() -> List[Dict[str, str]]:
    """
    모든 문서의 간략 요약 목록을 반환합니다 (전체 요약 텍스트 제외).
    """
    store = _load_store()

    return [
        {
            "filename": v["filename"],
            "doc_type": v.get("doc_type", ""),
            "key_topic": v.get("key_topic", ""),
            "indexed_at": v.get("indexed_at", ""),
        }
        for v in store.values()
    ]


def remove_summary(filename: str) -> bool:
    """특정 문서의 요약을 삭제합니다."""
    store = _load_store()
    if filename in store:
        del store[filename]
        _save_store(store)
        return True
    return False


def clear_all_summaries() -> int:
    """모든 요약을 삭제합니다."""
    store = _load_store()
    count = len(store)
    _save_store({})
    return count
