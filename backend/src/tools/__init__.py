"""
Tools Layer — 에이전트가 사용할 수 있는 도구 모음

도구 카테고리:
  1. KG Tools (lightrag_tools): Knowledge Graph 내용 검색
  2. Utility Tools (utility_tools): 파일 목록, 메타정보, 시스템 상태 조회
"""

from typing import Dict, Any, List

from .lightrag_tools import get_tools_for_graph, get_tools_map
from .utility_tools import get_utility_tools_descriptions, get_utility_tools_map


def get_all_tools_descriptions() -> List[Dict[str, Any]]:
    """모든 도구의 설명 목록 반환 (Actor 프롬프트에 주입)"""
    return get_tools_for_graph() + get_utility_tools_descriptions()


def get_all_tools_map() -> Dict[str, Any]:
    """모든 도구의 함수 매핑 반환 (Tool Executor에서 사용)"""
    combined = get_tools_map()
    combined.update(get_utility_tools_map())
    return combined


__all__ = [
    "get_tools_for_graph",
    "get_tools_map",
    "get_utility_tools_descriptions",
    "get_utility_tools_map",
    "get_all_tools_descriptions",
    "get_all_tools_map",
]
