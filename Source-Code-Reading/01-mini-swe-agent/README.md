# mini-SWE-agent 源码解读

> 固定版本：[`25941c89`](https://github.com/SWE-agent/mini-swe-agent/tree/25941c89cfbc91eb40b3f8756348c91d9977d57e)（mini-SWE-agent 2.4.6）
>
> 阅读范围：默认 Agent、Model/Environment 协议、Local/Docker Environment、配置与 Trajectory
>
> 不覆盖：每个模型提供方的认证细节、所有 Benchmark Runner 与 TUI Inspector

mini-SWE-agent 的价值不只是“代码少”。它把 Code Agent 收缩为三个可替换对象：`Agent` 决定控制流，`Model` 把历史转换成下一批 Action，`Environment` 执行动作并返回 Observation。这使它接近一份可以运行、可以替换部件的 Agent 形式化定义。

## 源码地图

| 路径 | 作用 | 阅读优先级 |
| --- | --- | --- |
| [`agents/default.py`](https://github.com/SWE-agent/mini-swe-agent/blob/25941c89cfbc91eb40b3f8756348c91d9977d57e/src/minisweagent/agents/default.py) | Loop、预算、异常、Trajectory | 必读 |
| [`__init__.py`](https://github.com/SWE-agent/mini-swe-agent/blob/25941c89cfbc91eb40b3f8756348c91d9977d57e/src/minisweagent/__init__.py) | `Model`、`Environment`、`Agent` Protocol | 必读 |
| [`run/mini.py`](https://github.com/SWE-agent/mini-swe-agent/blob/25941c89cfbc91eb40b3f8756348c91d9977d57e/src/minisweagent/run/mini.py) | CLI 组装 Model、Environment、Agent | 必读 |
| [`config/mini.yaml`](https://github.com/SWE-agent/mini-swe-agent/blob/25941c89cfbc91eb40b3f8756348c91d9977d57e/src/minisweagent/config/mini.yaml) | Prompt、预算、输出截断、提交协议 | 必读 |
| [`environments/local.py`](https://github.com/SWE-agent/mini-swe-agent/blob/25941c89cfbc91eb40b3f8756348c91d9977d57e/src/minisweagent/environments/local.py) | 本地子进程与进程组清理 | 推荐 |
| [`environments/docker.py`](https://github.com/SWE-agent/mini-swe-agent/blob/25941c89cfbc91eb40b3f8756348c91d9977d57e/src/minisweagent/environments/docker.py) | 持久容器、`docker exec` 与清理 | 推荐 |
| `models/utils/actions_*` | 文本/Tool Call 解析与 Observation 格式 | 第二遍 |

## 一句话架构

```text
CLI 递归合并配置
  → 创建 Model + Environment + Agent
  → Agent.run(task)
  → Model.query(messages)
  → Environment.execute(action)
  → Model.format_observation_messages(...)
  → 继续，直到 Environment 抛出 Submitted 或预算/错误终止
```

最重要的设计不是 `while True`，而是两个边界：

- Action 的解释权属于 Model Adapter：不同 API 可以使用文本、Chat Completions Tool Call 或 Responses Function Call；
- 结束不是模型输出一句话，而是 Environment 识别到专用提交命令并抛出 `Submitted`，由 Loop 记录为 `role=exit`。

## 推荐阅读

1. [控制流与异常协议](./01-Control-Flow.md)
2. [Environment、输出策略与 Trajectory](./02-Environment-and-Trajectory.md)
3. [四个可证伪的源码实验](./03-Labs.md)
4. [经典 SWE-agent：从极小基线回看 ACI](./04-Classic-SWE-agent.md)

## 读完应能回答

- 为什么 `FormatError` 的费用要在 Agent 层补记？
- 为什么 Local Environment 超时后要杀进程组而不是只杀父进程？
- 为什么 Docker 后端复用容器，但每次 Action 仍是新 shell？
- 为什么输出截断在模板层实现，而不是直接丢弃原始 Environment 输出？
- 为什么 `Submitted` 是控制流异常，而不是普通返回值？

这五个问题分别对应成本一致性、资源回收、执行语义、观察策略和终止协议，也是从 Demo 走向可靠 Harness 时最先出现的工程问题。
