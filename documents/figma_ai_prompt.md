# Figma AI 도식화 프롬프트

아래 프롬프트를 Figma AI에 입력하여 프로세스 다이어그램을 생성하세요.

---

## 프롬프트 1: 전체 에이전트 처리 흐름 (메인 다이어그램)

```
Create a professional system architecture flowchart for an "Agentic AI" system using a clean, modern design with rounded rectangles, soft shadows, and a dark navy (#1a1a2e) background with white text.

Layout: Top-to-bottom flow with clear swim lanes.

=== NODES (rounded rectangles) ===

1. "User Query" — Starting point, light blue (#4fc3f7) pill shape at the top
2. "Router" — Teal (#26a69a), labeled "Router (Gemini 2.5 Flash)", subtitle "Intent Classification: tool_query / general_chat"
3. "Direct Answer" — Green (#66bb6a), labeled "Direct Answer (Gemini 2.5 Flash)", subtitle "General Conversation"
4. "Actor" — Orange (#ffa726), labeled "Actor (Gemini 3 Flash Preview)", subtitle "Reasoning + Tool Selection"
5. "Tool Executor" — Purple (#ab47bc), labeled "Tool Executor", subtitle "Execute Selected Tool"
6. "Evaluator" — Red-orange (#ef5350), labeled "Evaluator (Gemini 3 Flash Preview)", subtitle "Technical + Logical Quality Assessment"
7. "Reflection" — Pink (#ec407a), labeled "Reflection (Gemini 3 Flash Preview)", subtitle "Failure Analysis + Strategy Revision"
8. "Exhaustion Answer" — Gray (#78909c), labeled "Exhaustion Answer", subtitle "Best-effort Answer from Partial Results"
9. "Final Answer" — Bright green (#00e676) pill shape at the bottom

=== EDGES (arrows with labels) ===

- User Query → Router
- Router → Direct Answer (label: "general_chat")
- Router → Actor (label: "tool_query")
- Direct Answer → Final Answer
- Actor → Tool Executor (label: "has action")
- Actor → Final Answer (label: "has final_answer")
- Actor → Exhaustion Answer (label: "max_steps exceeded")
- Tool Executor → Evaluator
- Evaluator → Actor (label: "PASS → next step")
- Evaluator → Reflection (label: "FAIL")
- Evaluator → Exhaustion Answer (label: "FAIL + max_reflection exceeded")
- Reflection → Actor (label: "revised strategy", dashed arrow)
- Exhaustion Answer → Final Answer

=== VISUAL STYLE ===
- Use 2px white arrows with labels in small gray text
- Add a subtle glow effect on the Router and Evaluator nodes (key decision points)
- Group Actor → Tool Executor → Evaluator in a dashed rectangle labeled "ReAct Loop (max 5 steps)"
- Group Evaluator → Reflection → Actor in another dashed rectangle labeled "Reflexion Loop (max 3 retries)"
- Add small icons: 🧠 on Actor, ⚙️ on Tool Executor, ✅/❌ on Evaluator, 🔄 on Reflection, 🗣️ on Router
- Bottom right corner: small legend box with node colors mapped to their LLM model
```

---

## 프롬프트 2: KG 쿼리 파이프라인 (LightRAG 내부 흐름)

```
Create a detailed pipeline diagram showing how a Knowledge Graph query works internally. Use a horizontal left-to-right flow with a clean white background and modern flat design.

=== PIPELINE STAGES ===

Stage 1: "Keyword Extraction" — Blue (#2196f3)
- Input: User query text
- Process: LLM extracts High-Level keywords (themes, concepts) and Low-Level keywords (proper nouns, terms)
- Output: HL keywords + LL keywords
- Icon: 🔑

Stage 2: "Vector Search" — Purple (#9c27b0)
- Split into two parallel paths:
  Path A — "Local Search (LL keywords)":
    - Search entities vector DB (938 items, 384d embeddings)
    - Find similar entity nodes by cosine similarity
    - Icon: 📍
  Path B — "Global Search (HL keywords)":
    - Search relationships vector DB (1,281 items, 384d embeddings)
    - Find similar relationship edges by cosine similarity
    - Icon: 🌐

Stage 3: "Graph Expansion" — Orange (#ff9800)
- Split into two parallel paths matching Stage 2:
  Path A — "Local Expansion":
    - From found nodes → traverse graph.edges() → collect 1-hop neighbor edges
    - Deduplicate with sorted tuple trick
    - Sort by edge_degree + weight (descending)
    - Icon: 🔗
  Path B — "Global Expansion":
    - From found edges → collect src_id + tgt_id → batch load node data
    - Icon: 🔗

Stage 4: "Round-Robin Merge" — Green (#4caf50)
- Interleave Local and Global results alternately
- Deduplicate by entity_name / src_id+tgt_id
- Apply token truncation (priority: similarity → degree → recency)
- Icon: 🔀

Stage 5: "Context Assembly" — Teal (#009688)
- Combine: Entities + Relationships + Document Chunks
- Format into structured context string
- Icon: 📋

Stage 6: "Answer Generation" — Red (#f44336)
- LLM reads assembled context + user query
- Generates grounded answer using only provided context
- Icon: 💬

=== VISUAL DETAILS ===
- Connect stages with thick arrows showing data flow
- Show the parallel Local/Global paths as two parallel lanes merging at Stage 4
- Add small data count badges: "938 entities", "1,281 relations", "47 chunks"
- Add a small "NetworkX GraphML" database icon between Stage 2 and Stage 3
- Bottom: timeline bar showing "~2-4 seconds total" with relative stage durations
```

