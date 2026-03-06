"""
LangGraph Nodes - Actor, Evaluator, SelfReflection 노드 함수

각 노드는 프롬프트 YAML 파일을 참조하여 동작.
하드코딩 없이 설정 파일 기반으로 범용적으로 사용 가능.
"""

import json
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.language_models.chat_models import BaseChatModel
import asyncio

from src.agent.state import AgentState
from src.config.prompt_loader import prompts
from src.llm.provider import get_llm


# ============ Exhaustion Answer Node ============

def exhaustion_answer_node(state: AgentState, llm: BaseChatModel = None) -> Dict[str, Any]:
    """
    Exhaustion Answer 노드 — max_steps 또는 max_reflection 초과 시 호출
    
    지금까지 수집된 부분 결과(observation, messages)를 종합하여
    사용자에게 "최선의 부분 답변"을 생성합니다.
    빈손으로 끝나는 대신, 시도한 내용과 확인된 정보를 전달합니다.
    """
    if llm is None:
        llm = get_llm()

    user_query = state.get("user_query", "")
    
    # 지금까지의 도구 실행 이력 수집
    partial_findings = []
    messages = state.get("messages", [])
    for msg in messages:
        content = msg.content if hasattr(msg, 'content') else str(msg)
        if "[Tool Result:" in content:
            partial_findings.append(content)
    
    # 마지막 관찰 결과
    last_observation = state.get("observation", "")
    if last_observation and last_observation not in str(partial_findings):
        partial_findings.append(f"최종 관찰: {last_observation[:800]}")
    
    # 실패 이유
    failure_reason = state.get("evaluation_reason", "")
    reflection_analysis = state.get("reflection_analysis", "")
    consecutive_failures = state.get("consecutive_failures", 0)
    current_step = state.get("current_step", 0)
    
    findings_text = "\n".join(partial_findings[-5:]) if partial_findings else "(수집된 정보 없음)"
    
    system_prompt = """당신은 친절한 AI 어시스턴트입니다.
여러 차례 시도했으나 사용자의 질문에 완벽한 답변을 제공하지 못한 상황입니다.
지금까지 수집한 부분 정보를 바탕으로 최선의 답변을 작성하세요.

규칙:
1. 수집된 정보가 있다면 그것을 정리하여 전달
2. 부족한 부분은 솔직히 언급 ("~에 대해서는 충분한 정보를 확보하지 못했습니다")
3. 추가로 확인할 수 있는 방법 안내 (예: 공식 웹사이트, 고객센터 등)
4. 마크다운 형식으로 깔끔하게 작성
5. 절대 거짓 정보를 만들어내지 마세요"""

    user_prompt = f"""사용자 질문: {user_query}

시도 횟수: {current_step}회
연속 실패: {consecutive_failures}회
마지막 실패 원인: {failure_reason}
실패 분석: {reflection_analysis}

--- 수집된 부분 정보 ---
{findings_text}
--- 끝 ---

위 정보를 바탕으로 사용자에게 전달할 최선의 답변을 작성하세요."""

    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])

        content = response.content
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict) and 'text' in part:
                    parts.append(part['text'])
                elif isinstance(part, str):
                    parts.append(part)
            content = "\n".join(parts)

        return {
            "final_answer": content,
            "thought": "최대 시도 횟수 초과 — 수집된 정보로 부분 답변 생성",
        }
    except Exception as e:
        # LLM 호출까지 실패하면 규칙 기반 fallback
        fallback_parts = [f"## 답변 안내\n\n'{user_query}'에 대해 {current_step}회 시도했으나 충분한 답변을 구성하지 못했습니다.\n"]
        if partial_findings:
            fallback_parts.append("### 지금까지 확인된 정보\n")
            for finding in partial_findings[-3:]:
                # Tool Result prefix 제거하고 핵심만
                clean = finding.replace("[Tool Result:", "**도구 결과** (").replace("]", "):", 1) if "[Tool Result:" in finding else finding
                fallback_parts.append(f"{clean[:500]}\n")
        fallback_parts.append(f"\n> 💡 추가 정보가 필요하시면 질문을 더 구체적으로 바꿔 다시 시도해 주세요.")
        
        return {
            "final_answer": "\n".join(fallback_parts),
            "thought": f"Exhaustion fallback (LLM error: {e})",
        }


