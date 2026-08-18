# 经典 SWE-agent：从极小基线回看 ACI

> 固定版本：[`3ea751c0`](https://github.com/SWE-agent/SWE-agent/tree/3ea751c087f32b16e039a2233dd6eefecef325d5)
>
> 阅读定位：经典完整 SWE-agent 的 Agent、Tool/ACI、History Processor 与 SWE-ReX Environment
>
> 当前关系：上游主要新工作转向 mini-SWE-agent，但经典实现仍适合研究可配置 ACI

mini-SWE-agent 用 Bash-only 证明最小基线可以很短；经典 SWE-agent 则回答另一个问题：怎样为模型设计专用命令、观察窗口、历史策略和可重复 Benchmark Environment。

## 1. 源码地图

| 路径 | 作用 |
| --- | --- |
| [`agent/agents.py`](https://github.com/SWE-agent/SWE-agent/blob/3ea751c087f32b16e039a2233dd6eefecef325d5/sweagent/agent/agents.py) | `DefaultAgent`、setup/step/run、异常重试和 Trajectory |
| [`tools/tools.py`](https://github.com/SWE-agent/SWE-agent/blob/3ea751c087f32b16e039a2233dd6eefecef325d5/sweagent/tools/tools.py) | `ToolConfig`、`ToolHandler`、命令安装、Parser 与 Blocklist |
| [`tools/parsing.py`](https://github.com/SWE-agent/SWE-agent/blob/3ea751c087f32b16e039a2233dd6eefecef325d5/sweagent/tools/parsing.py) | 文本/函数调用 Action 解析 |
| [`agent/history_processors.py`](https://github.com/SWE-agent/SWE-agent/blob/3ea751c087f32b16e039a2233dd6eefecef325d5/sweagent/agent/history_processors.py) | Last-N、Closed Window、Cache Control 等策略 |
| [`environment/swe_env.py`](https://github.com/SWE-agent/SWE-agent/blob/3ea751c087f32b16e039a2233dd6eefecef325d5/sweagent/environment/swe_env.py) | SWE-ReX Deployment、Repo Reset 与持久 shell |

## 2. `DefaultAgent` 的三份状态

经典实现明确分开：

- `history`：未裁剪的消息事实；
- `messages` property：依次经过 History Processor 后，真正发送给模型的视图；
- `_trajectory`：每一步的 thought、action、observation、state、execution time 与 query。

这比 mini 的单一 messages 列表更适合研究 Context Policy。History Processor 不删除原始 history，而是为请求生成派生视图，因此评测者仍可分析模型当时被隐藏了什么。

## 3. ToolConfig 定义 ACI

`ToolConfig`不只是工具名数组，还包含：

- 命令 Bundle 与安装方式；
- Action Parser；
- 命令文档与环境变量；
- blocklist 与错误模板；
- multi-line command guard；
- submit command；
- shell command fallback。

`ToolHandler.install()`把专用命令上传到 Environment，并修改 PATH。也就是说 ACI 同时包含模型看到的文档、输出 Parser 和容器内真正可执行的命令；只修改 prompt 里的工具描述却不修改安装/runtime，会产生协议漂移。

## 4. History Processor 是请求时投影

`DefaultAgent.messages`先按 agent name 过滤，再串联所有 processor。典型策略：

- `LastNObservations`：保留最近 N 个 observation，旧输出替换成省略标记；
- `ClosedWindowHistoryProcessor`：同一文件的旧窗口变成摘要，只保留最新窗口；
- `CacheControlHistoryProcessor`：给指定消息打 Provider cache 标签；
- Tag Processor：根据工具名给 observation 打 keep/remove 标签。

这比“取最后 N 条消息”更符合代码任务：旧工具输出可过期，但任务描述、Action 和特定验证证据不能一视同仁地删除。

一个细节是 Last-N 的 polling：不是每步都改变裁剪边界，可以减少 Prompt Cache 因历史前缀变化而失效。Context Policy 同时影响模型质量和 API 成本。

## 5. SWEEnv 与 mini Environment 的差别

经典 [`SWEEnv`](https://github.com/SWE-agent/SWE-agent/blob/3ea751c087f32b16e039a2233dd6eefecef325d5/sweagent/environment/swe_env.py)基于 SWE-ReX Deployment：

- 启动本地/容器/远程部署；
- 创建持久 Bash Session；
- 拷贝并 reset 指定 Repo/base commit；
- 安装 ACI 命令；
- 通过 runtime communicate 执行与中断；
- 在 Attempt 间把仓库恢复到干净基线。

它更适合批量 Benchmark：Environment 生命周期和 repo revision 是 Trial 配置的一部分。mini 的每 Action 新 shell 更简单；经典的持久 shell 方便保持 cwd/env，却增加了污染与恢复成本。

## 6. Step 中发生什么

```text
setup：启动环境、安装工具、构造 system/demo/instance history
  → messages：应用 History Processors
  → forward_with_handling：调用模型、解析 Action、处理格式/超时/费用错误
  → Environment 执行 Action
  → add_step_to_history：Action + 经过模板截断的 Observation
  → add_step_to_trajectory：保存分析所需原始 Step 字段
  → save trajectory
  → StepOutput.done 时结束
```

`forward_with_handling`允许对格式、blocklist 和 Bash 语法错误重新请求，并限制 requery 次数；环境/API/费用错误则映射为不同 exit status，必要时自动提交当前 patch。失败分类直接影响评测是否能区分 Agent 无能、基础设施故障和预算退出。

## 7. classic 与 mini 的设计对照

| 维度 | classic SWE-agent | mini-SWE-agent |
| --- | --- | --- |
| ACI | 专用 Commands + Parser + Bundle | 主要是 Bash Tool |
| Context | 可组合 History Processor | 线性 messages，模型适配器做格式化 |
| Shell | SWE-ReX 持久 Session | 每 Action 新子 shell / `docker exec` |
| 环境 | Deployment + Repo reset | Local/Docker 等轻量后端 |
| 状态 | history、messages view、trajectory 分离 | messages 为中心 |
| 适合 | ACI 消融、完整 Benchmark、历史策略 | 教学、最小基线、快速扩展 |

不要得出“mini 更新，所以 classic 没价值”的结论。mini 是更清晰的基线；classic 保存了专用编辑接口、History Processor 和可配置 ACI 如何改变 Agent 行为的工程样本。最佳阅读顺序是先 mini 理解闭环，再 classic 研究界面设计。

## 8. 建议实验

固定同一模型和任务，只切换三项：Bash-only vs 专用编辑工具、完整历史 vs Last-N Observation、持久 shell vs 独立 shell。记录 resolved、格式错误、工具步数、Token、环境污染和恢复次数。

这比笼统比较“classic 和 mini 谁更强”更有意义，因为它把差异归因到可控的 Harness 变量。
