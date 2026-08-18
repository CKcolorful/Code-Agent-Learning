# Codex 源码实验

Codex 体量大，实验应尽量复用已有 Core 测试与 mock model server，避免每次编译和真实 API 调用都扩大变量。先运行目标 crate 的窄测试，再做修改。

## 实验 1：录制一次 Turn Event Timeline

构造固定响应：assistant tool call → tool output → final assistant。记录 submission ID、turn ID、item/call ID、事件类型和时间。

检查：

- delta 与 completed item 的顺序；
- Function Call Output 是否匹配 call ID；
- TurnStarted/Completed 是否恰好一次；
- 工具失败时是否仍生成模型可消费 output；
- 客户端取消后是否还有迟到事件写入。

把 Timeline 保存为机器可 diff 的 JSON，升级 commit 后可直接比较协议变化。

## 实验 2：Start/Steer 的并发原子性

同时提交两个 start-if-idle，请求应只有一个 Started，另一个得到明确 NotSubmitted；随后在 active Turn 中提交 steer，确认它进入当前 Turn 而不是创建第二个并发 Turn。

再模拟 Turn 刚结束时的边界竞态，验证 API 返回值足以让调用方知道输入归属，不需要先查询状态。

## 实验 3：History 配对与 Rollback

构造包含两个 Function Call/Output 对、图像内容和长工具输出的 ContextManager：

- 删除最旧 item，检查成对元素是否一起处理；
- 切换到不支持图像的模型，检查 prompt 视图；
- 应用 output truncation，比较 raw 与 model-visible 内容；
- rollback 后检查 `history_version`与 reference context；
- 压缩前后验证工具协议仍合法。

## 实验 4：Approval × Sandbox 矩阵

准备只读命令、工作区写命令、工作区外写命令和网络命令，在不同 Permission Profile/Approval Policy 下记录：

```text
command class | asked? | user answer | sandbox | executed? | result
```

至少覆盖：用户允许但沙箱仍拒绝、策略禁止且不可询问、沙箱拒绝后允许一次升级、网络被单独控制。该实验用于证明审批不是沙箱的替代品。

## 实验 5：进程取消与输出截断

启动持续输出且创建子进程的命令，分别触发 timeout、用户 cancel 和输出上限。验证：

- 子进程是否清理；
- Event 中能否区分 timeout/cancel/non-zero exit；
- head-tail buffer 是否标记省略；
- 后台 process handle 是否失效；
- Thread 何时真正回到 idle。

## 实验 6：Compaction 状态保真

构造包含 instructions、一次权限变化、多个工具结果和当前失败测试的长历史，强制 compaction。提出恢复查询：任务目标、当前 diff、测试失败、权限和未完成步骤。比较压缩前后答案与 Token 数。

同时检查 compaction hooks 和 Rollout 事件，让“模型摘要正确”与“运行时状态迁移正确”分开验收。

## 建议提交物

```text
labs/codex/
├── turn-event-timeline.rs
├── concurrent-turn-input.rs
├── history-invariants.rs
├── approval-sandbox-matrix.md
├── process-cancellation.rs
├── compaction-fixtures/
└── RESULTS.md
```

Codex 实验的目标不是一次跑完整工作区测试，而是把一个生产级边界缩小成可解释、可复现的断言。
