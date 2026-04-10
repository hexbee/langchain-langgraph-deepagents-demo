from __future__ import annotations

import argparse
import asyncio

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend
from deepagents.backends.filesystem import FilesystemBackend
from demo_support import (
    ROOT_DIR,
    build_model,
    format_tool_log,
    load_project_env,
    stream_graph_result,
    stringify_content,
)
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from mcp_support import list_mcp_servers, load_mcp_tools
from skills_support import LOCAL_SKILLS_DIR, USER_SKILLS_DIR


DEFAULT_THREAD_ID = "deepagents-demo-session"


def build_deepagents_skills_config() -> tuple[
    list[str], FilesystemBackend | CompositeBackend | None
]:
    skill_sources: list[str] = []
    default_backend = FilesystemBackend(root_dir=ROOT_DIR, virtual_mode=True)
    routes = {}

    # In virtual_mode, Deep Agents must read skills via backend-visible virtual paths,
    # not host absolute paths.
    if USER_SKILLS_DIR.is_dir():
        routes["/user-skills/"] = FilesystemBackend(
            root_dir=USER_SKILLS_DIR,
            virtual_mode=True,
        )
        skill_sources.append("/user-skills/")

    if LOCAL_SKILLS_DIR.is_dir():
        skill_sources.append("/.agents/skills/")

    if not skill_sources:
        return [], None

    backend = (
        CompositeBackend(default=default_backend, routes=routes)
        if routes
        else default_backend
    )
    return skill_sources, backend


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
    parser.add_argument(
        "--thread-id",
        default=DEFAULT_THREAD_ID,
        help=(
            "Thread id used for the agent run. Reuse the same value to follow "
            "thread-scoped Deep Agents best practices."
        ),
    )
    return parser.parse_args()


async def run_agent(
    prompt: str,
    *,
    show_tool_log: bool = False,
    stream: bool = True,
    thread_id: str = DEFAULT_THREAD_ID,
) -> str:
    skill_sources, backend = build_deepagents_skills_config()
    config = {"configurable": {"thread_id": thread_id}}
    agent = create_deep_agent(
        model=build_model(),
        tools=await load_mcp_tools(),
        system_prompt=(
            "You are a concise demo Deep Agent. "
            "Answer directly unless tools are genuinely useful."
        ),
        skills=skill_sources or None,
        backend=backend,
        checkpointer=MemorySaver(),
    )

    payload = {"messages": [HumanMessage(content=prompt)]}

    if stream:
        return await stream_graph_result(
            agent,
            payload,
            show_tool_log=show_tool_log,
            config=config,
        )

    result = await agent.ainvoke(payload, config=config)

    if show_tool_log:
        for index, message in enumerate(result["messages"], start=1):
            for line in format_tool_log(index, message):
                print(line)

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

    result = asyncio.run(
        run_agent(
            prompt,
            show_tool_log=args.show_tool_log,
            stream=not args.no_stream,
            thread_id=args.thread_id,
        )
    )
    if args.no_stream:
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
