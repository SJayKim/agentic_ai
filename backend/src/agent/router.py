"""
Router Node — Tool-Aware Intent Router

프롬프트: prompts/router.yaml
모델: gemini-2.5-flash (빠른 분류에 최적화)

사용자의 쿼리 + 사용 가능한 도구 목록을 함께 분석하여
tool_query(도구 사용 필요) 또는 general_chat(직접 응답)으로 분류합니다.

핵심 개선:
  기존: 도구 목록 없이 막연한 카테고리("문서 질문 vs 일반 대화")로 분류
  개선: 실제 도구 목록 요약을 프롬프트에 주입 → "이 쿼리를 처리할 도구가 있는가?" 판단
"""

import json
import re
from typing import Dict, Any, List

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage

from src.agent.state import AgentState
from src.config.prompt_loader import prompts
from src.llm.provider import get_node_llm


def _build_tools_summary(tools: List[Dict[str, Any]]) -> str:
    """도구 목록을 Router용 간결한 요약으로 변환.
    
    Actor에 주입하는 상세 description과 달리, Router에는
    도구명 + 한 줄 요약만 전달하여 토큰을 절약합니다.
    """
    if not tools:
        return "(사용 가능한 도구 없음)"
    
    lines = []
    for t in tools:
        name = t.get("name", "unknown")
        desc = t.get("description", "")
        # description에서 첫 문장(마침표까지)만 추출
        short = desc.split(". ")[0].split("。")[0]
        if not short.endswith(".") and not short.endswith("다"):
            short += "."
        lines.append(f"  - {name}: {short}")
    return "\n".join(lines)


def router_node(state: AgentState, llm: BaseChatModel = None, tools: List[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Tool-Aware Router 노드 — 사용자 의도 분류
    
    프롬프트: prompts/router.yaml (tools_summary 플레이스홀더 포함)
    독립 LLM 인스턴스 사용 (context 오염 방지)
    
    Args:
        state: AgentState
        llm: Router용 LLM
        tools: 에이전트가 사용 가능한 도구 설명 리스트
    
    Returns:
        {"intent": "tool_query" | "general_chat"}
    """
    if llm is None:
        llm = get_node_llm("router")
    
    query = state.get("user_query", "")
    
    # 도구 목록 요약 생성
    tools_summary = _build_tools_summary(tools) if tools else "(도구 정보를 사용할 수 없음)"
    
    # YAML에서 시스템 프롬프트 로드 + 도구 요약 주입
    system_prompt = prompts.get_system_prompt("router")
    if not system_prompt:
        system_prompt = _FALLBACK_ROUTER_PROMPT
    
    # {tools_summary} 플레이스홀더 치환
    system_prompt = system_prompt.replace("{tools_summary}", tools_summary)
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"사용자 질의: {query}"),
    ]
    
    try:
        response = llm.invoke(messages)
        text = response.content
        
        # JSON 추출
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            text = match.group(0)
        parsed = json.loads(text)
        intent = parsed.get("intent", "tool_query")
        
        # 하위 호환: 기존 "rag_query"도 "tool_query"로 매핑
        if intent == "rag_query":
            intent = "tool_query"
        
        # 유효성 검증
        if intent not in ("tool_query", "general_chat"):
            intent = "tool_query"
        
        confidence = parsed.get("confidence", 0.5)
        reason = parsed.get("reason", "")
        print(f"[Router] intent={intent}, confidence={confidence}, reason={reason}")
        
    except Exception as e:
        print(f"[Router] Parse error: {e}, falling back to tool_query")
        intent = prompts.get_default("router", "fallback_intent", "tool_query")
        
    return {"intent": intent}


def direct_answer_node(state: AgentState, llm: BaseChatModel = None) -> Dict[str, Any]:
    """
    Direct Answer 노드 — 도구 없이 직접 응답
    
    프롬프트: prompts/router.yaml → direct_answer_prompt
    일반 대화, 인사, 감사 등에 사용
    """
    if llm is None:
        llm = get_node_llm("direct_answer")
    
    query = state.get("user_query", "")
    
    # YAML에서 direct_answer 프롬프트 로드
    router_config = prompts.get_prompt("router")
    da_prompt = router_config.get("direct_answer_prompt", "")
    if not da_prompt:
        da_prompt = "당신은 친절하고 도움이 되는 AI 어시스턴트입니다. 자연스럽게 한국어로 대화하세요."
    
    messages = [
        SystemMessage(content=da_prompt),
        HumanMessage(content=query),
    ]
    
    try:
        response = llm.invoke(messages)
        return {
            "final_answer": response.content,
            "thought": "Router가 일반 대화로 분류하여 직접 응답합니다.",
        }
    except Exception as e:
        return {
            "final_answer": f"죄송합니다, 응답 생성 중 오류가 발생했습니다: {str(e)}",
            "thought": f"Direct answer error: {str(e)}",
        }


# Fallback prompt (YAML 로드 실패 시)
_FALLBACK_ROUTER_PROMPT = """You are a tool-aware intent classifier.
Classify the user's query as either "tool_query" (needs tools like search, document access, web search)
or "general_chat" (simple greeting, small talk, general knowledge).
Respond ONLY with JSON: {"intent": "tool_query" | "general_chat", "confidence": 0.0-1.0, "reason": "brief reason"}"""
