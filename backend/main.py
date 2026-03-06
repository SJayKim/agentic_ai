import os
import uvicorn
from typing import Dict, Any, List
from fastapi import FastAPI, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import shutil

from src.agent.graph import create_reflexion_agent
from src.tools import get_all_tools_descriptions, get_all_tools_map
from src.memory.lessons_store import LessonsStore
from src.rag.lightrag_manager import ingest_documents, ingest_single_document
from src.rag.document_converter import SUPPORTED_EXTENSIONS

app = FastAPI(title="LightRAG Agent Demo API")

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    from src.rag.lightrag_manager import rag
    print("Initializing LightRAG storages on startup...")
    await rag.initialize_storages()
    print("LightRAG storages ready!")

# Initialize Agent
lessons_store = LessonsStore()
agent = create_reflexion_agent(
    tools=get_all_tools_descriptions(),
    tools_map=get_all_tools_map(),
    lessons_store=lessons_store
)

import json
import asyncio
from fastapi.responses import StreamingResponse

# Node별 사용자 친화적 라벨 매핑
NODE_LABELS = {
    "router": {"icon": "🔍", "label": "의도 분류 중..."},
    "actor": {"icon": "🧠", "label": "행동 결정 중..."},
    "tool_executor": {"icon": "🔧", "label": "도구 실행 중..."},
    "evaluator": {"icon": "📋", "label": "결과 평가 중..."},
    "reflection": {"icon": "💡", "label": "자기 반성 및 학습 중..."},
    "direct_answer": {"icon": "💬", "label": "답변 생성 중..."},
}

# 최종 답변 스트리밍 청크 크기 (글자 수)
ANSWER_CHUNK_SIZE = 8

class ChatRequest(BaseModel):
    query: str
    thread_id: str = "default_session"

@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    async def generate():
        step_counter = 0
        all_sources = []  # 모든 노드에서 수집된 출처
        try:
            config = {"configurable": {"thread_id": request.thread_id}}
            async for event in agent.astream(request.query, config=config, stream_mode="updates"):
                for node_name, state_update in event.items():
                    step_counter += 1
                    node_info = NODE_LABELS.get(node_name, {"icon": "⚙️", "label": node_name})

                    # ── 출처 수집 ──
                    if state_update.get("sources"):
                        all_sources.extend(state_update["sources"])

                    # ── 1) 사고 과정(Thinking) 이벤트 ──
                    thinking_data = {
                        "type": "thinking",
                        "step": step_counter,
                        "node": node_name,
                        "icon": node_info["icon"],
                        "label": node_info["label"],
                    }

                    # 각 노드별 핵심 정보만 간결하게 추출
                    if node_name == "router":
                        intent = state_update.get("intent", "unknown")
                        intent_label = {
                            "tool_query": "도구 사용 질문",
                            "rag_query": "문서 검색 질문",
                            "general_chat": "일반 대화",
                        }.get(intent, intent)
                        thinking_data["detail"] = f"분류 결과: {intent_label}"

                    elif node_name == "actor":
                        if state_update.get("thought"):
                            thinking_data["detail"] = state_update["thought"]
                        if state_update.get("action"):
                            thinking_data["label"] = "다음 행동 결정"
                            thinking_data["action"] = state_update["action"]
                            action_input = state_update.get("action_input", {})
                            if isinstance(action_input, dict) and action_input.get("query"):
                                thinking_data["action_detail"] = f'검색어: "{action_input["query"]}"'

                    elif node_name == "tool_executor":
                        obs = state_update.get("observation", "")
                        thinking_data["label"] = "도구 실행 완료"
                        thinking_data["detail"] = (obs[:200] + "...") if len(obs) > 200 else obs

                    elif node_name == "evaluator":
                        status = state_update.get("evaluation_status", "")
                        reason = state_update.get("evaluation_reason", "")
                        thinking_data["label"] = f"평가: {'✅ 성공' if status == 'PASS' else '❌ 실패'}"
                        thinking_data["detail"] = reason[:150] if reason else ""

                    elif node_name == "reflection":
                        thinking_data["detail"] = state_update.get("lesson", "")

                    elif node_name == "exhaustion_answer":
                        thinking_data["label"] = "부분 답변 생성"
                        thinking_data["detail"] = state_update.get("thought", "최대 시도 횟수 초과 — 수집된 정보로 답변 생성")

                    elif node_name == "direct_answer":
                        thinking_data["detail"] = "일반 대화 답변 생성"

                    # thinking 이벤트 전송 (final_answer만 있는 노드도 일단 thinking 보냄)
                    yield f"data: {json.dumps(thinking_data, ensure_ascii=False)}\n\n"

                    # ── 2) 최종 답변 스트리밍 ──
                    final_answer = state_update.get("final_answer")
                    if final_answer:
                        # 답변 시작 시그널
                        yield f"data: {json.dumps({'type': 'answer_start'}, ensure_ascii=False)}\n\n"

                        # 글자 단위 청크로 스트리밍
                        for i in range(0, len(final_answer), ANSWER_CHUNK_SIZE):
                            chunk = final_answer[i:i + ANSWER_CHUNK_SIZE]
                            yield f"data: {json.dumps({'type': 'answer_chunk', 'content': chunk}, ensure_ascii=False)}\n\n"
                            await asyncio.sleep(0.02)

                        # ── 2-b) 참고 자료(Sources) 이벤트 ──
                        if all_sources:
                            # 중복 제거 (title+type 기준)
                            seen = set()
                            unique_sources = []
                            for src in all_sources:
                                key = (src.get("type"), src.get("title"), src.get("url", ""))
                                if key not in seen:
                                    seen.add(key)
                                    unique_sources.append(src)
                            yield f"data: {json.dumps({'type': 'sources', 'sources': unique_sources}, ensure_ascii=False)}\n\n"

            # ── 3) 완료 시그널 ──
            yield f"data: {json.dumps({'type': 'done', 'total_steps': step_counter}, ensure_ascii=False)}\n\n"

        except Exception as e:
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

