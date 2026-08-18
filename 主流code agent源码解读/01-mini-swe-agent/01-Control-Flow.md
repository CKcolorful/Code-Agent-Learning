# 控制流：六个方法构成的最小 Agent

mini-SWE-agent 的默认控制面集中在 `DefaultAgent`。不要先看所有模型适配器，先看下面六个方法形成的闭环：

```text
run
 ├─ render system/instance template
 ├─ while true
 │    └─ step
 │        ├─ query
 │        │   ├─ 检查 step/cost/time
 │        │   ├─ model.query(messages)
 │        │   └─ 记账并追加 assistant message
 │        └─ execute_actions
 │            ├─ env.execute(action) × N
 │            └─ model.format_observation_messages(...)
 ├─ save trajectory（每轮 finally）
 └─ role == exit 时结束
```

对应源码是 [`DefaultAgent.run/query/execute_actions`](https://github.com/SWE-agent/mini-swe-agent/blob/25941c89cfbc91eb40b3f8756348c91d9977d57e/src/minisweagent/agents/default.py)。它刻意没有 Planner、Verifier 或复杂 Scheduler：消息列表既是模型上下文，也是可序列化轨迹的主体。

## 1. CLI 是 Composition Root

[`run/mini.py`](https://github.com/SWE-agent/mini-swe-agent/blob/25941c89cfbc91eb40b3f8756348c91d9977d57e/src/minisweagent/run/mini.py)从默认 YAML、额外配置文件和 CLI 参数递归合并出最终配置，然后用工厂分别创建 Model、Environment 和 Agent，最后调用 `agent.run(task)`。

CLI 不参与每一步决策。替换本地环境为 Docker，或替换文本 Action 为结构化 Tool Call，Agent 主循环都不需要修改。这是依赖倒置最小但清晰的应用。

## 2. Protocol 是真正的模块边界

根模块中的三个 Python `Protocol` 没有提供基类实现，只声明所需行为：

```text
Model: query / format_message / format_observation_messages / serialize
Environment: execute / get_template_vars / serialize
Agent: run / save
```

Model 不只负责 HTTP 请求，还拥有“如何从提供方响应中提取 Action”和“如何把结果编码回提供方消息格式”的责任。这个选择避免 Loop 充斥 OpenAI、Anthropic 或文本解析分支，但也让 Model Adapter 同时承担传输协议和 ACI 编解码。

## 3. `run()` 是异常驱动状态机

循环没有显式枚举状态，而是使用异常表达非正常转移：

| 异常 | 来源 | Loop 行为 |
| --- | --- | --- |
| `FormatError` | Model 无法解析有效动作 | 把纠错消息送回历史；连续超限后退出 |
| `InterruptAgentFlow` | 受控中断的共同路径 | 追加异常携带的消息 |
| `LimitsExceeded` | 调用次数或费用达到上限 | 追加 `exit` 消息 |
| `TimeExceeded` | 墙钟时间达到上限 | 追加 `exit` 消息 |
| 其他异常 | 编程错误、未知环境错误 | 记录 traceback 后重新抛出 |

受控异常携带“应写入消息历史的消息”，所以它既是控制信号也是状态转移载荷。如果吞掉未知异常，系统会把程序 Bug 伪装成正常 Agent 失败；如果所有异常都上抛，预算耗尽又无法形成完整 Trajectory。

## 4. 费用为何有特殊分支

正常路径中，`model.query()`返回 message 后，Agent 从 `message.extra.cost`累加费用。格式错误时，提供方请求已经产生费用，但 `query()`在成功返回 message 前抛出 `FormatError`，正常记账点不会执行。因此 `run()`从异常附带消息中补记 cost。

通用原则是：预算统计必须覆盖“远程副作用已发生、业务结果未返回”的半失败状态。类似问题还会出现在工具已执行但结果序列化失败、网络超时但服务端已接收请求等场景。

## 5. 结束协议在 Environment 中判定

默认 prompt 要求模型单独执行：

```bash
echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT
```

Environment 检查 stdout 第一行和退出码。满足条件时不返回普通 Observation，而是抛出 `Submitted`，其中包含 `role=exit`、`exit_status=Submitted`和 submission。

所以“模型停止生成”和“任务提交”是分离的。模型必须通过一个环境可观察动作进入终态。它仍不等于验证通过——SWE-bench correctness 由外部测试评测——但比“没有工具调用就算成功”明确得多。

## 6. 多 Action 的部分提交语义

`execute_actions()`对 message 中所有 Action 依次执行，随后统一格式化 Observation。这里没有并行、事务或中途回滚。如果第一个 Action 修改了文件，第二个失败，环境已经处于部分提交状态。

阅读时要明确三层事实：模型可以一次产生多个 Action；默认实现顺序执行；文件副作用不会因后续失败自动撤销。这为后续 Pi 的工具执行策略和 Codex 的工具编排提供了对照基线。

## 7. 最小设计的边界

它有意缺少独立 Verifier、审批状态、工作区写策略、可恢复 Session 状态机和 Action 事务隔离。这说明其目标是研究和基准执行，而不是默认在用户主机上提供生产级安全边界。学习时应把“代码存在的机制”和“生产系统还需要的机制”分开评价。