def _parse_json_response(text: str) -> Dict[str, Any]:
    """LLM 응답에서 JSON 추출 — Gemini 3 Flash Preview 호환
    
    여러 단계의 파싱을 시도:
    1. ```json ... ``` 코드 블록 추출
    2. ``` ... ``` 일반 코드 블록 추출
    3. { ... } 중괄호 직접 탐색
    4. 모든 파싱 실패 시 텍스트를 final_answer로 감싸서 반환
    """
    import re
    
    # Gemini 3 Flash Preview는 content를 list of parts로 반환할 수 있음
    if isinstance(text, list):
        # [{'type': 'text', 'text': '...'}, ...] 형태 처리
        parts = []
        for part in text:
            if isinstance(part, dict) and 'text' in part:
                parts.append(part['text'])
            elif isinstance(part, str):
                parts.append(part)
        text = "\n".join(parts)
    
    if not isinstance(text, str):
        text = str(text)
    
    print(f"[DEBUG PARSE] Raw text: {text[:500]}")
    
    # 1단계: ```json 코드 블록
    try:
        if "```json" in text:
            json_str = text.split("```json")[1].split("```")[0]
            return json.loads(json_str.strip())
    except (json.JSONDecodeError, IndexError) as e:
        print(f"[DEBUG PARSE] json block failed: {e}")
    
    # 2단계: ``` 일반 코드 블록
    try:
        if "```" in text:
            json_str = text.split("```")[1].split("```")[0]
            result = json.loads(json_str.strip())
            if isinstance(result, dict):
                return result
    except (json.JSONDecodeError, IndexError) as e:
        print(f"[DEBUG PARSE] code block failed: {e}")
    
    # 3단계: { ... } 최외곽 중괄호 직접 탐색
    try:
        brace_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
        if brace_match:
            result = json.loads(brace_match.group())
            if isinstance(result, dict) and ("action" in result or "final_answer" in result or "thought" in result):
                return result
    except json.JSONDecodeError as e:
        print(f"[DEBUG PARSE] brace search failed: {e}")
    
    # 4단계: 모든 파싱 실패 → 텍스트 자체를 final_answer로 활용 (graceful fallback)
    print(f"[DEBUG PARSE] All JSON parsing failed, using text as final_answer")
    # 코드 블록, 마크다운 fence 제거
    clean_text = re.sub(r'```\w*\n?', '', text).strip()
    if clean_text:
        return {
            "thought": "JSON 형식 파싱 실패, 텍스트 응답을 직접 전달",
            "final_answer": clean_text
        }
    
    return dict()


def _format_tools_desc(tools: List[Dict[str, Any]]) -> str:
    """도구 목록 포맷팅"""
    if not tools:
        return prompts.get_template("actor", "no_tools") or "(사용 가능한 도구 없음)"
    
    lines = []
    for t in tools:
        lines.append(f"- {t['name']}: {t['description']} (Args: {t.get('args', '{}')})")
    return "\n".join(lines)


def _format_lessons(lessons: List[str]) -> str:
    """교훈 포맷팅"""
    if not lessons:
        return prompts.get_template("actor", "no_lessons") or "(축적된 교훈 없음)"
    return "\n".join(f"- {lesson}" for lesson in lessons)


