from __future__ import annotations

import argparse
import asyncio

from demo_support import (
    build_model,
    format_tool_log,
    load_project_env,
    stream_graph_result,
    stringify_content,
)
from langchain_core.messages import SystemMessage
from langchain.tools import tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from mcp_support import list_mcp_servers, load_mcp_tools
from skills_support import append_prompt_text, build_skill_runtime


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


async def run_graph(
    prompt: str,
    *,
    show_tool_log: bool = False,
    stream: bool = True,
):
    model = build_model()
    skill_runtime = build_skill_runtime()
    tools = [add, multiply, divide, *(await load_mcp_tools())]
    tools.extend(skill_runtime.skill_tools)
    model_with_tools = model.bind_tools(tools)
    system_prompt = append_prompt_text(
        (
            "You are a concise demo assistant. "
            "Use arithmetic tools for calculations, MCP tools for external information, "
            "and skill tools when a relevant skill applies."
        ),
        skill_runtime.skills_prompt,
    )

    async def call_model(state: MessagesState):
        response = await model_with_tools.ainvoke(
            [
                SystemMessage(content=system_prompt),
                *state["messages"],
            ]
        )
        return {"messages": [response]}

    def should_continue(state: MessagesState):
        last_message = state["messages"][-1]
        return "tool_node" if getattr(last_message, "tool_calls", None) else END

    tool_node = ToolNode(tools, handle_tool_errors=True)
    graph = StateGraph(MessagesState)
    graph.add_node("llm_call", call_model)
    graph.add_node("tool_node", tool_node)
    graph.add_edge(START, "llm_call")
    graph.add_conditional_edges("llm_call", should_continue, ["tool_node", END])
    graph.add_edge("tool_node", "llm_call")
    compiled_graph = graph.compile()
    payload = {"messages": [{"role": "user", "content": prompt}]}

    if stream:
        return await stream_graph_result(
            compiled_graph,
            payload,
            show_tool_log=show_tool_log,
        )

    return await compiled_graph.ainvoke(payload)


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
    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="Disable streaming and wait for the full final answer before printing.",
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

    result = asyncio.run(
        run_graph(
            prompt,
            show_tool_log=args.show_tool_log,
            stream=not args.no_stream,
        )
    )

    if args.no_stream:
        if args.show_tool_log:
            for index, message in enumerate(result["messages"], start=1):
                for line in format_tool_log(index, message):
                    print(line)

        print(stringify_content(result["messages"][-1].content))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
