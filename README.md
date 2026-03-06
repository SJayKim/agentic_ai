# Agent Demo (LightRAG + LangGraph)

This is a demonstration project that integrates the ReAct + Reflexion Agent architecture with LightRAG to create a powerful Knowledge Graph based assistant.

## Features
- **Intent Router**: Automatically differentiates between casual chat and queries that require searching the knowledge graph.
- **LightRAG Knowledge Graph**: Ingests your documents and creates an efficient graph representation.
- **Agent Reflection**: If the RAG query fails or the tool usage errors out, the agent reflects, stores a lesson in its memory, and retries.
- **Modern Web UI**: A beautiful Vanilla JS/CSS frontend to interact with the API and ingest documents.

## Project Structure
```text
agent_demo/
├── backend/
│   ├── main.py                # FastAPI Server Entry Point
│   ├── config/                # Configuration (settings.yaml)
│   ├── prompts/               # Prompt templates for the Agent nodes
│   ├── requirements.txt
│   └── src/
│       ├── agent/             # Router, Graph, Nodes, and State
│       ├── llm/               # LangChain Model setup
│       ├── memory/            # Long-term Lessons Store
│       ├── rag/               # LightRAG Manager
│       └── tools/             # Tools exposed to the Agent (LightRAG Query)
├── frontend/
│   ├── index.html
│   ├── styles.css
│   └── app.js
└── data/
    ├── documents/             # Drop your .txt or .md files here
    ├── rag_storage/           # LightRAG internal graph data (auto-generated)
    └── lessons.json           # Agent's reflection memory
```

## Setup Instructions

1. **Install Dependencies**
   ```bash
   cd backend
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure API Keys**
   Ensure your `.env` file exists in `backend/` and contains the necessary keys:
   ```bash
   OPENAI_API_KEY=your_key_here
   GOOGLE_API_KEY=your_key_here
   ```
   *Note: LightRAG uses OpenAI models by default (`gpt-4o-mini-complete`, `openai_embedding`). The agent itself might use Gemini based on your `settings.yaml`.*

3. **Run the Backend API Server**
   ```bash
   cd backend
   source .venv/bin/activate
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

4. **Launch the Frontend**
   Simply open `frontend/index.html` in your web browser or use a quick static file server.
   ```bash
   cd frontend
   python3 -m http.server 3000
   ```
   Open `http://localhost:3000` in your browser.

5. **Test Document Ingestion**
   - Place a text file in `data/documents/`.
   - Click "Refresh" in the sidebar to see the file.
   - Click "Ingest Graph" to process it into LightRAG.
   - Ask the Agent questions about your document!
