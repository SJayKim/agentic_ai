"""
LightRAG Tools - Knowledge Graph 검색 도구

핵심 설계:
  LightRAG 쿼리를 **전용 백그라운드 스레드의 영구 이벤트 루프**에서 실행하여
  FastAPI/LangGraph의 메인 이벤트 루프와 완전 격리.
  
  중요: LightRAG 내부 워커(asyncio.Queue 등)가 최초 이벤트 루프에 바인딩되므로,
  매번 새 루프를 만들고 닫으면 두 번째 쿼리부터 'Event loop is closed' 에러 발생.
  → 영구 루프 1개를 유지하여 해결.
"""

import asyncio
import threading
from typing import Dict, Any, List

# 전체 쿼리 타임아웃 (초)
_QUERY_TIMEOUT = 120

# ── 영구 백그라운드 이벤트 루프 (LightRAG 전용) ──
_rag_loop: asyncio.AbstractEventLoop = None
_rag_thread: threading.Thread = None


def _get_rag_loop() -> asyncio.AbstractEventLoop:
    """LightRAG 전용 영구 이벤트 루프를 반환 (lazy init)."""
    global _rag_loop, _rag_thread
    if _rag_loop is not None and _rag_loop.is_running():
        return _rag_loop

    _rag_loop = asyncio.new_event_loop()

    def _run_loop(loop: asyncio.AbstractEventLoop):
        asyncio.set_event_loop(loop)
        loop.run_forever()

    _rag_thread = threading.Thread(
        target=_run_loop,
        args=(_rag_loop,),
        daemon=True,
        name="rag-event-loop",
    )
    _rag_thread.start()
    return _rag_loop


def get_tools_for_graph() -> List[Dict[str, Any]]:
    return [
        {
            "name": "query_knowledge_graph",
            "description": (
                "Knowledge Graph(지식 그래프)에서 문서의 내용을 의미 기반으로 검색합니다. "
                "인덱싱된 문서들의 텍스트 내용, 엔티티, 관계를 분석하여 질문에 대한 답변을 생성합니다. "
                "사용 시점: 문서 내용에 대한 질문, 요약 요청, 특정 정보 검색, 엔티티 간 관계 파악 시. "
                "예시: '영수증 내용 알려줘', '개발계획 요약해줘', '플랜티넷의 기술 로드맵은?'. "
                "검색 모드 가이드: "
                "hybrid(기본값, 권장) = 키워드+의미 검색 결합, "
                "local = 특정 엔티티 주변 관계 탐색, "
                "global = 문서 전체 주제/요약 파악, "
                "naive = 단순 벡터 유사도 검색. "
                "주의: 파일 목록/크기/개수 등 메타정보는 list_documents나 get_document_info를 사용하세요."
            ),
            "args": {
                "query": {
                    "type": "string",
                    "description": "검색할 질문 또는 키워드. 구체적이고 명확한 질문일수록 좋은 결과를 반환합니다.",
                },
                "mode": {
                    "type": "string",
                    "description": "검색 모드: 'hybrid'(기본값, 권장), 'local'(엔티티 중심), 'global'(전체 요약), 'naive'(단순 검색)",
                },
            },
        }
    ]


def get_tools_map() -> Dict[str, Any]:
    from src.rag.lightrag_manager import rag
    from lightrag import QueryParam

    async def query_wrapper(query: str, mode: str = "hybrid") -> str:
        """
        Knowledge Graph 검색 (영구 루프 격리 버전).

        Flow:
          메인 루프 (FastAPI)
            └── run_coroutine_threadsafe ──▶ 영구 백그라운드 루프 (rag-event-loop 스레드)
                                                └── rag.aquery()
                                                     └── gemini_llm_func (run_in_executor → _llm_executor)
        
        LightRAG 내부 워커가 한 번 초기화되면 같은 루프에서 계속 동작하므로
        'Event loop is closed' 에러가 발생하지 않음.
        """
        if mode not in ["naive", "local", "global", "hybrid"]:
            mode = "hybrid"

        try:
            loop = _get_rag_loop()
            print(f"[RAG-QUERY] Submitting query to dedicated loop: '{query[:100]}...' (mode={mode})")

            future = asyncio.run_coroutine_threadsafe(
                rag.aquery(query, param=QueryParam(mode=mode)),
                loop,
            )

            # 타임아웃 적용하여 결과 대기 (블로킹 방지를 위해 executor 사용)
            main_loop = asyncio.get_running_loop()
            result = await main_loop.run_in_executor(
                None,  # default executor
                lambda: future.result(timeout=_QUERY_TIMEOUT),
            )

            print(f"[RAG-QUERY] Query completed ({len(result) if result else 0} chars)")
            return result if result else "No results found in Knowledge Graph."

        except TimeoutError:
            print(f"[RAG-QUERY] Query timed out after {_QUERY_TIMEOUT}s")
            return f"Error: Knowledge Graph query timed out after {_QUERY_TIMEOUT} seconds."
        except Exception as e:
            import traceback
            print(f"[RAG-QUERY] Query error: {e}")
            traceback.print_exc()
            return f"Error querying Knowledge Graph: {str(e)}"

    return {"query_knowledge_graph": query_wrapper}
