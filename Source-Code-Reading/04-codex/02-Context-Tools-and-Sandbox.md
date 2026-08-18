# Context、Tool、Approval 与 Sandbox

## 1. ContextManager 不是消息数组包装器

[`ContextManager`](https://github.com/openai/codex/blob/f5e9d66851a20311b8385204686990c6c5960014/codex-rs/core/src/context_manager/history.rs)维护：

- 带 Harness metadata 的 `ResponseItemEnvelope`；
- `history_version`，在 compaction、rollback 等重写后递增；
- Token Usage；
- 下一 Turn 的 reference context；
- World State baseline，用于生成全量或增量状态；
- 面向模型 input modality 的规范化视图。

使用 `Arc<Vec<_>>`加 copy-on-write，使多个只读快照共享历史，直到某方真的修改。这对于 UI、扩展、压缩和模型请求并发读取长历史很重要。

## 2. History Invariant

记录 item 时，ContextManager 会过滤非 API message，对工具输出应用截断策略；发送前再规范化 call/output 配对，去掉模型不支持的图像或音频内容。删除一个 function call 时还要处理对应 output，否则 Provider 会拒绝不合法历史。

因此压缩或 rollback 不能直接 `items.truncate(n)`。它必须保持协议配对、developer/user context 顺序以及工具结果可解释性。

## 3. World State 采用 Diff

Context 中的 cwd、权限、环境、预算等状态不是每轮都重复完整注入。ContextManager 保存 baseline，根据新快照生成 model-visible diff，并可在首次或基线丢失时重新注入 full state。

这减少稳定前缀的 Token，但引入版本问题：如果 rollback 删除了建立 baseline 的历史，下一 Turn 必须清空 reference，重新发送完整状态，不能继续输出相对于不存在基线的 patch。

## 4. Compaction 是历史重写事务

Codex 同时存在本地与远程 compaction 路径。压缩不仅生成 summary，还需要：

- 保留初始上下文或重新注入必要 instructions；
- 处理 Function Call 与 Output 配对；
- 更新 token info 与 history version；
- 记录 compaction 生命周期事件；
- 执行 pre/post compact hooks；
- 失败时选择 fallback 或保留原历史。

判断压缩正确与否，应比较压缩后是否还能恢复任务状态、工具事实和安全上下文，而不是只看 Token 数。

## 5. Tool Router 分离“可见”与“可执行”

[`build_tool_router()`](https://github.com/openai/codex/blob/f5e9d66851a20311b8385204686990c6c5960014/codex-rs/core/src/tools/spec_plan.rs)按本 Turn 的模型能力、Feature、Permission Profile、MCP、Apps、Extension、动态工具、Tool Search 和环境构建 Registry 与 model-visible specs。

工具可能是：

- Direct：schema 直接发送给模型；
- Deferred：先由工具搜索发现；
- Code Mode only：只能从代码执行通道调用；
- Hidden：Runtime 存在但当前模型不可见。

因此“注册了工具”不等于“本轮 Prompt 暴露了工具”，更不等于“策略允许执行”。这三个集合必须分别审计。

## 6. ResponseItem 到 Tool Runtime

[`ToolRouter.build_tool_call()`](https://github.com/openai/codex/blob/f5e9d66851a20311b8385204686990c6c5960014/codex-rs/core/src/tools/router.rs)识别普通 Function Call、自定义工具和客户端执行的 Tool Search Call，统一成包含 name、namespace、call_id 和 payload 的 `ToolCall`。

Namespace 防止 MCP、Extension、Collaboration 和 Core 工具同名碰撞；call_id 则把最终 output 与模型请求配对。某些敏感工具的日志还避免记录明文参数，说明 observability 也必须遵守数据最小化。

Router 找到具体 `CoreToolRuntime`后，才将 Session、StepContext、CancellationToken 和 DiffTracker 交给它执行。Handler 不应该自行从全局重新推断本轮权限。

## 7. Orchestrator：策略、审批与执行尝试

工具 Handler 定义动作本身，Orchestrator 处理执行策略：

```text
Tool Invocation
  → 计算 approval requirement
  → 必要时发送 approval event 并等待回答
  → 选择 sandbox attempt
  → 执行
  → 若 sandbox denied，判断是否允许升级/重试
  → 规范化输出或错误
```

审批和沙箱不能合并：

- Approval 回答“用户是否授权这个意图”；
- Sandbox 强制“即使获授权，进程实际能访问哪些资源”。

用户允许安装依赖，不意味着命令自动获得读取 SSH Key 的能力；命令在沙箱中失败，也不应该无条件升级为 unrestricted。

## 8. Permission Profile 到平台沙箱

[`sandboxing/mod.rs`](https://github.com/openai/codex/blob/f5e9d66851a20311b8385204686990c6c5960014/codex-rs/core/src/sandboxing/mod.rs)接收已经解析的 command、cwd、env、network、expiration、capture policy、workspace roots、Windows level 和 Permission Profile，转换为最终 `ExecRequest`。

平台实现大致包括：

- macOS Seatbelt；
- Linux Landlock/Bubblewrap 等后端；
- Windows Restricted Token/ACL 或更高等级后端；
- 受管理网络代理和网络禁用标记。

核心原则是 policy 与 mechanism 分离：上层决定 workspace-write/read-only/network，平台层将其变成 OS 可强制的命令和文件系统规则。

## 9. 输出与进程生命周期

执行器还需要处理超时、流式 stdout、head-tail buffer、输出 Token 截断、异步 watcher、write_stdin、后台 process ID 和进程树清理。只在 Router 返回字符串会丢失这些真实生命周期。

一个命令工具的完整结果至少应说明：是否启动、是否仍在运行、exit code、超时/取消、输出是否截断、在哪个 cwd/沙箱执行，以及是否产生可继续交互的 process handle。

## 10. 完成不等于可信

Codex Turn 在模型没有继续产生工具调用时可以自然结束，但产品还可以通过 hooks、review/guardian、测试或调用方协议增加门禁。源码阅读时不要把“Turn completed event”直接解释为“代码修改正确”；正确性证据仍需绑定当前 diff 和测试 revision。
