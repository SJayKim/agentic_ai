import asyncio
from src.agent.graph import create_reflexion_agent
from src.tools import get_tools_for_graph, get_tools_map
from src.memory.lessons_store import LessonsStore

async def main():
    import nest_asyncio
    nest_asyncio.apply()
    
    lessons = LessonsStore()
    agent = create_reflexion_agent(
        tools=get_tools_for_graph(),
        tools_map=get_tools_map(),
        lessons_store=lessons
    )
    
    config = {"configurable": {"thread_id": "test_stream_1"}}
    query = "Who is the main developer of AgentDemo?"
    
    print("Starting stream...")
    try:
        async for event in agent.astream(query, config=config, stream_mode="updates"):
            for node, state in event.items():
                print(f"--- Node: {node} ---")
                if "thought" in state:
                    print(f"Thought: {state['thought']}")
                if "action" in state:
                    print(f"Action: {state['action']}")
                if "final_answer" in state:
                    print(f"Final Answer: {state['final_answer']}")
                print("")
    except Exception as e:
        print(f"Error during streaming: {e}")

if __name__ == "__main__":
    asyncio.run(main())
