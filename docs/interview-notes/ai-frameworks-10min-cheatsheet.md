# LangChain / LangGraph / DeepAgents 10 分钟面试 Cheat Sheet

## 1. 开场 30 秒

如果面试官问：“你怎么理解 LangChain、LangGraph、DeepAgents？”

直接答：

> 我会把它们理解成三层。  
> LangChain 是高层 agent 开发框架，适合快速做单 agent 应用；  
> LangGraph 是底层状态图 runtime，适合复杂流程、持久化执行和人工介入；  
> DeepAgents 是面向复杂任务执行的高层 harness，适合 planning、workspace 和 subagent delegation。  
> 我一般按复杂度选型：简单场景 LangChain，复杂流程 LangGraph，复杂任务执行 DeepAgents。

---

## 2. 先讲清依赖关系 1 分钟

### 2.1 一定要先区分两种依赖

- 包依赖：安装时谁依赖谁
- 架构依赖：设计上谁建立在谁之上

### 2.2 当前项目里的真实包依赖

当前环境版本：

- `langchain==1.2.15`
- `langgraph==1.1.6`
- `deepagents==0.5.1`

可以这样记：

```text
deepagents -> langchain -> langgraph -> langchain-core
langchain-openai -> langchain-core
langchain-mcp-adapters -> langchain-core + mcp
```

最重要的结论：

- 当前版本下，`LangChain` 包依赖 `LangGraph`
- 但“用 LangChain”不代表你必须自己手写 `StateGraph`
- `LangGraph` 不依赖顶层 `LangChain`，但依赖 `langchain-core`
- `DeepAgents` 建在 `LangChain` 之上，底层最终还是到 `LangGraph`

### 2.3 最容易被问的那句

如果被问：“单独使用 LangChain 的时候依赖 LangGraph 吗？”

标准回答：

> 在我当前这个版本里，包依赖上是依赖的；但使用心智上不代表我一定要直接写 LangGraph，我可以只用 LangChain 的高层 API，比如 `create_agent(...)`。

---

## 3. LangChain 2 分钟

### 3.1 一句话定位

> LangChain 是一个高层 LLM 应用开发框架，核心价值是把 model、message、tool、agent、structured output、streaming 这些能力统一到一套 API 里。

### 3.2 它解决什么问题

- 统一不同模型提供商接入方式
- 统一 messages / tools / agents / output schema
- 降低从 demo 到 PoC 的开发成本

### 3.3 它最适合什么

- 快速搭单 agent 应用
- 工具调用不太复杂的场景
- 希望更快验证业务想法

### 3.4 你要会说的关键词

- `create_agent(...)`
- messages
- tools
- structured output
- middleware
- streaming
- memory / store / checkpointer

### 3.5 它的边界

> LangChain 强在开发效率，不强在复杂控制流。一旦流程里需要显式状态机、复杂路由、恢复执行，我会下沉到 LangGraph。

---

## 4. LangGraph 2.5 分钟

### 4.1 一句话定位

> LangGraph 是一个面向长生命周期、有状态 AI 工作流的底层编排 runtime，本质上是把 agent 建模成 state、node、edge 构成的状态图。

### 4.2 它解决什么问题

- 把复杂流程从黑盒 agent loop 变成显式状态机
- 支持条件路由、循环、持久化执行
- 支持人工审批、中断恢复、调试回放

### 4.3 你要会说的核心抽象

- `State`
- `Node`
- `Edge`
- `START / END`
- `StateGraph`
- `compile()`
- `checkpoint`
- `interrupt`
- `time travel`

### 4.4 面试里最好的一句话

> LangGraph 的核心价值不是“画流程图”，而是让 agent 运行过程变得可控制、可恢复、可审计。

### 4.5 它适合什么

- 多阶段复杂流程
- 明确状态依赖
- 条件分支、循环、重试
- 需要人工审批
- 需要持久化和恢复执行

### 4.6 它的代价

> LangGraph 控制力更强，但学习成本和开发成本也更高，因为你要自己设计状态和流程。

---

