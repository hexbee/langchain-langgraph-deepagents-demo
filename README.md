# LangChain / LangGraph / DeepAgents MCP Demo

This repository is a small runnable Python demo that shows how to load the same MCP tool set from `.mcp.json` into:

- `langchain-demo.py`
- `langgraph-demo.py`
- `deepagents-demo.py`

All three scripts now support shared flags:

- `--show-tool-log`
- `--no-stream`

By default, the scripts now stream output token by token when the upstream model supports it, so you can see partial output before the full run ends.

- `--show-tool-log`: print tool call logs so you can verify that MCP tools were actually called, not just connected
- `--no-stream`: disable streaming and wait for the final answer before printing

## Requirements

- Python `>=3.12.10`
- `uv` is recommended
- `npx` is required if you want to use the GitHub MCP server

## Install

```sh
uv sync
```

You can also run the scripts with the Python interpreter from your active virtual environment if you prefer.

To keep the examples cross-platform, the commands below use `uv run python ...`.

```sh
uv run python --version
```

## Configure

Create a `.env` file. You can start from `.env.exmaple`.

Example:

```env
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=sk-your-api-key
OPENAI_MODEL=gpt-4o-mini

CONTEXT7_API_KEY=your-context7-api-key
GITHUB_PERSONAL_ACCESS_TOKEN=your-github-personal-access-token
```

MCP servers are configured in `.mcp.json`. The current demo includes:

- `openaiDeveloperDocs`
- `context7`
- `github`

Notes:

- If a server in `.mcp.json` depends on an env var that is missing, that server's tools are skipped automatically.
- Printing `MCP servers: ...` only means the server names exist in config.
- To confirm real tool execution, use `--show-tool-log`.

## Run

### LangChain

Default run:

```sh
uv run python langchain-demo.py
```

Pass a custom prompt:

```sh
uv run python langchain-demo.py "Briefly explain MCP in Chinese."
```

Show tool logs:

```sh
uv run python langchain-demo.py --show-tool-log "Use an MCP tool from the OpenAI developer docs server to find one OpenAI API endpoint related to models. Briefly answer in Chinese."
```

### LangGraph

Default run:

```sh
uv run python langgraph-demo.py
```

Show tool logs:

```sh
uv run python langgraph-demo.py --show-tool-log "Use an MCP tool from the OpenAI developer docs server to find one OpenAI API endpoint related to models. Briefly answer in Chinese."
```

Disable streaming:

```sh
uv run python langgraph-demo.py --no-stream
```

### DeepAgents

Default run:

```sh
uv run python deepagents-demo.py
```

Show tool logs:

```sh
uv run python deepagents-demo.py --show-tool-log "Use an MCP tool from the OpenAI developer docs server to find one OpenAI API endpoint related to models. Briefly answer in Chinese."
```

Disable streaming:

```sh
uv run python deepagents-demo.py --no-stream
```

## How To Verify MCP Was Really Used

With `--show-tool-log`, real tool usage looks like this:

```text
[tool-log:2] call openaiDeveloperDocs_list_api_endpoints args={}
[tool-log:3] result openaiDeveloperDocs_list_api_endpoints: ...
```

Meaning:

- `call ...` means the model requested a tool.
- `result ...` means the program executed that tool and returned its result.

If you only see the final answer and no tool logs, one of these is likely true:

- The prompt did not require tools.
- The MCP tools were not loaded successfully.
- The upstream model API hit rate limits, cooldown, or timeout.

## Script Differences

`langchain-demo.py`

- Uses `create_agent(...)`
- Best for the simplest agent + tools example

`langgraph-demo.py`

- Uses `StateGraph`
- Explicitly implements the `LLM -> tools -> LLM` loop
- Best for observing tool execution flow

`deepagents-demo.py`

- Uses `create_deep_agent(...)`
- Smallest example for DeepAgents integration

## Streaming Notes

- `langchain-demo.py` streams with `agent.astream(...)` when MCP tools are loaded, and with `model.astream(...)` otherwise
- `langgraph-demo.py` and `deepagents-demo.py` use `astream(..., stream_mode=["messages", "updates"], version="v2")`
- `stream_mode="messages"` is what lets the terminal print partial LLM output as tokens arrive
- `stream_mode="updates"` is used to keep `--show-tool-log` working during streaming
- If an upstream model provider does not emit token chunks, the scripts fall back to printing the final answer at the end

## Important Files

- `demo_support.py`: shared model setup, env loading, tool log formatting
- `mcp_support.py`: loads MCP config and converts MCP tools into LangChain tools
- `.mcp.json`: MCP server config
- `.env.exmaple`: env var example

## FAQ

### Why does the default prompt often look like it did not use MCP?

Because "tools are registered" is not the same as "the model must call a tool". The default prompts are often simple explanation tasks, so the model may answer directly.

### Why do I see `MCP servers: ...` but still no tool calls?

Because `list_mcp_servers()` only lists configured server names. Actual tool loading happens later and may skip servers with unresolved env vars.

### Why do I sometimes get `429` or cooldown errors?

That is usually an upstream model provider limitation, not an MCP integration problem. Retry later, switch models, or reduce request frequency.
