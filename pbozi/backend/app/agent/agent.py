from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from app.agent.tools import tools_list as static_tools
from langgraph.checkpoint.memory import MemorySaver

# Use an in-memory saver for checkpointing as requested for state management
# We make this global so thread states are preserved across requests
memory = MemorySaver()

def get_agent_executor(
    model_name: str,
    api_key: str,
    base_url: str,
    custom_tools: list = None,
    disabled_tool_names: set[str] | None = None,
    system_prompt: str | None = None,
):
    llm = ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=0.0,
        streaming=True,
        stream_usage=True,
        default_headers={
            "HTTP-Referer": "https://jgpti.local",
            "X-Title": "JGPTi",
        }
    )
    
    disabled_tool_names = disabled_tool_names or set()
    all_tools = [tool for tool in static_tools if getattr(tool, "name", "") not in disabled_tool_names]
    if custom_tools:
        all_tools.extend(custom_tools)
    
    return create_react_agent(
        llm,
        all_tools,
        checkpointer=memory,
        prompt=system_prompt,
    )
