from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from demo_support import MCP_CONFIG_PATH


_BRACED_VAR_RE = re.compile(r"\$\{([^}]+)\}")


def _expand_env_vars(value: str) -> str:
    return _BRACED_VAR_RE.sub(
        lambda match: os.environ.get(match.group(1), match.group(0)), value
    )


def _resolve_value(value: Any) -> Any:
    if isinstance(value, str):
        return _expand_env_vars(value)
    if isinstance(value, list):
        return [_resolve_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _resolve_value(item) for key, item in value.items()}
    return value


def _has_unresolved_placeholders(value: Any) -> bool:
    if isinstance(value, str):
        return bool(_BRACED_VAR_RE.search(value))
    if isinstance(value, list):
        return any(_has_unresolved_placeholders(item) for item in value)
    if isinstance(value, dict):
        return any(_has_unresolved_placeholders(item) for item in value.values())
    return False


def _normalize_transport(raw_transport: str) -> str:
    lowered = raw_transport.strip().lower().replace("-", "_")
    if lowered in {"http", "streamable_http"}:
        return "http"
    if lowered in {"stdio", "sse", "websocket"}:
        return lowered
    if lowered == "ws":
        return "websocket"
    raise ValueError(f"Unsupported MCP server transport/type: {raw_transport}")


def load_mcp_connections(config_path: Path | None = None) -> dict[str, dict[str, Any]]:
    resolved_path = config_path or MCP_CONFIG_PATH
    if not resolved_path.exists():
        return {}

    payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    raw_servers = payload.get("mcpServers", {})
    connections: dict[str, dict[str, Any]] = {}

    for server_name, raw_config in raw_servers.items():
        raw_transport = raw_config.get("transport") or raw_config.get("type")
        if not raw_transport:
            raise ValueError(
                f"MCP server '{server_name}' is missing 'type' or 'transport'."
            )

        transport = _normalize_transport(str(raw_transport))
        connection: dict[str, Any] = {"transport": transport}

        for key in ("url", "command", "args", "env", "headers", "cwd"):
            if key in raw_config:
                connection[key] = _resolve_value(raw_config[key])

        if transport == "stdio":
            connection.setdefault("args", [])

        connections[server_name] = connection

    return connections


def list_mcp_servers(config_path: Path | None = None) -> list[str]:
    return list(load_mcp_connections(config_path))


async def load_mcp_tools(config_path: Path | None = None) -> list[BaseTool]:
    connections = {
        name: connection
        for name, connection in load_mcp_connections(config_path).items()
        if not _has_unresolved_placeholders(connection)
    }
    if not connections:
        return []

    client = MultiServerMCPClient(connections, tool_name_prefix=True)
    return await client.get_tools()
