# Agent Loop 与 Session：从一次生成到可交互产品

## 1. 两个入口，共用一个 Loop

[`agent-loop.ts`](https://github.com/earendil-works/pi/blob/e5dde9a76bfec3c4eff764d1b6db3b60e5dd0b30/packages/agent/src/agent-loop.ts)暴露两个入口：

- `agentLoop(prompts, context, ...)`：加入新 prompt 后启动；
- `agentLoopContinue(context, ...)`：不加入新消息，从已有 user/toolResult 继续，主要用于重试。

二者最终进入 `runLoop()`。Continue 会拒绝空历史和以 assistant 结尾的历史，因为多数 Provider 要求下一次请求从 user 或 tool result 边界继续。这是协议合法性检查，不是界面限制。

## 2. 内外双层循环

```text
outer while
  ├─ inner while：还有 tool call 或 steering message
  │    ├─ 注入 pending steering
  │    ├─ 流式生成 assistant message
  │    ├─ 执行 tool calls
  │    ├─ 产生 tool results
  │    └─ prepareNextTurn 可替换 context/model/reasoning
  ├─ 若没有 tool call，检查 follow-up queue
  └─ 没有欠下的消息才 agent_end
```

内层解决当前任务还需不需要继续采样；外层解决 Agent 原本准备停止时，用户是否已经排队了后续要求。因此“模型不调用工具”不必立即销毁一次交互会话。

## 3. Steering 与 Follow-up

- **Steering**：用户在 Agent 工作中途补充方向，在下一次 assistant 响应前注入；
- **Follow-up**：当前 Agent 自然结束后再发起下一轮工作。

两类队列都支持一次取一条或一次取全部。区分它们能避免一个常见竞态：用户的“别改那个文件”如果被当作普通 follow-up，可能要等当前工具链结束才生效；普通新任务如果中途插入，又会污染当前修复。

## 4. EventStream 是 UI 与 Core 的契约

循环发出 `agent_start`、`turn_start`、`message_start/end`、工具更新、`turn_end`、`agent_end`等事件。调用者不需要等完整回答才刷新界面，也不需要从 messages diff 猜发生了什么。

事件还有两个工程含义：

- `Agent`可以通过订阅更新自己的 `isStreaming`、pending tool calls 与错误状态；
- `AgentSession`可以在同一事件边界完成持久化、扩展分发、自动压缩和重试判断。

这比让 TUI 直接侵入 Loop 更容易测试，但事件顺序本身成为兼容协议，新增异步监听器时必须考虑它是否阻塞当前 Run。

## 5. Tool Call 的防御路径

Loop 不会把所有模型输出直接执行：

- 先从 assistant content 提取 `toolCall`块；
- 如果 stop reason 是 `length`，视为参数可能被截断，整批调用失败而不执行；
- 使用 schema 验证工具参数；
- 经过 before/after tool call hook；
- 依据配置决定多个工具顺序或并行执行；
- 把结果转换成 ToolResultMessage，再加入上下文。

“length 时不执行”非常重要：一个看似合法的 JSON 前缀也可能缺少模型原本准备追加的路径或选项。安全默认值应是把截断结果反馈给模型，而不是猜测参数。

## 6. `Agent` 只做运行态封装

[`agent.ts`](https://github.com/earendil-works/pi/blob/e5dde9a76bfec3c4eff764d1b6db3b60e5dd0b30/packages/agent/src/agent.ts)持有：system prompt、model、thinking level、tools、messages、流式状态、AbortController，以及 steering/follow-up queue。

它不负责把 Session 写到磁盘，也不负责发现 Skills/Extensions。这样低层 Agent 可以用于 SDK、测试或不同宿主。`AgentSession`订阅 Agent 事件，把它提升为 coding product。

## 7. `AgentSession` 是应用服务

[`core/agent-session.ts`](https://github.com/earendil-works/pi/blob/e5dde9a76bfec3c4eff764d1b6db3b60e5dd0b30/packages/coding-agent/src/core/agent-session.ts)负责：

- 将 Agent 消息追加到 SessionManager；
- 维护自动压缩、重试、Branch Summary 与独立 AbortController；
- 组装基础工具、自定义工具和扩展工具；
- 刷新 System Prompt、Skills 和资源；
- 把事件转发给 ExtensionRunner；
- 暴露交互、Print、JSON、RPC 共用的会话 API。

它体量较大不是因为 Loop 复杂，而是多条生命周期会在此交汇。阅读时建议按“一次 prompt”“一次 compaction”“一次 extension reload”三条调用链分开追踪，不要试图一次记住所有字段。

## 8. 取消不是一个布尔值

Agent Run、Compaction、Branch Summary、Retry、外部 Bash 分别有 AbortController。原因是取消范围不同：用户取消当前生成，不一定要破坏整个 Session；压缩失败不应误杀无关 Bash；切换 Session 时又必须等待所有占用旧状态的活动收敛。

生产 Agent 的取消语义应回答：取消谁、谁负责向子任务传播、何时算 idle、迟到事件是否还能写入状态。Pi 把这些问题集中在 Session 层处理。
