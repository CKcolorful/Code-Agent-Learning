# Thread、Session 与 Turn：Codex 的控制主干

## 1. 三个层级不要混淆

| 层级 | 代表对象 | 生命周期 | 主要职责 |
| --- | --- | --- | --- |
| Thread | `CodexThread` | 面向宿主的会话句柄 | submit、事件接收、resume/shutdown |
| Session | `Session` + `SessionIo` | Core 内的长寿命运行时 | 状态、服务、active turn、队列、持久化 |
| Turn | `run_turn` + Task/Context | 一次用户工作区间 | 多次模型采样、工具调用、完成与取消 |

`CodexThread`封装 `Arc<Session>`和 I/O 通道。它不是所有逻辑的 God Object，而是 App Server、TUI 等宿主调用 Core 的稳定门面。

## 2. Submission/Event 双向通道

Session 初始化时创建：

- 有界 Submission Channel：客户端向 Core 发送 `Op`；
- Event Channel：Core 向客户端发布流式 `Event`。

Submission 有容量上限可以提供背压，避免失控客户端无限排队操作。Event 流需要及时消费和更高吞吐，否则模型 delta、工具进度和状态更新会阻塞核心控制流；真实系统仍需在宿主侧做消费、聚合与断线策略。

`SessionIo.submit()`为每个操作生成 ID，再把 `Submission { id, op, trace... }`送进 channel。ID 让前端把异步事件、审批回答和原始请求关联起来，而不是依赖事件到达顺序猜测。

## 3. Session Spawn 是策略冻结点

[`Session::spawn_internal`](https://github.com/openai/codex/blob/f5e9d66851a20311b8385204686990c6c5960014/codex-rs/core/src/session/mod.rs)需要装配模型、用户指令、配置层、权限、环境、Skills、Plugins、MCP、Thread Store、扩展与遥测。

关键不是参数多，而是这些输入中有些必须在 Session 建立时冻结：

- 基础 instructions 的来源优先级；
- 新建、恢复、fork 的 history 模式；
- permission profile 与 approval policy；
- 模型 fallback 和 capability；
- 继承的执行规则与多 Agent 版本。

如果在 Turn 中随意重新读取未版本化全局配置，同一 Thread 的安全和提示语义会悄悄漂移。Codex 会在 Turn Context 中形成本轮快照，并通过事件/历史表达必要变化。

## 4. `Op` 分发把控制请求与模型工作分开

Session Loop 接收的不只有用户消息，还包括 interrupt、shutdown、approval response、user-input response、compact、review、settings update 等操作。它们不是都应该进入模型上下文。

例如 approval answer 是控制面输入，用来恢复一个等待中的工具执行；用户 steering 才是可能进入当前 Turn 的模型可见输入。把两者都编码成普通 chat message，会让权限协议依赖模型理解，并难以处理超时和重复回答。

## 5. Start、Steer 与 Recover 是显式结果

`CodexThread`提供 start-or-steer、start-if-idle、steer、recover 等接口，并返回：Started、Steered 或 NotSubmitted(reason)。调用者无需先读 Thread 状态再决定动作，从而避免典型 TOCTOU：查询时 idle，提交时已经 running。

Core 在一个原子控制路径中判断并返回结果。Recover 还可以保持已记录的 turn ID，不把进程中断后的继续伪装成全新用户 Turn。

## 6. Regular Task 驱动一个或多个输入批次

普通任务调用 `run_turn()`。若运行期间 Input Queue 又积累了 steering，任务会在同一 Turn 任务边界继续取下一批输入；没有 pending input 才返回最后 assistant message。

这与 Pi 的内外双层循环解决相似问题，但表达不同：Pi 把队列逻辑放在通用 Agent Loop，Codex 把 active turn、input queue 和 Task 生命周期结合在 Session 运行时中。

## 7. `run_turn()` 才是采样循环

[`session/turn.rs`](https://github.com/openai/codex/blob/f5e9d66851a20311b8385204686990c6c5960014/codex-rs/core/src/session/turn.rs)的大致路径：

```text
写入本轮 input/context update
  → 检查是否需要 pre-turn/inline compaction
  → 建立 ModelClientSession
  → 构造 Prompt：instructions + ContextManager history + tool specs
  → 读取 Response stream
  → 记录 reasoning/message/tool item 与 delta event
  → ToolRouter 识别 function/custom/tool-search call
  → 并发或顺序执行允许的工具
  → 记录 FunctionCallOutput
  → 还有工具结果或 pending input：再次采样
  → 只有 assistant final：完成本 Turn
```

`run_turn()`注释中的 Loop 很简单，但前后包含 Hook、Skill/MCP 注入、工具动态发现、Retry、Diff Tracker、Token Budget 和 Compaction。阅读时先抓住“模型 item 是否产生下一次输入”这条主线，再逐个打开旁路。

## 8. 取消必须向下传播

Turn 使用 `CancellationToken`，工具和子任务拿 child token。取消不等于丢弃 Future：已经启动的进程、网络请求或工具 Runtime 必须观察 token 并清理。部分工具还声明是否等待 Runtime cancellation，决定上层能否宣布 Turn 已收敛。

生产定义的 idle 不是“模型流停了”，而是与本 Turn 关联的必等任务、进程、审批和持久化都到达安全边界。

## 9. Rollout 与 Thread Store

模型历史、面向前端的事件和可恢复 Thread 元数据不是一份文件的三个名字：它们服务不同消费者。Rollout 记录 Harness 轨迹，Thread Store 提供 Thread 元数据与历史加载，ContextManager 则提供下一次模型请求所需的规范化视图。

恢复必须把它们重新对齐：Thread 身份、Turn 边界、历史 item、当前配置与工作区事实不能互相矛盾。这也是 Codex 比最小 Trajectory 多出大量重建与迁移代码的原因。