# 구 엔드포인트 호환 (브라우저 캐시 대응) - 내부적으로 stream과 동일 로직 사용
@app.post("/api/chat")
async def chat_compat(request: ChatRequest):
    try:
        config = {"configurable": {"thread_id": request.thread_id}}
        result = await agent.ainvoke(request.query, config=config)
        return {"status": "success", "answer": result.get("final_answer", "No answer generated.")}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/ingest")
async def ingest():
    try:
        result = await ingest_documents()
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/upload")
async def upload_document(file: UploadFile = File(...)):
    try:
        docs_dir = "./data/documents"
        if not os.path.exists(docs_dir):
            os.makedirs(docs_dir)
        
        # 지원되는 파일 형식 확인
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return {
                "status": "error",
                "message": f"Unsupported file type: {ext}. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            }
            
        file_path = os.path.join(docs_dir, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # 단일 문서 변환 후 KG에 인제스트
        result = await ingest_single_document(file_path)
        return {
            "status": result["status"],
            "message": f"File uploaded: {file.filename}",
            "ingest_result": result
        }
    except Exception as e:
        return {"status": "error", "message": f"Upload failed: {str(e)}"}

@app.get("/api/documents")
async def list_documents():
    docs_dir = "./data/documents"
    if not os.path.exists(docs_dir):
        return {"documents": []}
    
    documents = []
    for entry in sorted(os.listdir(docs_dir)):
        file_path = os.path.join(docs_dir, entry)
        if not os.path.isfile(file_path):
            continue
        ext = os.path.splitext(entry)[1].lower()
        if ext in SUPPORTED_EXTENSIONS:
            size_kb = os.path.getsize(file_path) / 1024
            documents.append({
                "filename": entry,
                "type": ext[1:].upper(),
                "size_kb": round(size_kb, 1),
            })
    
    return {"documents": documents, "supported_types": sorted(SUPPORTED_EXTENSIONS)}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
