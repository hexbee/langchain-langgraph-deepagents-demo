from __future__ import annotations

import argparse
import asyncio

from demo_support import (
    build_model,
    format_tool_log,
    load_project_env,
    stringify_content,
)
from langchain.tools import tool
from langchain_core.messages import SystemMessage, ToolMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from mcp_support import list_mcp_servers, load_mcp_tools


@tool
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


@tool
def multiply(a: int, b: int) -> int:
    """Multiply two integers."""
    return a * b


@tool
def divide(a: float, b: float) -> float:
    """Divide a by b."""
    return a / b


async def run_graph(prompt: str):
    model = build_model()
    tools = [add, multiply, divide, *(await load_mcp_tools())]
    tools_by_name = {tool_item.name: tool_item for tool_item in tools}
    model_with_tools = model.bind_tools(tools)

    async def call_model(state: MessagesState):
        response = await model_with_tools.ainvoke(
            [
                SystemMessage(
                    content=(
                        "You are a helpful math assistant. "
                        "Use arithmetic tools for calculations and MCP tools when relevant."
                    )
                ),
                *state["messages"],
            ]
        )
        return {"messages": [response]}

    async def call_tools(state: MessagesState):
        outputs = []
        for tool_call in state["messages"][-1].tool_calls:
            observation = await tools_by_name[tool_call["name"]].ainvoke(
                tool_call["args"]
            )
            outputs.append(
                ToolMessage(
                    content=str(observation),
                    tool_call_id=tool_call["id"],
                    name=tool_call["name"],
                )
            )
        return {"messages": outputs}

    def should_continue(state: MessagesState):
        last_message = state["messages"][-1]
        return "tool_node" if getattr(last_message, "tool_calls", None) else END

    graph = StateGraph(MessagesState)
    graph.add_node("llm_call", call_model)
    graph.add_node("tool_node", call_tools)
    graph.add_edge(START, "llm_call")
    graph.add_conditional_edges("llm_call", should_continue, ["tool_node", END])
    graph.add_edge("tool_node", "llm_call")
    compiled_graph = graph.compile()
    return await compiled_graph.ainvoke(
        {"messages": [{"role": "user", "content": prompt}]}
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "LangGraph demo with OpenAI-compatible configuration from .env "
            "and optional MCP tools from .mcp.json."
        )
    )
    parser.add_argument(
        "prompt",
        nargs="*",
        help="Prompt to send to the graph. If omitted, a default prompt is used.",
    )
    parser.add_argument(
        "--show-tool-log",
        action="store_true",
        help="Print MCP/tool call logs before the final answer.",
    )
    return parser.parse_args()


def main() -> int:
    load_project_env()
    args = parse_args()
    prompt = " ".join(args.prompt).strip() or (
        "Calculate (12 + 8) * 3 and then divide the result by 5."
    )

    server_names = list_mcp_servers()
    if server_names:
        print(f"MCP servers: {', '.join(server_names)}")

    result = asyncio.run(run_graph(prompt))

    if args.show_tool_log:
        for index, message in enumerate(result["messages"], start=1):
            for line in format_tool_log(index, message):
                print(line)

    print(stringify_content(result["messages"][-1].content))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
