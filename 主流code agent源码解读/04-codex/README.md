# Codex 源码解读

> 固定版本：[`f5e9d668`](https://github.com/openai/codex/tree/f5e9d66851a20311b8385204686990c6c5960014)
>
> 阅读范围：开源 Codex Rust Core 的 Thread、Session、Turn、Context、Tool 与 Sandbox 主链
>
> 不覆盖：Codex 云端基础设施、所有 UI、认证细节、每个 MCP/App/Realtime/Multi-agent 分支

Codex 的难点不在 Loop 本身，而在“真实用户机器上的长寿命并发 Agent”需要同时处理协议稳定性、流式事件、会话恢复、动态工具、审批、跨平台沙箱、进程清理、上下文压缩和前端订阅。

## 不要从仓库根目录顺序阅读

固定版本已有大量 crate。建议先锁定 `codex-rs/core`中的一条主线：

```text
Client/App Server/TUI
  → CodexThread.submit / start_or_steer_turn
  → SessionIo submission channel
  → session_loop dispatch Op
  → RegularTask
  → session::turn::run_turn
  → Model Response stream
  → ToolRouter
  → ToolOrchestrator / Approval / Sandbox / Executor
  → FunctionCallOutput 写回上下文
  → 无工具欠款时 Turn complete
```

## 源码地图

| 路径 | 作用 |
| --- | --- |
| [`codex_thread.rs`](https://github.com/openai/codex/blob/f5e9d66851a20311b8385204686990c6c5960014/codex-rs/core/src/codex_thread.rs) | 面向宿主的 Thread 句柄和双向协议入口 |
| [`session/mod.rs`](https://github.com/openai/codex/blob/f5e9d66851a20311b8385204686990c6c5960014/codex-rs/core/src/session/mod.rs) | Session 初始化、Submission/Event Channel、主循环 |
| [`session/handlers.rs`](https://github.com/openai/codex/blob/f5e9d66851a20311b8385204686990c6c5960014/codex-rs/core/src/session/handlers.rs) | `Op`分发与控制事件 |
| [`session/turn.rs`](https://github.com/openai/codex/blob/f5e9d66851a20311b8385204686990c6c5960014/codex-rs/core/src/session/turn.rs) | 模型采样和工具往返主循环 |
| [`context_manager/history.rs`](https://github.com/openai/codex/blob/f5e9d66851a20311b8385204686990c6c5960014/codex-rs/core/src/context_manager/history.rs) | History、规范化、截断、Token 与 World State |
| [`tools/spec_plan.rs`](https://github.com/openai/codex/blob/f5e9d66851a20311b8385204686990c6c5960014/codex-rs/core/src/tools/spec_plan.rs) | 按 Turn 构建真实 Tool Registry 与可见 schema |
| [`tools/router.rs`](https://github.com/openai/codex/blob/f5e9d66851a20311b8385204686990c6c5960014/codex-rs/core/src/tools/router.rs) | ResponseItem → ToolCall → Runtime |
| [`tools/orchestrator.rs`](https://github.com/openai/codex/blob/f5e9d66851a20311b8385204686990c6c5960014/codex-rs/core/src/tools/orchestrator.rs) | 审批、沙箱尝试、升级与错误映射 |
| [`sandboxing/mod.rs`](https://github.com/openai/codex/blob/f5e9d66851a20311b8385204686990c6c5960014/codex-rs/core/src/sandboxing/mod.rs) | 策略解析后的执行请求与平台适配 |

## 推荐阅读

1. [Thread、Session 与 Turn](./01-Thread-Session-and-Turn.md)
2. [Context、Tool、Approval 与 Sandbox](./02-Context-Tools-and-Sandbox.md)
3. [源码实验](./03-Labs.md)

## 读完应能回答

- 为什么 Thread 只是句柄，真正的可变运行态在 Session？
- 为什么用户输入要经过有界 Submission Channel，而 Event Channel 可以无界？
- 为什么 ContextManager 同时保存 history version、token info 和 world-state baseline？
- 为什么 Tool Router 每个 Turn 重新按配置、MCP、Extension 与环境构建？
- Approval 与 Sandbox 为什么必须是两个独立层？
- 命令被 Sandbox 拒绝后，什么时候允许请求升级，什么时候必须直接失败？

Codex 源码最值得借鉴的是边界和失败语义，而不是照搬所有类型。每增加一层，先问它防止了哪一种具体竞态、越权或不可恢复状态。
