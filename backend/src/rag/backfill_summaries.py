"""
기존 인덱싱된 문서들의 요약을 일괄 생성/캐싱하는 스크립트.

이미 KG에 인제스트된 문서들에 대해 요약 캐시가 없는 경우
document_converter + document_summarizer를 실행하여 summary_store에 저장합니다.

사용법:
    cd backend
    python -m src.rag.backfill_summaries
"""

import asyncio
import os
import sys

# backend 디렉토리를 기준으로 임포트 경로 설정
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env"))

from src.rag.document_converter import convert_all_documents
from src.rag.document_summarizer import summarize_documents
from src.rag.summary_store import save_summaries_batch, _load_store


DOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "documents")


async def backfill():
    """기존 문서의 요약을 일괄 생성합니다."""
    # 현재 캐시 상태 확인
    existing_store = _load_store()
    print(f"[BACKFILL] 현재 캐시된 요약: {len(existing_store)}개")
    if existing_store:
        for fname in existing_store:
            print(f"  ✅ {fname}")

    # 문서 변환
    print(f"\n[BACKFILL] 문서 폴더: {DOCS_DIR}")
    converted = convert_all_documents(os.path.abspath(DOCS_DIR))

    if not converted:
        print("[BACKFILL] 변환할 문서가 없습니다.")
        return

    # 이미 캐시된 문서 제외
    need_summary = [d for d in converted if not d.error and d.content.strip() and d.filename not in existing_store]

    if not need_summary:
        print(f"[BACKFILL] 모든 문서({len(existing_store)}개)가 이미 캐시되어 있습니다.")
        return

    print(f"[BACKFILL] 요약 생성 대상: {len(need_summary)}개")
    for d in need_summary:
        print(f"  📄 {d.filename} ({len(d.content):,} chars)")

    # LLM 구조화 요약
    summaries = await summarize_documents(need_summary)

    # 캐시 저장
    saved = save_summaries_batch(summaries)
    print(f"\n[BACKFILL] 완료: {saved}개 요약 저장됨")

    # 최종 상태
    final_store = _load_store()
    print(f"[BACKFILL] 총 캐시된 요약: {len(final_store)}개")
    for fname in final_store:
        print(f"  ✅ {fname}")


if __name__ == "__main__":
    asyncio.run(backfill())
