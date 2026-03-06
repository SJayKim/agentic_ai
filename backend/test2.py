import asyncio
import traceback
from src.rag.lightrag_manager import gemini_llm_func, local_embedding_func, rag

async def main():
    print("Testing LLM...", flush=True)
    try:
        res = await gemini_llm_func("Hello?")
        print("LLM Success:", res[:50], flush=True)
    except Exception as e:
        print("LLM Error:")
        traceback.print_exc()

    print("Testing LightRAG query...", flush=True)
    try:
        res = await rag.aquery("Who is the main developer of AgentDemo?", param=None)
        print("Query Success:", res[:50], flush=True)
    except Exception as e:
        print("Query Error:")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