def _format_history(messages: List[Any]) -> str:
    """메시지 히스토리 포맷팅"""
    if not messages:
        return ""
    
    header = prompts.get_template("actor", "history_header") or "--- 이전 실행 기록 ---"
    footer = prompts.get_template("actor", "history_footer") or "----------------------"
    
    lines = [header]
    for msg in messages[-20:]:  # 최근 20개
        if hasattr(msg, 'content'):
            role = "Human" if isinstance(msg, HumanMessage) else "AI"
            content = msg.content
            # observation은 더 길게 보여줌 (500자)
            max_len = 500 if role == "AI" else 200
            if len(content) > max_len:
                content = content[:max_len] + "..."
            lines.append(f"{role}: {content}")
    lines.append(footer)
    return "\n".join(lines)


# ============ Actor Node ============

def actor_node(state: AgentState, llm: BaseChatModel = None, tools: List[Dict] = None) -> Dict[str, Any]:
    """
    Actor 노드 - 다음 행동 결정
    
    프롬프트: src/prompts/actor.yaml
    
    Returns:
        {"thought", "action", "action_input"} 또는 {"thought", "final_answer"}
    """
    if llm is None:
        llm = get_llm()
    
    # 프롬프트 구성
    tools_desc = _format_tools_desc(tools or [])
    lessons_text = _format_lessons(state.get("lessons", []))
    history_text = _format_history(state.get("messages", []))
    
    # 시스템 프롬프트 로드
    system_prompt = prompts.get_system_prompt("actor")
    system_prompt = system_prompt.format(
        tools_desc=tools_desc,
        lessons_text=lessons_text
    )
    
    # 사용자 프롬프트 구성
    user_query = state.get("user_query", "")
    user_prompt = f"{history_text}\n\n사용자 요청: {user_query}"
    
    # 이전 observation이 있으면 추가
    if state.get("observation"):
        user_prompt += f"\n\n이전 실행 결과:\n{state['observation']}"
    
    # Reflection의 재시도 전략이 있으면 추가 (논리적 실패 피드백)
    if state.get("reflection_suggestion"):
        user_prompt += f"\n\n" + "="*50
        user_prompt += f"\n⚠️ [중요] 이전 시도가 실패하여 Reflection이 다음 전략을 제안했습니다:\n"
        if state.get("reflection_analysis"):
            user_prompt += f"실패 원인: {state['reflection_analysis']}\n"
        user_prompt += f"▶ 반드시 따를 전략: {state['reflection_suggestion']}\n"
        user_prompt += f"교훈: {state.get('lesson', '')}\n"
        user_prompt += "="*50
        user_prompt += "\n위 전략을 **반드시** 따라 다음 행동을 결정하세요. 이전과 같은 도구/파라미터를 반복하지 마세요."
    
    # LLM 호출
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt)
    ]
    
    try:
        response = llm.invoke(messages)
        result = _parse_json_response(response.content)
        
        # 결과 검증
        if not result.get("thought"):
            result["thought"] = prompts.get_default("actor", "fallback_thought", "Analyzing...")
        
        # action 또는 final_answer 확인
        if "final_answer" in result:
            return {
                "thought": result.get("thought"),
                "final_answer": result.get("final_answer"),
                "action": None,
                "action_input": None,
                "current_step": state.get("current_step", 0) + 1,
                "messages": [
                    HumanMessage(content=f"[Step {state.get('current_step', 0)+1}] {user_prompt}"),
                ],
            }
        elif "action" in result:
            return {
                "thought": result.get("thought"),
                "action": result.get("action"),
                "action_input": result.get("action_input", {}),
                "final_answer": None,
                "current_step": state.get("current_step", 0) + 1,
                "messages": [
                    HumanMessage(content=f"[Step {state.get('current_step', 0)+1}] Thought: {result.get('thought', '')}\nAction: {result.get('action', '')}"),
                ],
            }
        else:
            # 파싱 실패 시 기본 응답
            return {
                "thought": "Unable to parse response",
                "final_answer": prompts.get_default("actor", "fallback_answer", "Unable to determine action"),
                "action": None,
                "action_input": None,
                "current_step": state.get("current_step", 0) + 1,
            }
    except Exception as e:
        return {
            "thought": f"Error: {str(e)}",
            "final_answer": f"Actor error: {str(e)}",
            "action": None,
            "action_input": None,
            "current_step": state.get("current_step", 0) + 1,
        }


