# Turn、SessionEvent 与 Tool Pipeline

## 1. Step 与 Turn 有意分开

[`ReactLoopAgent`](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/core/agent-loop/src/agent.ts)定义：一次 Step 是模型请求及其工具调用；一次 Turn 可以包含多个 Step。工具结果欠下一次模型请求，steering 也可以让当前 Turn 继续。

```text
turn/start
  → preStep：从 Inbox claim 输入，装配 System Prompt
  → step/start
  → user/message
  → deriveMessages()
  → agent/request → llm/stream
  → assistant/chunk* → assistant/message
  → tool/call* → ToolRuntime → tool/result*
  → step/end
  → 若工具或 next-step inbox 仍欠工作，继续 Step
  → agent/turn-stopping
  → turn/end(reason)
```

`turn/end`在 finally 中追加，所以 completed、blocked、aborted、max-tokens 和 error 都形成明确持久结局。错误不会只存在 stderr 中。

## 2. Phase 是并发安全边界

Agent 的 Phase 联合类型区分 idle、maintenance 和 running。Running 持有 AbortController、turn、step 和 wake latch；maintenance 用于压缩等不能与普通 Turn 并发的工作。

`wakeDriver()`不会为每条消息新建循环。如果已有 driver，它只把消息放入 Inbox，必要时设置 wakeRequested；旧活动收敛后再决定是否启动下一轮。这避免多个 Loop 同时消费同一 Session。

## 3. Inbox 表达输入时机

- `followup()`发送到 `next-turn`并唤醒；
- `steer()`发送到 `next-step`并唤醒；
- `inject()`发送到 `next-step`但不主动唤醒。

Inject 适合“下一次本来就要请求模型时加入上下文”，不会为了后台信息单独烧一次模型调用。时机是 Agent 输入协议的一部分，不只是三个相似 API。

## 4. Session Log 是唯一真源

[`Session`](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/core/session/src/index.ts)维护 append-only `SessionEvent[]`。每次 append：

1. 检查 payload 能否无损 JSON 序列化；
2. 验证 event/surface 状态转移；
3. 分配连续 `seq = log.length`和时间；
4. deep freeze 数据；
5. 提交到内存日志；
6. 通知 `session/event`观察者。

观察者失败不会撤销已经提交的事件。持久化插件订阅 feed 并异步写盘，`session/flush`则提供明确 durability checkpoint。

## 5. “模型可见即已记录”

`deriveMessages()`从 Session Surface 投影模型历史。流式 chunk 先作为事件记录，完整 assistant message 再带 `sourceEventSeqs`指向来源 chunk。UI 可以逐块渲染，恢复时又能重建最终消息。

如果一个插件把额外 context 直接塞进 HTTP Request 而不产生 Session Event，恢复、fork 和调试就无法解释模型为什么看到了它。项目用 invariant 强制模型边界可从日志重建，这是事件溯源最重要的价值。

## 6. Tool Registry 是作用域 Pipeline

[`ToolRuntime.execute()`](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/core/tools/src/index.ts)不是 `tools[name](args)`，而是分阶段处理：

```text
snapshot + JSON/schema validation
  → resolve visible tool in agent scope
  → tools/pre-execute waterfall
  → optional ask/approval
  → monotonic guards
  → tools/execute waterfall（around wrapper）
  → tool body
  → normalize canonical result
  → tools/post-execute waterfall
  → finalizer / presentation
  → immutable tools/result event
```

未知工具、参数非法、调用前取消、执行中取消和工具抛错都被规范化为结果。取消还区分 body 是否已经启动：已经启动的 Promise 要先收敛，再把外部结果标记为 aborted，避免后台副作用继续跑而上层误以为已经结束。

## 7. Guard 为什么是单调的

Pre-execute 策略可以 allow、ask 或 deny；后续 guard 可以进一步拒绝，但不应该把前面拒绝的动作重新升级为允许。安全组合应单调收紧权限，否则某个晚加载插件可能意外绕过管理员策略。

Scope 又增加一层：全局策略适用于所有 Agent，Agent Context 上的 guard 只看该 Agent 的调用。注册工具时同名冲突会明确报错；若需要 per-agent variant，应注册在对应 `agent.ctx`而不是覆盖全局。

## 8. Headless Runner 是最短产品路径

[`bundle/headless/src/index.ts`](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/bundle/headless/src/index.ts)值得作为入口阅读：等待插件树装载完成，取 `agents/defaultModel/sessions`服务，创建 Agent，发送 follow-up，等待 idle，flush Session，从事件中提取最后 assistant 文本与 turn reason，最后按 completed 与否设置退出码。

它证明 UI 不是 Agent 内核：同一插件图可以由 Web、CLI 或一次性 Runner 驱动，结果协议仍由 SessionEvent 定义。
