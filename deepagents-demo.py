from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend
from deepagents.backends.filesystem import FilesystemBackend
from deepagents.backends.local_shell import LocalShellBackend
from demo_support import (
    ROOT_DIR,
    StreamPrinter,
    build_model,
    format_tool_log,
    load_project_env,
    stream_graph_result,
    stringify_content,
)
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command, Interrupt
from mcp_support import list_mcp_servers, load_mcp_tools
from skills_support import LOCAL_SKILLS_DIR, USER_SKILLS_DIR


DEFAULT_THREAD_ID = "deepagents-demo-session"
PROJECT_SKILLS_VIRTUAL_PATH = "/.agents/skills/"
USER_SKILLS_VIRTUAL_PATH = "/user-skills/"

DeepAgentsBackend = FilesystemBackend | LocalShellBackend | CompositeBackend
DeepAgentsBackendFactory = Callable[[Any], DeepAgentsBackend]
ConfiguredDeepAgentsBackend = DeepAgentsBackend | DeepAgentsBackendFactory


@dataclass(frozen=True)
class DeepAgentsRuntimeConfig:
    skill_sources: tuple[str, ...]
    backend: ConfiguredDeepAgentsBackend | None


def _build_shell_backend() -> LocalShellBackend:
    return LocalShellBackend(
        root_dir=ROOT_DIR,
        virtual_mode=True,
        inherit_env=True,
    )


def _build_default_backend(*, allow_shell: bool) -> ConfiguredDeepAgentsBackend | None:
    if allow_shell:
        return _build_shell_backend()
    return None


def _build_skill_sources_and_routes() -> tuple[list[str], dict[str, FilesystemBackend]]:
    skill_sources: list[str] = []
    routes: dict[str, FilesystemBackend] = {}

    # In virtual_mode, Deep Agents must read skills via backend-visible virtual paths,
    # not host absolute paths.
    if USER_SKILLS_DIR.is_dir():
        routes[USER_SKILLS_VIRTUAL_PATH] = FilesystemBackend(
            root_dir=USER_SKILLS_DIR,
            virtual_mode=True,
        )
        skill_sources.append(USER_SKILLS_VIRTUAL_PATH)

    if LOCAL_SKILLS_DIR.is_dir():
        routes[PROJECT_SKILLS_VIRTUAL_PATH] = FilesystemBackend(
            root_dir=LOCAL_SKILLS_DIR,
            virtual_mode=True,
        )
        skill_sources.append(PROJECT_SKILLS_VIRTUAL_PATH)

    return skill_sources, routes


def build_deepagents_runtime_config(*, allow_shell: bool) -> DeepAgentsRuntimeConfig:
    skill_sources, routes = _build_skill_sources_and_routes()
    default_backend = _build_default_backend(allow_shell=allow_shell)

    if not skill_sources:
        return DeepAgentsRuntimeConfig(skill_sources=(), backend=default_backend)

    if allow_shell:
        backend: ConfiguredDeepAgentsBackend = CompositeBackend(
            default=_build_shell_backend(),
            routes=routes,
        )
    else:
        # Keep the main workspace thread-scoped by default. Only the skills
        # directories are mounted from the host filesystem.
        def backend(runtime: Any) -> DeepAgentsBackend:
            _ = runtime
            return CompositeBackend(default=StateBackend(), routes=routes)

    return DeepAgentsRuntimeConfig(skill_sources=tuple(skill_sources), backend=backend)


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
    parser.add_argument(
        "--allow-shell",
        action="store_true",
        help=(
            "Enable Deep Agents execute support via LocalShellBackend. "
            "This also switches the main workspace from thread-scoped storage "
            "to the real local project directory."
        ),
    )
    parser.add_argument(
        "--interrupt-on-execute",
        action="store_true",
        help=(
            "Require approval before Deep Agents executes shell commands. "
            "Only valid together with --allow-shell."
        ),
    )
    return parser.parse_args()


def _prompt_choice(prompt: str, allowed: set[str]) -> str:
    while True:
        choice = input(prompt).strip().lower()
        if choice in allowed:
            return choice
        print(f"Please enter one of: {', '.join(sorted(allowed))}")


def _prompt_edit_action(action_request: dict[str, Any]) -> dict[str, Any]:
    current_name = action_request["name"]
    current_args = action_request["args"]

    print("Edit requested action. Press Enter to keep the current value.")
    new_name = input(f"Tool name [{current_name}]: ").strip() or current_name
    print("Current args:")
    print(json.dumps(current_args, ensure_ascii=False, indent=2))
    new_args_text = input("Args JSON [keep current]: ").strip()
    if not new_args_text:
        new_args = current_args
    else:
        try:
            new_args = json.loads(new_args_text)
        except json.JSONDecodeError as exc:
            print(f"Invalid JSON: {exc}")
            return _prompt_edit_action(action_request)
        if not isinstance(new_args, dict):
            print("Args JSON must decode to an object.")
            return _prompt_edit_action(action_request)

    return {
        "type": "edit",
        "edited_action": {
            "name": new_name,
            "args": new_args,
        },
    }


