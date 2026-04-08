from __future__ import annotations

import argparse
import asyncio

from demo_support import (
    build_model,
    format_tool_log,
    load_project_env,
    stringify_content,
)
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, SystemMessage
from mcp_support import list_mcp_servers, load_mcp_tools


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "LangChain demo with OpenAI-compatible configuration from .env "
            "and optional MCP tools from .mcp.json."
        )
    )
    parser.add_argument(
        "prompt",
        nargs="*",
        help="Prompt to send to the model. If omitted, a default prompt is used.",
    )
    parser.add_argument(
        "--show-tool-log",
        action="store_true",
        help="Print MCP/tool call logs before the final answer.",
    )
    return parser.parse_args()


async def run_prompt(prompt: str, show_tool_log: bool = False) -> str:
    model = build_model()
    mcp_tools = await load_mcp_tools()

    if mcp_tools:
        agent = create_agent(
            model=model,
            tools=mcp_tools,
            system_prompt=(
                "You are a concise and accurate AI assistant. "
                "Use MCP tools when they help answer the user."
            ),
        )
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": prompt}]}
        )

        if show_tool_log:
            for index, message in enumerate(result["messages"], start=1):
                for line in format_tool_log(index, message):
                    print(line)

        return stringify_content(result["messages"][-1].content)

    response = await model.ainvoke(
        [
            SystemMessage(content="You are a concise and accurate AI assistant."),
            HumanMessage(content=prompt),
        ]
    )
    return stringify_content(response.content)


def main() -> int:
    load_project_env()
    args = parse_args()

    prompt = " ".join(args.prompt).strip() or (
        "Briefly explain the differences between LangChain, LangGraph, and "
        "DeepAgents. Answer in Simplified Chinese."
    )

    server_names = list_mcp_servers()
    if server_names:
        print(f"MCP servers: {', '.join(server_names)}")

    print(asyncio.run(run_prompt(prompt, show_tool_log=args.show_tool_log)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