---

## 프롬프트 3: 문서 인제스트 파이프라인

```
Create a simple left-to-right pipeline diagram showing the document ingestion process. Use a clean design with soft gradients.

=== PIPELINE ===

Step 1: "Document Upload" — Blue (#42a5f5)
- Supported formats shown as small file icons: .txt, .md, .pdf, .docx, .xlsx, .pptx
- Arrow labeled "6 formats supported"

Step 2: "Format Conversion" — Indigo (#5c6bc0)
- DocumentConverter: converts any format to plain text
- Small label: "PyPDF2, python-docx, openpyxl, python-pptx"

Step 3: "Structured Summarization" — Purple (#ab47bc)
- LLM (Gemini 2.5 Flash) creates structured summary
- Shows summary structure: Title, Overview, Key Topics, Key Entities, Conclusions
- Small label: "Reduces noise before KG ingestion"
- Cache icon: "summary_store.json"

Step 4: "LightRAG Ingestion" — Orange (#ff7043)
- Text chunking (split into ~47 chunks)
- Entity extraction (→ 938 entities, 20 types)
- Relationship extraction (→ 1,281 relations)
- Graph construction (NetworkX GraphML)
- Embedding generation (all-MiniLM-L6-v2, 384d, local)

Step 5: "Knowledge Graph" — Green (#66bb6a)
- Show as a network/graph visualization with interconnected nodes
- Label: "305 nodes, ~1,281 edges"
- Small icons for 3 vector DBs: entities, relationships, chunks

=== STYLE ===
- Horizontal flow with large arrows between steps
- Each step is a rounded card with icon, title, and bullet points
- Subtle gradient background from light blue to light green
- "Before vs After" comparison badge: "Raw docs → Structured KG, noise reduced 20%"
```

---

## 프롬프트 4: 시스템 아키텍처 전체 구성도

```
Create a system architecture overview diagram showing all components of the Agentic AI system. Use an isometric or layered card layout.

=== LAYERS (top to bottom) ===

Layer 1: "Frontend" — Light blue background8
- index.html + app.js + styles.css
- Features: SSE Streaming, Accordion Thinking UI, Source References, Document Upload
- Port: 3000

Layer 2: "API Layer" — White background
- FastAPI + Uvicorn
- Endpoints: /api/chat, /api/chat/stream (SSE), /api/documents, /api/upload, /api/ingest
- Port: 8000
- CORS: allow_origins=["*"]

Layer 3: "Agent Layer" — Orange background
- LangGraph StateGraph
- 7 Nodes: Router, Direct Answer, Actor, Tool Executor, Evaluator, Reflection, Exhaustion Answer
- Show as connected boxes in a mini flow diagram

Layer 4: "Tools Layer" — Purple background
- 8 Tools in a grid:
  Row 1: query_knowledge_graph, web_search, list_documents, get_document_info
  Row 2: get_document_summary, get_document_content, list_document_summaries, get_system_status

Layer 5: "RAG & Storage Layer" — Green background
- Left side: LightRAG (HKUDS/LightRAG)
  - NetworkX GraphML (305 nodes, 1281 edges)
  - 3 Vector DBs (JSON-based): entities(938), relationships(1281), chunks(47)
- Right side: Support modules
  - Document Converter (6 formats)
  - Document Summarizer (LLM-based)
  - Summary Cache
  - Lessons Store (long-term memory)

Layer 6: "LLM Layer" — Dark background
- Left: Gemini 2.5 Flash (Router, Direct Answer, LightRAG internal)
- Right: Gemini 3 Flash Preview (Actor, Evaluator, Reflection)
- Center: all-MiniLM-L6-v2 (Embeddings, 384d, Local)

=== CONNECTIONS ===
- Vertical arrows between layers
- Highlight the SSE streaming path from Frontend ↔ API ↔ Agent with a dashed blue line
- Show bidirectional arrows where applicable (e.g., API ↔ Agent)

=== STYLE ===
- Each layer is a wide horizontal card with rounded corners
- Use consistent color coding per layer
- Add small technology logos where possible (FastAPI, LangGraph, NetworkX, HuggingFace)
- Bottom: "Tech Stack" summary bar listing all key technologies
```

---

## 사용 방법

1. Figma에서 **Figma AI** (또는 **Make Design** 등 AI 플러그인) 열기
2. 위 프롬프트 중 원하는 것을 복사하여 입력
3. 생성된 결과를 기반으로 색상, 레이아웃, 텍스트 미세 조정
4. 프롬프트 1(메인 흐름)을 먼저 만들고, 필요에 따라 2~4번을 서브 다이어그램으로 추가 권장

### 추천 순서
1. **프롬프트 4** (시스템 전체 구성도) → 전체 그림 파악
2. **프롬프트 1** (에이전트 처리 흐름) → 핵심 로직 상세
3. **프롬프트 3** (문서 인제스트) → 데이터 파이프라인
4. **프롬프트 2** (KG 쿼리) → 기술 심화
