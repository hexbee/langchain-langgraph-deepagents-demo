from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Minimal LangChain chat demo with OpenAI-compatible configuration from .env."
    )
    parser.add_argument(
        "prompt",
        nargs="*",
        help="Prompt to send to the model. If omitted, a default prompt is used.",
    )
    return parser.parse_args()


def main() -> int:
    load_project_env()
    args = parse_args()

    prompt = " ".join(args.prompt).strip() or (
        "Briefly explain the differences between LangChain, LangGraph, and "
        "DeepAgents. Answer in Simplified Chinese."
    )
    model = build_model()

    response = model.invoke(
        [
            SystemMessage(content="You are a concise and accurate AI assistant."),
            HumanMessage(content=prompt),
        ]
    )

    print(stringify_content(response.content))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
