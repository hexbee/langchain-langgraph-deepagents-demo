# LangChain / LangGraph / DeepAgents MCP Demo

This repository is a small runnable Python demo that shows how to load the same MCP tool set from `.mcp.json` into:

- `langchain-demo.py`
- `langgraph-demo.py`
- `deepagents-demo.py`

It now also supports shared agent skills loaded from:

- `~/.agents/skills/`
- `./.agents/skills/`

If the same skill name exists in both places, the project-local skill wins.

All three scripts now support shared flags:

- `--show-tool-log`
- `--no-stream`

By default, the scripts now stream output token by token when the upstream model supports it, so you can see partial output before the full run ends.

- `--show-tool-log`: print tool call logs so you can verify that MCP tools were actually called, not just connected
- `--no-stream`: disable streaming and wait for the final answer before printing

`deepagents-demo.py` also supports:

- `--allow-shell`: enable Deep Agents `execute` tool via `LocalShellBackend`
- `--interrupt-on-execute`: require approval before the `execute` tool runs, must be used with `--allow-shell`

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

## Agent Skills

All three demos can now discover agent skills from:

- `~/.agents/skills/`
- `./.agents/skills/`

Expected layout:

```text
.agents/skills/
  my-skill/
    SKILL.md
```

`SKILL.md` should follow the common agent-skills style with YAML frontmatter:

```md
---
name: my-skill
description: What the skill does and when to use it
---

# My Skill
...
```

Resolution order:

- User-level skills are loaded first from `~/.agents/skills/`
- Project-level skills are loaded second from `./.agents/skills/`
- If names collide, the project-level skill overrides the user-level one

Framework behavior:

- `deepagents-demo.py` uses DeepAgents native `skills=[...]` support
- `langchain-demo.py` injects discovered skill metadata into the system prompt and exposes `load_skill` plus `load_skill_resource`
- `langgraph-demo.py` adds the same progressive-disclosure tools to its graph-based tool loop

Notes:

- `LangChain` and `LangGraph` now follow a 3-layer progressive disclosure model: metadata in prompt, `SKILL.md` via `load_skill`, supporting files via `load_skill_resource`
- `DeepAgents` uses backend-visible virtual skill paths, so it can read project skills from `/.agents/skills/` and optional user skills from `/user-skills/` without relying on host absolute paths
- In `DeepAgents`, the second and third disclosure layers show up as native file reads such as `read_file .../SKILL.md` and then `read_file .../visual-companion.md`
- `deepagents-demo.py` also passes a thread id plus an in-memory checkpointer so the example follows the normal Deep Agents invocation pattern for thread-scoped state

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

Use a skill:

```sh
uv run python langchain-demo.py --show-tool-log "If there is a relevant agent skill for this task, use it before answering: help me design a new feature rollout plan."
```

Verify progressive disclosure:

```sh
uv run python langchain-demo.py --no-stream --show-tool-log "Use the brainstorming skill. First call load_skill for brainstorming, then load the referenced file visual-companion.md with load_skill_resource, and finally summarize in Simplified Chinese when the browser-based visual companion should be offered."
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

Use a skill:

```sh
uv run python langgraph-demo.py --show-tool-log "If a relevant skill exists, load it and then explain how to brainstorm a scoped implementation plan."
```

Verify progressive disclosure:

```sh
uv run python langgraph-demo.py --no-stream --show-tool-log "Use the brainstorming skill. First call load_skill for brainstorming, then load the referenced file visual-companion.md with load_skill_resource, and finally summarize in Simplified Chinese when the browser-based visual companion should be offered."
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

Use a skill:

```sh
uv run python deepagents-demo.py --show-tool-log "If a relevant agent skill exists, use it to help me structure a design before implementation."
```

Verify progressive disclosure:

```sh
uv run python deepagents-demo.py --no-stream --show-tool-log "Use the brainstorming skill and follow its progressive-disclosure workflow. If you need the detailed instructions, consult the skill and then any specifically referenced file such as visual-companion.md before summarizing in Simplified Chinese when the browser-based visual companion should be offered."
```

Disable streaming:

```sh
uv run python deepagents-demo.py --no-stream
```

Reuse a specific thread id:

```sh
uv run python deepagents-demo.py --thread-id demo-session-1
```

Enable local shell execution:

```sh
uv run python deepagents-demo.py --allow-shell --show-tool-log "Use execute to run `python --version`, then answer in Simplified Chinese."
```

Enable local shell execution with approval before each command:

```sh
uv run python deepagents-demo.py --allow-shell --interrupt-on-execute --show-tool-log "Use execute to run `python --version`, then answer in Simplified Chinese."
```

Important:

- `--allow-shell` uses Deep Agents `LocalShellBackend`
- This enables unrestricted shell execution on your local machine
- It is disabled by default and should only be used in trusted local workflows
- `--interrupt-on-execute` adds Deep Agents `interrupt_on={"execute": True}` so shell commands pause for approval before execution
- When paused, the CLI will prompt in the terminal for `approve`, `edit`, or `reject`, then resume the run automatically

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
- Loads reusable skills with metadata injection plus `load_skill` and `load_skill_resource`
- Best for the simplest agent + tools example

`langgraph-demo.py`

- Uses `StateGraph`
- Explicitly implements the `LLM -> tools -> LLM` loop
- Uses LangGraph `ToolNode(..., handle_tool_errors=True)` so tool failures can be surfaced back to the model in the standard graph pattern
- Reuses the same progressive-disclosure skill tools as the LangChain demo
- Best for observing tool execution flow

`deepagents-demo.py`

- Uses `create_deep_agent(...)`
- Uses DeepAgents native skills support with a virtual filesystem backend
- Can opt into the `execute` tool with `--allow-shell`, which switches the default backend to `LocalShellBackend`
- Can require approval before shell execution with `--interrupt-on-execute`
- Passes a thread id and in-memory checkpointer so the demo follows the thread-scoped Deep Agents calling pattern
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
- `skills_support.py`: shared skill discovery, metadata injection, `load_skill`, and `load_skill_resource`
- `.mcp.json`: MCP server config
- `.env.exmaple`: env var example

## FAQ

### Why does the default prompt often look like it did not use MCP?

Because "tools are registered" is not the same as "the model must call a tool". The default prompts are often simple explanation tasks, so the model may answer directly.

### Why do I see `MCP servers: ...` but still no tool calls?

Because `list_mcp_servers()` only lists configured server names. Actual tool loading happens later and may skip servers with unresolved env vars.

### Why do I sometimes get `429` or cooldown errors?

That is usually an upstream model provider limitation, not an MCP integration problem. Retry later, switch models, or reduce request frequency.