## 5. DeepAgents 2 分钟

### 5.1 一句话定位

> DeepAgents 是一个面向复杂任务执行的高层 agent harness，默认提供 planning、workspace、subagent delegation 和上下文压缩能力。

### 5.2 它解决什么问题

- 复杂任务里主 agent 上下文容易膨胀
- 多步骤任务需要规划和进度跟踪
- 子任务需要委派给更专门的 agent

### 5.3 你要会说的关键词

- `create_deep_agent(...)`
- `write_todos`
- filesystem workspace
- `task` / subagents
- summarization
- long-running task execution

### 5.4 它最值得讲的点

> Subagent 的价值不只是并行，而是上下文隔离。主代理负责协调，子代理在自己的上下文里解决细节问题，最后只把结果摘要返回。

### 5.5 它适合什么

- 复杂、多步骤、长任务
- 中间材料很多
- 需要拆子任务
- 需要在工作区产出文件

### 5.6 它的边界

> DeepAgents 很强，但也更重。简单问答或轻量工具调用时，通常没必要上它。

---

## 6. 三者怎么选 1 分钟

最推荐直接背这段：

> 我一般按复杂度选型。  
> 如果只是简单问答或普通工具调用，我用 LangChain；  
> 如果需要显式状态、条件路由、checkpoint、interrupt，我用 LangGraph；  
> 如果问题天然是复杂任务执行，需要 planning、workspace 和 subagent delegation，我会优先考虑 DeepAgents。

再补一句更显工程感：

> 这三者不是竞争关系，而是分层关系。

---

## 7. 结合你项目怎么讲 1 分钟

当前仓库里：

- `langchain-demo.py`
  - 体现的是 `create_agent + MCP tools + streaming`
- `langgraph-demo.py`
  - 体现的是 `StateGraph + conditional edges + 显式 LLM -> tools -> LLM 循环`
- `deepagents-demo.py`
  - 体现的是 `create_deep_agent + MCP tools`

你可以这样总结项目：

> 我这个项目其实就是在对比三种抽象层。LangChain 负责最轻量的 agent 层，LangGraph 负责显式工作流和运行时控制，DeepAgents 负责复杂任务执行入口。

---

## 8. 高频追问速答

### 为什么不用原生模型 SDK？

> 因为真实应用不只是一句 prompt，还要处理 tools、messages、streaming、structured output、memory 和 observability，这时候框架能明显降低整合成本。

### 为什么有 LangChain 还要 LangGraph？

> 因为 LangChain 开发快，但复杂流程需要显式状态机和持久化执行，LangGraph 在这方面更强。

### 为什么有 LangGraph 还要 DeepAgents？

> 因为 LangGraph 给的是底层控制力，DeepAgents 则把 planning、workspace、delegation 这些复杂任务最佳实践直接打包好了。

### DeepAgents 底层是不是还是 LangGraph？

> 是。当前版本里 `create_deep_agent(...)` 最终返回的是 `CompiledStateGraph`。

### 什么时候不建议上 DeepAgents？

> 简单问答、轻量工具调用、没有任务分解需求时，DeepAgents 通常过重。

---

## 9. 30 秒收尾模板

最后收尾可以这样说：

> 如果让我总结，这三者分别代表三种层级。LangChain 提供高层 agent 开发效率，LangGraph 提供底层流程控制能力，DeepAgents 提供复杂任务执行的默认架构。  
> 我不会混着无差别使用，而是按问题复杂度选型。

---

## 10. 真正上场前最后看一眼的版本

```text
LangChain:
- 高层 agent 框架
- 快速原型
- model/message/tool/agent 统一抽象

LangGraph:
- 底层状态图 runtime
- state/node/edge
- checkpoint / interrupt / time travel

DeepAgents:
- 复杂任务执行 harness
- planning / workspace / subagents
- 适合长任务和上下文隔离

选型:
- 简单场景 -> LangChain
- 复杂流程 -> LangGraph
- 复杂任务执行 -> DeepAgents

依赖:
- deepagents -> langchain -> langgraph -> langchain-core
```
