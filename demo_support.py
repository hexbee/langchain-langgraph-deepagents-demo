from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model


ROOT_DIR = Path(__file__).resolve().parent
ENV_PATH = ROOT_DIR / ".env"
MCP_CONFIG_PATH = ROOT_DIR / ".mcp.json"


def load_project_env() -> None:
    load_dotenv(dotenv_path=ENV_PATH)


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
                    content_text = item.get("content")
                    if isinstance(content_text, str):
                        parts.append(content_text)
                    else:
                        parts.append(str(item))
            else:
                parts.append(str(item))
        return "\n".join(part for part in parts if part)
    return str(content)


def format_tool_log(message_count: int, message: Any) -> list[str]:
    lines: list[str] = []

    if getattr(message, "tool_calls", None):
        for tool_call in message.tool_calls:
            lines.append(
                f"[tool-log:{message_count}] call {tool_call['name']} args={tool_call['args']}"
            )

    if getattr(message, "type", "") == "tool":
        tool_name = getattr(message, "name", None) or "unknown_tool"
        content = stringify_content(message.content).strip()
        if len(content) > 500:
            content = f"{content[:500]}..."
        lines.append(f"[tool-log:{message_count}] result {tool_name}: {content}")

    return lines


def _unwrap_message_value(value: Any) -> list[Any]:
    if value is None:
        return []
    if hasattr(value, "value"):
        return _unwrap_message_value(value.value)
    if isinstance(value, list):
        return value
    return [value]


def iter_messages_from_update(update_data: Any) -> list[Any]:
    if not isinstance(update_data, dict):
        return []

    messages: list[Any] = []
    for node_update in update_data.values():
        if isinstance(node_update, dict) and "messages" in node_update:
            messages.extend(_unwrap_message_value(node_update["messages"]))
    return messages


class StreamPrinter:
    def __init__(self, show_tool_log: bool = False):
        self.show_tool_log = show_tool_log
        self.answer_parts: list[str] = []
        self.latest_ai_message = ""
        self._answer_line_open = False
        self._printed_text = False
        self._seen_tool_messages: set[tuple[Any, ...]] = set()
        self._message_count = 0

    def emit_text(self, text: str) -> None:
        if not text:
            return
        print(text, end="", flush=True)
        self.answer_parts.append(text)
        self._answer_line_open = True
        self._printed_text = True

    def emit_line(self, line: str) -> None:
        if self._answer_line_open:
            print(flush=True)
            self._answer_line_open = False
        print(line, flush=True)

    def record_message(self, message: Any) -> None:
        content = stringify_content(getattr(message, "content", "")).strip()
        if getattr(message, "type", "") == "ai" and content:
            self.latest_ai_message = content

        if not self.show_tool_log:
            return

        if (
            not getattr(message, "tool_calls", None)
            and getattr(message, "type", "") != "tool"
        ):
            return

        fingerprint = (
            getattr(message, "type", type(message).__name__),
            getattr(message, "id", None),
            getattr(message, "name", None),
            getattr(message, "tool_call_id", None),
            tuple(
                tool_call.get("id")
                for tool_call in (getattr(message, "tool_calls", None) or [])
            ),
            stringify_content(getattr(message, "content", ""))[:200],
        )
        if fingerprint in self._seen_tool_messages:
            return

        self._seen_tool_messages.add(fingerprint)
        self._message_count += 1
        for line in format_tool_log(self._message_count, message):
            self.emit_line(line)

    def handle_stream_chunk(self, chunk: Any) -> None:
        if not isinstance(chunk, dict):
            return

        chunk_type = chunk.get("type")
        if chunk_type == "messages":
            message_chunk, _metadata = chunk["data"]
            self.emit_text(stringify_content(message_chunk.content))
            return

        if chunk_type == "updates":
            for message in iter_messages_from_update(chunk["data"]):
                self.record_message(message)

    def final_text(self) -> str:
        streamed = "".join(self.answer_parts).strip()
        return streamed or self.latest_ai_message

    def finish(self) -> None:
        if self._answer_line_open:
            print(flush=True)
            self._answer_line_open = False

        final_text = self.final_text()
        if final_text and not self._printed_text:
            print(final_text, flush=True)
            self._printed_text = True


async def stream_graph_result(
    runnable: Any,
    payload: dict[str, Any],
    *,
    show_tool_log: bool = False,
    config: dict[str, Any] | None = None,
) -> str:
    printer = StreamPrinter(show_tool_log=show_tool_log)

    async for chunk in runnable.astream(
        payload,
        config=config,
        stream_mode=["messages", "updates"],
        version="v2",
    ):
        printer.handle_stream_chunk(chunk)

    printer.finish()
    return printer.final_text()


async def stream_chat_model_response(model: Any, messages: list[Any]) -> str:
    printer = StreamPrinter(show_tool_log=False)

    async for chunk in model.astream(messages):
        printer.emit_text(stringify_content(chunk.content))

    printer.finish()
    return printer.final_text()