# ============ Evaluator Node ============

def evaluator_node(state: AgentState, llm: BaseChatModel = None) -> Dict[str, Any]:
    """
    Evaluator 노드 - 2단계 평가 (기술적 + 논리적)
    
    프롬프트: src/prompts/evaluator.yaml
    
    1단계 (규칙 기반): 도구 실행의 기술적 성공/실패 → 에러 시 즉시 FAIL
    2단계 (LLM 기반): 결과의 논리적 적합성 평가 → 질문에 부합하는지 검증
    
    Returns:
        {"evaluation_status": "PASS"|"FAIL", "evaluation_reason": str,
         "evaluation_type": "technical"|"logical"}
    """
    observation = state.get("observation", "")
    
    # ── 1단계: 기술적 평가 (규칙 기반) ──
    simple_result = _evaluate_simple(observation)
    
    if simple_result["status"] == "FAIL":
        return {
            "evaluation_status": "FAIL",
            "evaluation_reason": simple_result["reason"],
            "evaluation_type": "technical",
            "consecutive_failures": state.get("consecutive_failures", 0) + 1,
        }
    
    # ── 2단계: 논리적 평가 (LLM 기반) ──
    # final_answer가 있거나, 도구 실행 결과가 있을 때 LLM으로 논리적 적합성 검증
    if not observation.strip() and not state.get("final_answer"):
        return {
            "evaluation_status": "PASS",
            "evaluation_reason": simple_result["reason"],
            "evaluation_type": "technical",
            "consecutive_failures": 0,
        }
    
    if llm is None:
        llm = get_llm()
    
    system_prompt = prompts.get_system_prompt("evaluator")
    
    user_query = state.get("user_query", "")
    action = state.get("action", "")
    action_input = state.get("action_input", {})
    final_answer = state.get("final_answer", "")
    
    context_template = prompts.get_template("evaluator", "context")
    if context_template:
        user_prompt = context_template.format(
            user_query=user_query,
            action=action,
            action_input=action_input,
            observation=observation,
            final_answer=final_answer or "(아직 최종 답변 없음)",
        )
    else:
        user_prompt = f"""사용자 요청: {user_query}
실행한 행동: {action}
입력: {action_input}
결과: {observation}
최종 답변: {final_answer or "(아직 최종 답변 없음)"}"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt)
    ]
    
    try:
        response = llm.invoke(messages)
        result = _parse_json_response(response.content)
        
        status = result.get("status", "PASS").upper()
        if status not in ["PASS", "FAIL"]:
            status = "PASS"
        
        eval_type = result.get("type", "logical")
        
        consecutive = state.get("consecutive_failures", 0)
        if status == "FAIL":
            consecutive += 1
        else:
            consecutive = 0
        
        return {
            "evaluation_status": status,
            "evaluation_reason": result.get("reason", "No reason provided"),
            "evaluation_type": eval_type,
            "consecutive_failures": consecutive,
        }
    except Exception as e:
        return {
            "evaluation_status": prompts.get_default("evaluator", "fallback_status", "PASS"),
            "evaluation_reason": f"Evaluator error: {str(e)}",
            "evaluation_type": "technical",
            "consecutive_failures": state.get("consecutive_failures", 0),
        }


def _evaluate_simple(observation: str) -> Dict[str, str]:
    """규칙 기반 간단 평가 (LLM 호출 없이)"""
    prompt_config = prompts.get_prompt("evaluator")
    error_indicators = prompt_config.get("error_indicators", [
        "error", "exception", "failed", "not found", "실패", "오류"
    ])
    
    observation_lower = observation.lower()
    
    for indicator in error_indicators:
        if indicator in observation_lower:
            return {"status": "FAIL", "reason": f"Error indicator '{indicator}' found"}
    
    if not observation or observation.strip() == "":
        return {"status": "FAIL", "reason": "Empty observation"}
    
    return {"status": "PASS", "reason": "No error indicators found"}


# ============ Self-Reflection Node ============

def reflection_node(state: AgentState, llm: BaseChatModel = None) -> Dict[str, Any]:
    """
    Self-Reflection 노드 - 실패 분석 및 재시도 전략 수립
    
    기술적/논리적 실패를 구분하여 적절한 재시도 전략을 수립합니다.
    
    프롬프트: src/prompts/self_reflection.yaml
    
    Returns:
        {"lesson": str, "reflection_analysis": str, "reflection_suggestion": str}
    """
    if llm is None:
        llm = get_llm()
    
    system_prompt = prompts.get_system_prompt("self_reflection")
    
    # 실패 컨텍스트 구성
    failed_context = ""
    if state.get("action"):
        failed_context = f"\n실패한 행동: {state['action']}"
        if state.get("action_input"):
            failed_context += f"\n입력: {state['action_input']}"
    if state.get("observation"):
        obs_preview = state["observation"][:1000]
        failed_context += f"\n실행 결과: {obs_preview}"
    
    history_text = _format_history(state.get("messages", []))
    last_error = state.get("evaluation_reason", state.get("observation", "Unknown error"))
    failure_type = state.get("evaluation_type", "unknown")
    evaluator_suggestion = ""
    
    # Evaluator가 suggestion을 제공했으면 전달
    if state.get("evaluation_reason"):
        evaluator_suggestion = state["evaluation_reason"]
    
    context_template = prompts.get_template("self_reflection", "context")
    if context_template:
        user_prompt = context_template.format(
            user_query=state.get("user_query", ""),
            failed_context=failed_context,
            history_text=history_text,
            failure_type=failure_type,
            last_error=last_error,
            evaluator_suggestion=evaluator_suggestion,
        )
    else:
        user_prompt = f"""사용자 요청: {state.get("user_query", "")}
{failed_context}
{history_text}
마지막 실패: {last_error}"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt)
    ]
    
    try:
        response = llm.invoke(messages)
        result = _parse_json_response(response.content)
        
        suggestion = result.get("suggestion", prompts.get_default("self_reflection", "fallback_suggestion", "Try a different approach"))
        
        return {
            "lesson": result.get("lesson", prompts.get_default("self_reflection", "fallback_lesson", "Verify inputs")),
            "reflection_analysis": result.get("analysis", prompts.get_default("self_reflection", "fallback_analysis", "Analysis unavailable")),
            "reflection_suggestion": suggestion,
        }
    except Exception as e:
        return {
            "lesson": prompts.get_default("self_reflection", "fallback_lesson", "Unexpected error, try different approach"),
            "reflection_analysis": f"Reflection error: {str(e)}",
            "reflection_suggestion": "Try a different approach",
        }


