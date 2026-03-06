"""
LangGraph Graph Definition - 에이전트 워크플로우 정의

ReAct + Reflexion 패턴을 LangGraph StateGraph로 구현.
각 노드(router, actor, evaluator, reflection)는 독립된 LLM 인스턴스를 사용하여
context 오염을 방지합니다.
"""

from typing import Dict, Any, List, Callable, Optional, Literal

from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver

from src.agent.state import AgentState, create_initial_state
from src.agent.nodes import (
    actor_node,
    evaluator_node,
    reflection_node,
    tool_executor_node,
)
from src.agent.router import router_node, direct_answer_node
from src.llm.provider import get_llm, get_node_llm
from src.config.config_loader import config


class ReflexionGraph:
    """
    LangGraph 기반 Reflexion 에이전트 그래프
    
    각 노드는 독립된 LLM 인스턴스를 사용합니다:
    - router:        gemini-2.5-flash (빠른 분류)
    - actor:         gemini-3-flash-preview (고성능 추론)
    - evaluator:     gemini-3-flash-preview (정확한 판단)
    - reflection:    gemini-3-flash-preview (심층 분석)
    - direct_answer: gemini-2.5-flash (일반 대화)
    
    Flow:
    START → router → (rag_query?) → actor → (has action?) → tool_executor → evaluator →
            ↓            ↑                                            ↓
      (general_chat?)    ↑← reflection ←(FAIL)←─────────────────────←┘
            ↓            ↑                                            ↓
        direct_answer    └───────────← (continue?) ←────────────────←(PASS)
            ↓                                ↓
           END                              END (final_answer)
    """
    
    def __init__(
        self,
        tools: List[Dict[str, Any]] = None,
        tools_map: Dict[str, Callable] = None,
        llm: Optional[Any] = None,
        lessons_store: Optional[Any] = None,
        checkpointer: Optional[Any] = None,
    ):
        """
        Args:
            tools: 도구 설명 리스트 [{"name": ..., "description": ..., "args": ...}]
            tools_map: 실제 도구 함수 매핑 {"tool_name": callable}
            llm: LangChain ChatModel (None이면 노드별 독립 LLM 자동 생성)
            lessons_store: LessonsStore 인스턴스 (장기 기억)
            checkpointer: LangGraph 체크포인터 (None이면 MemorySaver 사용)
        """
        self.tools = tools or []
        self.tools_map = tools_map or {}
        self.lessons_store = lessons_store
        self.checkpointer = checkpointer or MemorySaver()
        
        # 노드별 독립 LLM 인스턴스 생성 (context 오염 방지)
        if llm:
            # 외부에서 LLM을 주입한 경우 모든 노드에 동일 LLM 사용
            self.llm_router = llm
            self.llm_actor = llm
            self.llm_evaluator = llm
            self.llm_reflection = llm
            self.llm_direct_answer = llm
        else:
            # 노드별 독립 LLM 생성 (settings.yaml 기반)
            print("[Agent] Initializing per-node LLM instances...")
            self.llm_router = get_node_llm("router")
            self.llm_actor = get_node_llm("actor")
            self.llm_evaluator = get_node_llm("evaluator")
            self.llm_reflection = get_node_llm("reflection")
            self.llm_direct_answer = get_node_llm("direct_answer")
            print("[Agent] All node LLMs initialized successfully.")
        
        # 설정에서 max_steps 로드
        agent_config = config.get("agent", {})
        self.max_steps = agent_config.get("max_steps", 5)
        self.max_reflection = agent_config.get("max_reflection", 3)
        
        # 그래프 빌드
        self.graph = self._build_graph()
        self.compiled = self.graph.compile(checkpointer=self.checkpointer)
    
    def _build_graph(self) -> StateGraph:
        """StateGraph 빌드"""
        graph = StateGraph(AgentState)
        
        # 노드 추가 - 클로저로 의존성 주입
        graph.add_node("router", self._create_router_node())
        graph.add_node("direct_answer", self._create_direct_answer_node())
        graph.add_node("actor", self._create_actor_node())
        graph.add_node("tool_executor", self._create_tool_executor_node())
        graph.add_node("evaluator", self._create_evaluator_node())
        graph.add_node("reflection", self._create_reflection_node())
        graph.add_node("exhaustion_answer", self._create_exhaustion_answer_node())
        
        # 엣지 추가
        graph.add_edge(START, "router")
        graph.add_conditional_edges(
            "router",
            lambda x: "actor" if x.get("intent") == "tool_query" else "direct_answer",
            {
                "actor": "actor",
                "direct_answer": "direct_answer",
            }
        )
        graph.add_edge("direct_answer", END)
        graph.add_conditional_edges(
            "actor",
            self._route_after_actor,
            {
                "tool_executor": "tool_executor",
                "exhaustion_answer": "exhaustion_answer",
                "end": END,
            }
        )
        graph.add_edge("tool_executor", "evaluator")
        graph.add_conditional_edges(
            "evaluator",
            self._route_after_evaluator,
            {
                "reflection": "reflection",
                "actor": "actor",
                "exhaustion_answer": "exhaustion_answer",
                "end": END,
            }
        )
        graph.add_edge("reflection", "actor")
        graph.add_edge("exhaustion_answer", END)
        
        return graph
    
    # ============ Node Factories ============
    
    def _create_router_node(self) -> Callable:
        """Router 노드 — gemini-2.5-flash (독립 인스턴스, Tool-Aware)"""
        llm = self.llm_router
        tools = self.tools  # Router에 도구 목록 전달
        def node(state: AgentState) -> Dict[str, Any]:
            return router_node(state, llm=llm, tools=tools)
        return node
        
    def _create_direct_answer_node(self) -> Callable:
        """Direct Answer 노드 — gemini-2.5-flash (독립 인스턴스)"""
        llm = self.llm_direct_answer
        def node(state: AgentState) -> Dict[str, Any]:
            return direct_answer_node(state, llm=llm)
        return node
    
    def _create_actor_node(self) -> Callable:
        """Actor 노드 — gemini-3-flash-preview (독립 인스턴스)"""
        llm = self.llm_actor
        tools = self.tools
        lessons_store = self.lessons_store
        
        def node(state: AgentState) -> Dict[str, Any]:
            # lessons_store에서 교훈 로드
            lessons = []
            if lessons_store:
                lessons = lessons_store.find_relevant(state.get("user_query", ""))
            
            # state에 lessons 추가
            state_with_lessons = {**state, "lessons": lessons}
            
            return actor_node(state_with_lessons, llm=llm, tools=tools)
        
        return node
    
    def _create_tool_executor_node(self) -> Callable:
        """Tool Executor 노드 — LLM 불필요 (도구 실행 전용)"""
        tools_map = self.tools_map
        
        async def node(state: AgentState) -> Dict[str, Any]:
            return await tool_executor_node(state, tools_map=tools_map)
        
        return node
    
    def _create_evaluator_node(self) -> Callable:
        """Evaluator 노드 — gemini-3-flash-preview (독립 인스턴스)"""
        llm = self.llm_evaluator
        
        def node(state: AgentState) -> Dict[str, Any]:
            return evaluator_node(state, llm=llm)
        
        return node
    
    def _create_reflection_node(self) -> Callable:
        """Reflection 노드 — gemini-3-flash-preview (독립 인스턴스)"""
        llm = self.llm_reflection
        lessons_store = self.lessons_store
        
        def node(state: AgentState) -> Dict[str, Any]:
            result = reflection_node(state, llm=llm)
            
            # 새 교훈을 lessons_store에 저장
            # reflection_analysis = 실패 원인 분석 (problem으로 저장)
            # lesson = 학습된 해결책 (solution으로 저장)
            if lessons_store and result.get("lesson"):
                lessons_store.add_lesson(
                    problem=result.get("reflection_analysis", "Unknown problem"),
                    solution=result["lesson"],
                    context=state.get("user_query", ""),
                )
            
            return result
        
        return node
    
    def _create_exhaustion_answer_node(self) -> Callable:
        """Exhaustion Answer 노드 — 반복 제한 초과 시 부분 답변 생성"""
        llm = self.llm_direct_answer  # 빠른 모델 사용
        
        def node(state: AgentState) -> Dict[str, Any]:
            return exhaustion_answer_node(state, llm=llm)
        
        return node
    
    # ============ Routing Functions ============
    
    def _route_after_actor(self, state: AgentState) -> Literal["tool_executor", "exhaustion_answer", "end"]:
        """Actor 후 라우팅"""
        # final_answer가 있으면 종료
        if state.get("final_answer"):
            return "end"
        
        # action이 있으면 tool 실행
        if state.get("action"):
            return "tool_executor"
        
        # max_steps 초과 + final_answer 없음 → exhaustion_answer로
        if state.get("current_step", 0) >= self.max_steps:
            return "exhaustion_answer"
        
        return "exhaustion_answer"
    
    def _route_after_evaluator(
        self, state: AgentState
    ) -> Literal["reflection", "actor", "exhaustion_answer", "end"]:
        """Evaluator 후 라우팅"""
        # FAIL이면 reflection으로
        if state.get("evaluation_status") == "FAIL":
            # 연속 실패 횟수 체크 → exhaustion_answer로
            if state.get("consecutive_failures", 0) >= self.max_reflection:
                return "exhaustion_answer"
            return "reflection"
        
        # PASS이면 actor로 다시 (다음 스텝)
        # max_steps 체크 → 이미 PASS된 상태이므로 정상 종료
        if state.get("current_step", 0) >= self.max_steps:
            return "end"
        
        return "actor"
    
    # ============ Public API ============
    
    def invoke(
        self,
        query: str,
        config: Optional[Dict[str, Any]] = None,
        initial_lessons: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        에이전트 실행
        
        Args:
            query: 사용자 질의
            config: LangGraph config (thread_id 등)
            initial_lessons: 초기 교훈 리스트
            
        Returns:
            최종 상태 딕셔너리
        """
        initial_state = create_initial_state(
            user_query=query,
            lessons=initial_lessons,
        )
        
        graph_config = config or {"configurable": {"thread_id": "default"}}
        
        result = self.compiled.invoke(initial_state, config=graph_config)
        return result
    
    async def ainvoke(
        self,
        query: str,
        config: Optional[Dict[str, Any]] = None,
        initial_lessons: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """비동기 에이전트 실행"""
        initial_state = create_initial_state(
            user_query=query,
            lessons=initial_lessons,
        )
        
        graph_config = config or {"configurable": {"thread_id": "default"}}
        
        result = await self.compiled.ainvoke(initial_state, config=graph_config)
        return result
    
    def stream(
        self,
        query: str,
        config: Optional[Dict[str, Any]] = None,
        initial_lessons: Optional[List[str]] = None,
    ):
        """
        스트리밍 실행 - 각 노드별 결과 반환
        
        Yields:
            {node_name: state_update}
        """
        initial_state = create_initial_state(
            user_query=query,
            lessons=initial_lessons,
        )
        
        graph_config = config or {"configurable": {"thread_id": "default"}}
        
        for event in self.compiled.stream(initial_state, config=graph_config):
            yield event

    async def astream(
        self,
        query: str,
        config: Optional[Dict[str, Any]] = None,
        initial_lessons: Optional[List[str]] = None,
        **kwargs
    ):
        """비동기 스트리밍 실행"""
        initial_state = create_initial_state(
            user_query=query,
            lessons=initial_lessons,
        )
        
        graph_config = config or {"configurable": {"thread_id": "default"}}
        
        async for event in self.compiled.astream(initial_state, config=graph_config, **kwargs):
            yield event
    
    def get_state(self, config: Dict[str, Any]) -> AgentState:
        """특정 thread의 현재 상태 조회"""
        return self.compiled.get_state(config)


# ============ Factory Function ============

def create_reflexion_agent(
    tools: List[Dict[str, Any]] = None,
    tools_map: Dict[str, Callable] = None,
    lessons_store: Optional[Any] = None,
    **llm_kwargs,
) -> ReflexionGraph:
    """
    Reflexion 에이전트 생성 팩토리 함수
    
    Args:
        tools: 도구 설명 리스트
        tools_map: 도구 함수 매핑
        lessons_store: LessonsStore 인스턴스
        **llm_kwargs: get_llm()에 전달할 추가 인자
            비어있으면 노드별 독립 LLM 자동 생성
            값이 있으면 단일 LLM으로 모든 노드 공유
        
    Returns:
        ReflexionGraph 인스턴스
    """
    # llm_kwargs가 있으면 단일 LLM 생성, 없으면 None → 노드별 독립 LLM
    llm = get_llm(**llm_kwargs) if llm_kwargs else None
    
    return ReflexionGraph(
        tools=tools,
        tools_map=tools_map,
        llm=llm,
        lessons_store=lessons_store,
    )
