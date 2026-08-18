# Pi Agent 源码解读

> 固定版本：[`e5dde9a7`](https://github.com/earendil-works/pi/tree/e5dde9a76bfec3c4eff764d1b6db3b60e5dd0b30)
>
> 阅读范围：`packages/agent` 与 `packages/coding-agent` 的核心调用链
>
> 不覆盖：所有 Provider 实现、TUI 每个组件、浏览器/Server/Telemetry 包

Pi 的核心思想不是“只提供四个工具”，而是把推理循环、产品级会话、终端 UI 与扩展机制分层。固定版本中，低层 `packages/agent`提供模型无关的流式 Agent；`packages/coding-agent`再加入资源加载、Session、Compaction、Extension、CLI 模式和交互体验。

## 四层对象

```text
CLI / Interactive / Print / JSON / RPC
                  │
                  ▼
             AgentSession
   持久化、压缩、重试、扩展、工具刷新
          │                 │
          ▼                 ▼
       Agent            SessionManager
  流式 Loop、队列、状态      JSONL 树与分支
          │
          ▼
     Model Stream + AgentTool
```

将这些对象混为“Agent 类”会看不懂源码：`Agent`只拥有当前运行状态和循环；`AgentSession`是应用服务；`SessionManager`保存可分支历史；`ExtensionRunner`把第三方行为接入 Session 生命周期。

## 源码地图

| 路径 | 作用 |
| --- | --- |
| [`packages/agent/src/agent-loop.ts`](https://github.com/earendil-works/pi/blob/e5dde9a76bfec3c4eff764d1b6db3b60e5dd0b30/packages/agent/src/agent-loop.ts) | 内外双层循环、流式响应、工具调用、steering/follow-up |
| [`packages/agent/src/agent.ts`](https://github.com/earendil-works/pi/blob/e5dde9a76bfec3c4eff764d1b6db3b60e5dd0b30/packages/agent/src/agent.ts) | Stateful wrapper、订阅、消息队列、Abort |
| [`core/agent-session.ts`](https://github.com/earendil-works/pi/blob/e5dde9a76bfec3c4eff764d1b6db3b60e5dd0b30/packages/coding-agent/src/core/agent-session.ts) | 产品级编排中心 |
| [`core/session-manager.ts`](https://github.com/earendil-works/pi/blob/e5dde9a76bfec3c4eff764d1b6db3b60e5dd0b30/packages/coding-agent/src/core/session-manager.ts) | 父子 Entry、分支、Compaction 边界 |
| [`core/compaction/compaction.ts`](https://github.com/earendil-works/pi/blob/e5dde9a76bfec3c4eff764d1b6db3b60e5dd0b30/packages/coding-agent/src/core/compaction/compaction.ts) | 压缩触发、切分与摘要 |
| [`core/extensions/runner.ts`](https://github.com/earendil-works/pi/blob/e5dde9a76bfec3c4eff764d1b6db3b60e5dd0b30/packages/coding-agent/src/core/extensions/runner.ts) | 扩展注册、事件、命令与 UI 上下文 |
| [`main.ts`](https://github.com/earendil-works/pi/blob/e5dde9a76bfec3c4eff764d1b6db3b60e5dd0b30/packages/coding-agent/src/main.ts) | CLI Composition Root 与模式选择 |

## 推荐阅读

1. [Agent Loop、消息队列与 Session](./01-Agent-Loop-and-Session.md)
2. [Session Tree、Compaction 与 Extension](./02-Compaction-and-Extensions.md)
3. [源码实验](./03-Labs.md)

## 读完应能回答

- 为什么 Loop 有内外两层，而不是单个 `while(toolCalls)`？
- Steering 和 Follow-up 为什么需要两个队列？
- 为什么 Session Entry 使用 `parentId`而不是只有线性数组？
- Compaction 后为什么还要保留 `firstKeptEntryId`？
- Extension 为什么能更改工具和 Prompt，却不能被当作安全沙箱？

Pi 的可学习之处在于：保持模型循环足够通用，同时把产品复杂度放进明确的 Session 层，而不是不断往 Loop 加 if/else。
