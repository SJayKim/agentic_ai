"""
Agent State - LangGraph 상태 정의

ReAct + Reflexion 에이전트의 상태를 정의.
LangGraph StateGraph에서 사용.
"""

from typing import Annotated, Any, Dict, List, Optional, TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """
    에이전트 상태 정의
    
    LangGraph의 StateGraph에서 노드 간 전달되는 상태.
    Reflexion 알고리즘의 모든 컴포넌트가 참조.
    """
    # 메시지 히스토리 (LangGraph 자동 누적)
    messages: Annotated[List[BaseMessage], add_messages]
    
    # 사용자 요청
    user_query: str
    
    # 실행 추적
    current_step: int
    max_steps: int
    
    # Actor 출력
    thought: Optional[str]
    action: Optional[str]
    action_input: Optional[Dict[str, Any]]
    
    # Tool 실행 결과
    observation: Optional[str]
    
    # Evaluator 출력
    evaluation_status: Optional[str]  # "PASS" | "FAIL"
    evaluation_reason: Optional[str]
    evaluation_type: Optional[str]  # "technical" | "logical"
    
    # Self-Reflection 출력
    lesson: Optional[str]
    reflection_analysis: Optional[str]
    reflection_suggestion: Optional[str]  # 다음 시도 전략
    
    # 최종 답변
    final_answer: Optional[str]
    
    # 장기 기억 (LessonsStore에서 로드)
    lessons: List[str]
    
    # 연속 실패 카운트 (Early Stopping)
    consecutive_failures: int
    
    # 세션 메타데이터
    session_id: Optional[str]
    created_tasks: List[str]
    created_docs: List[str]
    
    # Router 출력
    intent: Optional[str]
    
    # 참고 자료 (출처 추적)
    # 각 항목: {"type": "document"|"web"|"llm", "title": str, "url": str (optional), "tool": str}
    sources: Annotated[List[Dict[str, Any]], lambda a, b: a + b]

def create_initial_state(
    user_query: str,
    lessons: List[str] = None,
    max_steps: int = 5,
    session_id: str = None
) -> AgentState:
    """초기 상태 생성"""
    return AgentState(
        messages=[],
        user_query=user_query,
        current_step=0,
        max_steps=max_steps,
        thought=None,
        action=None,
        action_input=None,
        observation=None,
        evaluation_status=None,
        evaluation_reason=None,
        evaluation_type=None,
        lesson=None,
        reflection_analysis=None,
        reflection_suggestion=None,
        final_answer=None,
        lessons=lessons or [],
        consecutive_failures=0,
        session_id=session_id,
        created_tasks=[],
        created_docs=[],
        intent=None,
        sources=[],
    )