# ============ Tool Executor Node ============

async def tool_executor_node(state: AgentState, tools_map: Dict[str, callable] = None) -> Dict[str, Any]:
    """
    Tool 실행 노드
    
    Actor가 선택한 action을 실제로 실행.
    
    Args:
        state: 현재 상태
        tools_map: {"tool_name": LangChain Tool} 매핑
        
    Returns:
        {"observation": str}
    """
    action = state.get("action")
    action_input = state.get("action_input", {})
    
    if not action:
        return {"observation": "No action specified"}
    
    if tools_map is None:
        return {"observation": f"Tool '{action}' not available (no tools provided)"}
    
    tool = tools_map.get(action)
    if not tool:
        available = list(tools_map.keys())
        return {"observation": f"Unknown tool: {action}. Available: {available}"}
    
    try:
        # LangChain Tool은 .invoke() 메서드 사용
        if hasattr(tool, 'ainvoke'):
            if isinstance(action_input, dict):
                result = await tool.ainvoke(action_input)
            else:
                result = await tool.ainvoke({"input": action_input})
        elif hasattr(tool, 'invoke'):
            if isinstance(action_input, dict):
                result = tool.invoke(action_input)
            else:
                result = tool.invoke({"input": action_input})
        elif asyncio.iscoroutinefunction(tool):
            if isinstance(action_input, dict):
                result = await tool(**action_input)
            else:
                result = await tool(action_input)
        elif callable(tool):
            # 일반 callable의 경우
            if isinstance(action_input, dict):
                result = tool(**action_input)
            else:
                result = tool(action_input)
        else:
            return {"observation": f"Tool '{action}' is not callable"}
        
        # 결과를 문자열로 변환
        if isinstance(result, dict):
            observation = json.dumps(result, ensure_ascii=False, indent=2)
        elif isinstance(result, list):
            observation = json.dumps(result, ensure_ascii=False, indent=2)
        else:
            observation = str(result)
        
        # ── 출처(Source) 추출 ──
        sources = _extract_sources(action, action_input, observation)
        
        # observation을 messages에도 누적하여 Actor가 이전 결과를 참조할 수 있도록 함
        from langchain_core.messages import AIMessage
        obs_summary = observation[:800] if len(observation) > 800 else observation
        return {
            "observation": observation,
            "sources": sources,
            "messages": [
                AIMessage(content=f"[Tool Result: {action}]\n{obs_summary}"),
            ],
        }
    except Exception as e:
        from langchain_core.messages import AIMessage
        err_msg = f"Tool execution error: {str(e)}"
        return {
            "observation": err_msg,
            "messages": [
                AIMessage(content=f"[Tool Error: {action}] {err_msg}"),
            ],
        }