def _prompt_hitl_request(interrupt: Interrupt) -> dict[str, Any]:
    value = interrupt.value
    action_requests = (
        value.get("action_requests", []) if isinstance(value, dict) else []
    )
    review_configs = value.get("review_configs", []) if isinstance(value, dict) else []

    if not action_requests or not review_configs:
        print(
            "Paused execution requires input, but no tool approval details were provided."
        )
        raw_value = input("Resume value (JSON or plain text): ").strip()
        if not raw_value:
            return ""
        try:
            return json.loads(raw_value)
        except json.JSONDecodeError:
            return raw_value

    decisions: list[dict[str, Any]] = []
    print("\nApproval required before tool execution.\n")

    for index, action_request in enumerate(action_requests, start=1):
        review_config = review_configs[index - 1]
        tool_name = action_request["name"]
        tool_args = action_request["args"]
        description = action_request.get("description", "")
        allowed_decisions = set(review_config.get("allowed_decisions", []))

        print(f"[approval:{index}] Tool: {tool_name}")
        if description:
            print(description)
        print("Args:")
        print(json.dumps(tool_args, ensure_ascii=False, indent=2))

        options: list[str] = []
        if "approve" in allowed_decisions:
            options.append("a=approve")
        if "edit" in allowed_decisions:
            options.append("e=edit")
        if "reject" in allowed_decisions:
            options.append("r=reject")
        print(f"Allowed decisions: {', '.join(options)}")

        choice = _prompt_choice(
            "Decision: ",
            {
                key
                for key, decision in (
                    ("a", "approve"),
                    ("e", "edit"),
                    ("r", "reject"),
                )
                if decision in allowed_decisions
            },
        )

        if choice == "a":
            decisions.append({"type": "approve"})
            continue
        if choice == "e":
            decisions.append(_prompt_edit_action(action_request))
            continue

        message = input("Rejection message [optional]: ").strip()
        decision: dict[str, Any] = {"type": "reject"}
        if message:
            decision["message"] = message
        decisions.append(decision)

    return {"decisions": decisions}


async def _resume_from_interrupts(agent: Any, config: dict[str, Any]) -> Command | None:
    state = await agent.aget_state(config)
    if not state.interrupts:
        return None

    resume_map = {
        interrupt.id: _prompt_hitl_request(interrupt) for interrupt in state.interrupts
    }
    return Command(resume=resume_map)


async def run_agent(
    prompt: str,
    *,
    show_tool_log: bool = False,
    stream: bool = True,
    thread_id: str = DEFAULT_THREAD_ID,
    allow_shell: bool = False,
    interrupt_on_execute: bool = False,
) -> str:
    runtime_config = build_deepagents_runtime_config(allow_shell=allow_shell)
    config = {"configurable": {"thread_id": thread_id}}
    agent = create_deep_agent(
        model=build_model(),
        tools=await load_mcp_tools(),
        system_prompt=(
            "You are a concise demo Deep Agent. "
            "Answer directly unless tools are genuinely useful. "
            "Treat files under /.agents/skills/ and /user-skills/ as read-only "
            "reference material unless the user explicitly asks to modify a skill."
        ),
        skills=runtime_config.skill_sources or None,
        backend=runtime_config.backend,
        checkpointer=MemorySaver(),
        interrupt_on={"execute": True} if interrupt_on_execute else None,
    )

    payload: Any = {"messages": [HumanMessage(content=prompt)]}
    printer = StreamPrinter(show_tool_log=show_tool_log) if stream else None

    while True:
        if stream:
            final_text = await stream_graph_result(
                agent,
                payload,
                show_tool_log=show_tool_log,
                config=config,
                printer=printer,
            )
        else:
            result = await agent.ainvoke(payload, config=config)

            if show_tool_log:
                for index, message in enumerate(result["messages"], start=1):
                    for line in format_tool_log(index, message):
                        print(line)

            final_text = stringify_content(result["messages"][-1].content)

        resume_command = await _resume_from_interrupts(agent, config)
        if resume_command is None:
            return final_text

        payload = resume_command


def main() -> int:
    load_project_env()
    args = parse_args()
    if args.interrupt_on_execute and not args.allow_shell:
        raise SystemExit("--interrupt-on-execute requires --allow-shell")
    prompt = " ".join(args.prompt).strip() or (
        "Briefly describe what kinds of problems DeepAgents is good at solving. "
        "Answer in Simplified Chinese."
    )

    server_names = list_mcp_servers()
    if server_names:
        print(f"MCP servers: {', '.join(server_names)}")
    if not args.allow_shell:
        print(
            "Default Deep Agents workspace: thread-scoped temporary storage. "
            "Only configured skill directories are mounted from disk."
        )
    if args.allow_shell:
        print(
            "Shell access enabled: Deep Agents can execute unrestricted local "
            "commands and use the real local project directory as its workspace."
        )
    if args.interrupt_on_execute:
        print("Execute approval enabled: shell commands will pause for approval.")

    result = asyncio.run(
        run_agent(
            prompt,
            show_tool_log=args.show_tool_log,
            stream=not args.no_stream,
            thread_id=args.thread_id,
            allow_shell=args.allow_shell,
            interrupt_on_execute=args.interrupt_on_execute,
        )
    )
    if args.no_stream:
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
