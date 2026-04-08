from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, MessagesState, StateGraph


def load_project_env() -> None:
    load_dotenv(dotenv_path=Path(__file__).resolve().with_name(".env"))


def read_env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def require_env(*names: str) -> str:
    value = read_env(*names)
    if value:
        return value
    joined_names = ", ".join(names)
    raise SystemExit(f"Missing environment variable. Set one of: {joined_names}")


def build_model():
    model_name = require_env("OPENAI_MODEL", "OPENAI_MODEL_NAME", "OPENAI_COMPAT_MODEL")
    api_key = require_env("OPENAI_API_KEY", "OPENAI_COMPAT_API_KEY")
    base_url = read_env("OPENAI_BASE_URL", "OPENAI_COMPAT_BASE_URL")

    kwargs: dict[str, Any] = {
        "model": model_name,
        "model_provider": "openai",
        "api_key": api_key,
        "temperature": 0,
        "use_responses_api": False,
    }
    if base_url:
        kwargs["base_url"] = base_url

    return init_chat_model(**kwargs)


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


def stringify_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
                else:
                    parts.append(str(item))
            else:
                parts.append(str(item))
        return "\n".join(part for part in parts if part)
    return str(content)


def build_graph():
    model = build_model()
    tools = [add, multiply, divide]
    tools_by_name = {tool_item.name: tool_item for tool_item in tools}
    model_with_tools = model.bind_tools(tools)

    def call_model(state: MessagesState):
        return {
            "messages": [
                model_with_tools.invoke(
                    [
                        SystemMessage(
                            content=(
                                "You are a helpful math assistant. "
                                "Use the available tools whenever calculation is needed."
                            )
                        ),
                        *state["messages"],
                    ]
                )
            ]
        }

    def call_tools(state: MessagesState):
        outputs = []
        for tool_call in state["messages"][-1].tool_calls:
            observation = tools_by_name[tool_call["name"]].invoke(tool_call["args"])
            outputs.append(
                ToolMessage(content=str(observation), tool_call_id=tool_call["id"])
            )
        return {"messages": outputs}

    def should_continue(state: MessagesState) -> Literal["tool_node", END]:
        last_message = state["messages"][-1]
        return "tool_node" if getattr(last_message, "tool_calls", None) else END

    graph = StateGraph(MessagesState)
    graph.add_node("llm_call", call_model)
    graph.add_node("tool_node", call_tools)
    graph.add_edge(START, "llm_call")
    graph.add_conditional_edges("llm_call", should_continue, ["tool_node", END])
    graph.add_edge("tool_node", "llm_call")
    return graph.compile()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Minimal LangGraph StateGraph demo with OpenAI-compatible configuration from .env."
    )
    parser.add_argument(
        "prompt",
        nargs="*",
        help="Prompt to send to the graph. If omitted, a default prompt is used.",
    )
    return parser.parse_args()


def main() -> int:
    load_project_env()
    args = parse_args()
    prompt = " ".join(args.prompt).strip() or (
        "Calculate (12 + 8) * 3 and then divide the result by 5."
    )

    graph = build_graph()
    result = graph.invoke({"messages": [HumanMessage(content=prompt)]})

    for index, message in enumerate(result["messages"], start=1):
        print(f"[{index}] {message.type}")
        if getattr(message, "tool_calls", None):
            tool_names = ", ".join(tool_call["name"] for tool_call in message.tool_calls)
            print(f"tool_calls: {tool_names}")
        text = stringify_content(message.content)
        if text:
            print(text)
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