# ============ Source Extraction Helper ============

def _extract_sources(action: str, action_input: Any, observation: str) -> list:
    """
    도구 실행 결과에서 참고 자료(출처) 정보를 추출합니다.
    
    출처 유형:
      - document: 내부 문서 (KG, 문서 조회)
      - web: 웹 검색 결과 (URL 포함)
    """
    import re
    sources = []
    
    if action == "web_search":
        # 웹 검색: **title** + 출처: URL 패턴 추출
        # 패턴: "  1. **제목**\n     내용\n     출처: URL"
        entries = re.findall(
            r'\d+\.\s+\*\*(.+?)\*\*.*?출처:\s*(https?://\S+)',
            observation,
            re.DOTALL
        )
        seen_urls = set()
        for title, url in entries:
            if url not in seen_urls:
                seen_urls.add(url)
                sources.append({
                    "type": "web",
                    "title": title.strip(),
                    "url": url.strip(),
                    "tool": action,
                })
    
    elif action == "query_knowledge_graph":
        # KG 검색: 결과 자체가 문서 기반이므로 도구 사용 기록만
        query = ""
        if isinstance(action_input, dict):
            query = action_input.get("query", "")
        sources.append({
            "type": "document",
            "title": f"지식 그래프 검색: {query[:60]}" if query else "지식 그래프 검색",
            "tool": action,
        })
    
    elif action in ("get_document_content", "get_document_summary", "get_document_info"):
        # 문서 조회 계열: filename 직접 사용
        filename = ""
        if isinstance(action_input, dict):
            filename = action_input.get("filename", "")
        if filename and "error" not in observation.lower()[:100]:
            sources.append({
                "type": "document",
                "title": filename,
                "tool": action,
            })
    
    elif action == "list_documents":
        # 문서 목록은 메타 정보이므로 출처 불필요
        pass
    
    elif action == "list_document_summaries":
        pass
    
    elif action == "get_system_status":
        pass
    
    return sources
