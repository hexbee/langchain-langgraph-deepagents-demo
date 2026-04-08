from __future__ import annotations

import argparse
import asyncio

from deepagents import create_deep_agent
from demo_support import build_model, load_project_env, stringify_content
from langchain_core.messages import HumanMessage
from mcp_support import list_mcp_servers, load_mcp_tools


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "DeepAgents demo with OpenAI-compatible configuration from .env "
            "and optional MCP tools from .mcp.json."
        )
    )
    parser.add_argument(
        "prompt",
        nargs="*",
        help="Prompt to send to the agent. If omitted, a default prompt is used.",
    )
    return parser.parse_args()


async def run_agent(prompt: str) -> str:
    agent = create_deep_agent(
        model=build_model(),
        tools=await load_mcp_tools(),
        system_prompt=(
            "You are a concise demo Deep Agent. "
            "Answer directly unless tools are genuinely useful."
        ),
    )
    result = await agent.ainvoke({"messages": [HumanMessage(content=prompt)]})
    return stringify_content(result["messages"][-1].content)


def main() -> int:
    load_project_env()
    args = parse_args()
    prompt = " ".join(args.prompt).strip() or (
        "Briefly describe what kinds of problems DeepAgents is good at solving. "
        "Answer in Simplified Chinese."
    )

    server_names = list_mcp_servers()
    if server_names:
        print(f"MCP servers: {', '.join(server_names)}")

    print(asyncio.run(run_agent(prompt)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
