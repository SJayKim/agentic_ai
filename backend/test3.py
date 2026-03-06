import asyncio
import traceback
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv

load_dotenv()

async def main():
    print("Testing LLM...", flush=True)
    try:
        llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.1)
        res = await llm.ainvoke([HumanMessage(content="Hello?")])
        print("LLM Success:", res.content[:50], flush=True)
    except Exception as e:
        print("LLM Error:")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
