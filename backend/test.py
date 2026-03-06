import asyncio
from src.rag.lightrag_manager import gemini_llm_func, local_embedding_func, rag

async def main():
    print("Testing LLM...")
    try:
        res = await gemini_llm_func("Hello?")
        print("LLM Success:", res[:50])
    except Exception as e:
        print("LLM Error:", type(e), e)

    print("Testing Embedding...")
    try:
        res = await local_embedding_func(["Hello world"])
        print("Embedding Success shape:", res.shape)
    except Exception as e:
        print("Embedding Error:", type(e), e)

    print("Testing LightRAG ainsert...")
    try:
        await rag.ainsert(["AgentDemo is a test system."])
        print("LightRAG Insert Success")
    except Exception as e:
        print("LightRAG Error:", type(e), e)

if __name__ == "__main__":
    asyncio.run(main())
