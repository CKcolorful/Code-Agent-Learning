# OpenHands 详读：从算法原型到可运行的 Agent 平台

论文：[OpenHands: An Open Platform for AI Software Developers as Generalist Agents](https://arxiv.org/abs/2407.16741)

官方代码：[OpenHands/OpenHands](https://github.com/OpenHands/OpenHands)

项目文档：[docs.openhands.dev](https://docs.openhands.dev/)

作者：Xingyao Wang 等｜首次提交：2024 年 7 月

## 一句话结论

OpenHands 的核心贡献不是某个新的推理算法，而是一套可组合的平台抽象：Agent 只负责决定下一动作，Event Stream 保存所有状态变化，Runtime 在隔离环境执行动作，Controller 协调循环。这样不同 agent、工具、用户界面和 benchmark 才能共享同一套运行基础设施。

## 1. 为什么“能跑的 agent”需要平台

研究 demo 往往可以在一个脚本里完成：拼 prompt、调用模型、执行 shell、循环。但一旦系统需要支持真实用户和多个 benchmark，就会出现横切问题：

- shell、Python、浏览器是否共享同一工作区和进程状态；
- 如何隔离不可信代码、限制网络和资源；
- 用户中途发消息后，agent 如何看到；
- 怎样暂停、恢复、重放一条轨迹；
- action 失败、进程超时或 runtime 重启时，状态是否一致；
- 不同 agent 怎样复用工具，而不各写一套执行器；
- benchmark adapter 怎样拿到 patch、日志和最终状态。

OpenHands 把这些问题视为平台职责。论文的研究价值在于给出一组边界清晰的抽象，而不是只报告一个 SWE-bench 数字。

## 2. 四个核心对象

```text
                 actions
Agent  ------------------------------>
  ^                                     Runtime
  |                observations           |
  +---------------------------------------+
               Event Stream
                    ^
                    |
              User / Controller
```

更准确地说，所有参与者不直接互调，而是围绕 Event Stream 读写事件。

### Agent

Agent 接收当前状态和历史事件，生成下一条 Action。它可以是 CodeActAgent，也可以是未来的规划型、多代理或专用 agent。

### Controller

Controller 管理 agent 循环：把事件交给 agent、限制迭代、处理暂停/结束、连接用户与 runtime。它是控制平面，不负责具体 shell 语义。

### Event Stream

Event Stream 是追加式事件日志，记录 Action、Observation、用户消息和状态变化。它既是 agent 的上下文来源，也是 UI、评测、调试和重放的统一事实源。

### Runtime

Runtime 是执行平面。它接收可执行 Action，在 sandbox 内运行，然后产生对应 Observation。Docker runtime、远程 runtime 或其他后端可以实现同一接口。

## 3. Event-sourced 设计为什么关键

传统脚本常把当前状态分散在 Python 变量、shell 进程、日志文件和 UI 内。出错后很难回答“第 18 步到底发生了什么”。

OpenHands 把交互写成事件序列：

```text
MessageAction(user request)
CmdRunAction("rg ...")
CmdOutputObservation(exit_code=0, output="...")
FileEditAction(...)
FileEditObservation(...)
MessageAction(user clarification)
AgentFinishAction(...)
```

这样带来四个能力：

1. **可观测**：UI、日志和评测读取同一事件，不需猜内部状态。
2. **可重放**：可从历史事件恢复 agent 上下文或分析决策。
3. **可插入人类反馈**：用户消息也是事件，不需要特殊旁路。
4. **可扩展**：新增 action/observation 类型，而不重写所有 agent。

但 Event Stream 不是完整世界状态。文件系统、进程内存和外部网站仍在 runtime 中；若要严格重放，还需要固定镜像、仓库 commit、环境变量、随机种子和外部服务响应。

## 4. Action / Observation 类型逐项理解

论文列出多种通用动作。

### `CmdRunAction`

在持久 shell 中执行命令，用于搜索、构建、测试和 git 操作。Observation 至少要包含输出和退出状态。持久 shell 允许 `cd`、环境激活等状态跨调用保留，但也增加隐藏状态，需要日志化当前目录和会话。

### `IPythonRunCellAction`

在持久 Jupyter/IPython 内核执行代码，适合数据探索、计算和保留 Python 对象。它与 shell 的用途不同：shell 操作项目，Notebook 更适合交互分析。

### `BrowserInteractiveAction`

驱动浏览器读取网页、点击和输入。对需要查文档、操作 Web 应用或完成 WebArena 类任务的 generalist agent，这是第一等工具，而不是临时爬虫脚本。

### `MessageAction`

向用户发送消息或接收用户输入。把对话也建模成 action/event，意味着“询问澄清”和“汇报结果”可以进入同一轨迹。

### `AgentFinishAction`

显式声明任务结束。平台可在此收集最终文本、工作树 patch 和评测产物。

### `AgentDelegateAction`

把子任务委派给另一个 agent。论文展示了委派扩展点，但多 agent 不会自动提升：还需要任务边界、上下文传递、共享工作区冲突与结果合并协议。

Action 与 Observation 应成对设计。例如命令动作的观察不能只是一串文本，还应表达退出码、超时和截断；编辑观察应表达修改是否真正落盘。

## 5. Runtime 与 Sandbox：真正执行发生在哪里

论文中的 runtime 通过 action execution API 在 Docker sandbox 中执行代码。主要资源包括：

- 持久 Bash 会话；
- Jupyter/IPython 内核；
- 浏览器环境；
- 挂载的 workspace；
- 文件读写与辅助技能。

Sandbox 有三个不同目标，不能混为一谈。

### 可复现性

固定镜像、依赖与系统包，使同一 action 在不同机器上尽量得到相同结果。

### 安全隔离

agent 会执行不可信仓库代码和自己生成的命令。容器边界、非特权用户、资源限制、网络策略和凭据隔离能降低宿主风险。

### 生命周期管理

平台需要创建、暂停、恢复和销毁 runtime，并处理长命令、后台进程和崩溃。只用 `subprocess.run` 很难覆盖这些状态。

容器不是自动安全证明。挂载宿主敏感目录、传入云凭据或开放 Docker socket 都会突破隔离；生产系统仍需最小权限和审计。

## 6. Workspace、终端与浏览器如何保持一致

一个 generalist agent 可能先在浏览器读 issue，再在 shell 修改仓库，又用 Python 分析输出。若三种工具不共享任务 identity 和文件状态，就会产生“浏览器看到版本 A，shell 正在改版本 B”的错位。

平台应显式定义：

- workspace 在 runtime 内的路径；
- 宿主挂载是只读还是读写；
- shell 与 notebook 的当前目录；
- 多 agent 是否共享同一工作树；
- runtime 重启后哪些文件和进程保留；
- 最终 patch 从哪个 git 基线计算。

OpenHands 的价值在于把这些约束放进 runtime/controller 层，使 agent 算法可以专注于决策。

## 7. AgentSkills：何时用专用工具

OpenHands 提供 AgentSkills，处理模型直接通过低级命令不容易稳定完成的操作，例如带窗口的文件编辑、读取图像或 PDF。

设计原则不是“为每种动作都造工具”。专用 skill 应在以下情况出现：

- 低级操作需要脆弱、多轮命令；
- 输出需要严格裁剪或结构化；
- 动作失败必须原子回滚；
- 需要外部模型或非文本解析器；
- 相同能力被多个 agent 复用。

这延续了 SWE-agent 的 ACI 思路，但被平台化：skill 不属于某一个 prompt，而是 runtime 可提供的能力组件。

## 8. CodeActAgent 的思路

论文平台中的代表 agent 使用 CodeAct 风格：让模型生成可执行代码/命令作为动作，而不是在大量预定义 JSON 工具之间切换。

优势是表达力强：shell 和 Python 能组合现有程序，工具扩展不必为每个命令新增 schema。风险是动作自由度大、输出难预测、安全边界更重。

因此 OpenHands 与 SWE-agent 看似相反：一个强调通用代码动作，一个强调专用 ACI。实际上二者可以共存：

- 通用 shell/Python 提供开放世界能力；
- 专用 file editor、浏览器操作和解析 skill 提供高频动作的可靠性；
- runtime 统一执行、安全与观察格式。

## 9. Context 管理：Event Stream 不等于把全部事件塞给模型

Event Stream 可以保存完整历史，但模型上下文仍有限。Controller/agent 必须选择哪些事件进入下一轮：

- 最近的动作与原始观察；
- 对旧阶段的结构化摘要；
- 当前工作树和测试状态；
- 用户的最新约束；
- 必要时从完整历史检索的证据。

这里要区分三种一致性：

1. **日志一致性**：完整事件没有丢失。
2. **模型上下文一致性**：输入给模型的摘要没有与当前状态冲突。
3. **环境一致性**：文件和进程确实对应事件所描述的结果。

只实现第一种还不够。比如编辑成功事件被保留，但随后用户手动改了文件；模型若不重新读取，就会基于过期状态继续行动。

## 10. 多 Agent 与委派的真实难点

`AgentDelegateAction` 让主 agent 可以把任务交给子 agent，但论文提供的是抽象接口，不是多 agent 正确性的保证。

实际系统至少要解决：

- 子任务是否相互独立；
- 传递完整仓库还是精简上下文；
- 多个 agent 能否同时编辑同一文件；
- 子 agent 的结论用文本、patch 还是事件返回；
- 谁负责最终测试和冲突解决；
- 委派成本是否超过并行收益。

最安全的初始模式通常是只读并行探索或独立工作树，最后由单一 owner 合并。

## 11. Benchmark integration 为什么是平台接口

OpenHands 论文覆盖 15 个 benchmark，包含软件工程、网页浏览与通用辅助任务。支持 benchmark 不只是写一个启动命令，还要提供 adapter：

```text
dataset instance
  -> initialize runtime/workspace
  -> create user task event
  -> run controller loop
  -> collect final answer/patch
  -> invoke benchmark evaluator
  -> save trajectory and metrics
```

平台化的好处是 agent 算法与 benchmark 环境解耦。相同 agent 可跨任务运行；相同 benchmark 也能比较不同 agent，而不必重写 sandbox 与日志。

## 12. 测试策略：为什么要 Mock LLM

端到端 agent 测试昂贵且不确定。论文/项目强调使用 mock LLM 做集成测试：预先规定模型每一步输出什么动作，再验证 controller、runtime 和 event stream 是否按预期工作。

这样能独立测试：

- action parser 是否正确；
- runtime 是否返回对应 observation；
- 超时与异常是否产生事件；
- finish 是否停止循环；
- 轨迹是否可序列化；
- benchmark adapter 是否收集正确 patch。

Mock LLM 不能测模型能力，却能防止平台 bug 被误判成推理失败。

## 13. 论文结果该如何看

OpenHands 报告多个 agent 在多个 benchmark 上的结果，用于证明平台能够承载不同任务和方法。与专门追求 SWE-bench SOTA 的论文相比，这里的首要贡献是覆盖面、统一性与可扩展性。

阅读分数时要问：

- 使用哪个 agent 和模型，而非把成绩统称为“OpenHands”；
- runtime 提供哪些工具与网络权限；
- benchmark 版本和最大迭代数；
- 是否使用专用 prompt/skills；
- 失败来自 agent 还是 adapter/runtime。

OpenHands 是平台名，不是单一固定 policy。不同配置的成绩不能简单归因于平台本身。

## 14. 从论文平台到生产系统还缺什么

- **身份与凭据隔离**：不同用户、仓库和外部服务的权限边界。
- **危险动作策略**：删除、发布、支付、生产部署等动作需要审批。
- **资源治理**：CPU、内存、磁盘、网络、并发和 LLM 成本限额。
- **持久化恢复**：runtime 崩溃后事件与真实文件状态如何对账。
- **供应链安全**：执行陌生仓库安装脚本可能下载任意代码。
- **可观测性**：按 action、模型调用、环境失败和用户等待分解时延。
- **多租户隔离**：容器逃逸、缓存污染和跨任务数据泄漏。

论文提供骨架，不等于这些生产问题已经自动解决。

## 15. 与前后论文的关系

- ReAct 给出 Thought/Action/Observation 的最小认知循环。
- SWE-agent 证明 ACI 影响模型有效能力。
- Agentless 说明开放式循环可被结构化 pipeline 替代。
- OpenHands 让这些不同 policy 都能运行在统一 Event Stream 与 Runtime 上。
- SWE-Gym 再利用可执行环境和轨迹训练更适合 agent 行为的模型。

可以把 OpenHands 看成“机制中立”的承载层：agent 可以是 ReAct 式、CodeAct 式、pipeline 式或委派式。

## 16. 官方源码怎么读

项目发展很快，当前源码会比论文版本更复杂。建议按架构对象而不是 UI 页面阅读：

1. [`openhands/events/`](https://github.com/OpenHands/OpenHands/tree/main/openhands/events)：Action、Observation 与事件模型。
2. [`openhands/runtime/`](https://github.com/OpenHands/OpenHands/tree/main/openhands/runtime)：runtime 接口与不同执行后端。
3. [`openhands/controller/`](https://github.com/OpenHands/OpenHands/tree/main/openhands/controller)：agent loop、状态和事件协调。
4. [`openhands/agenthub/`](https://github.com/OpenHands/OpenHands/tree/main/openhands/agenthub)：不同 agent 实现。
5. [`evaluation/`](https://github.com/OpenHands/OpenHands/tree/main/evaluation)：benchmark adapter 与评测脚本。

用一个最小任务做 tracing：在 `step()` 断点观察 Action 如何进入 Event Stream，Runtime 如何消费它并写回 Observation，Controller 又如何把新状态交给 Agent。能画出这条链，才算理解平台。

## 17. 常见误读

- **“OpenHands 是一个固定 agent。”** 它是平台，可承载多个 agent、模型和配置。
- **“Event Stream 保存完整日志，所以任务可完美重放。”** 外部世界与进程状态仍需固定或快照。
- **“Docker 就等于安全。”** 错误挂载、特权模式和凭据注入仍可破坏边界。
- **“通用 shell 能替代所有专用工具。”** 高频脆弱操作仍受益于 AgentSkills/ACI。
- **“支持多 agent 就会自然提分。”** 委派还需隔离、合并和最终责任机制。
- **“benchmark 数字代表平台本身的智能。”** 成绩来自具体 policy、模型、工具和预算组合。

## 18. 可复现练习

### 练习一：实现最小 Event Stream

定义 `Action`、`Observation`、`Message` 三类事件，追加写入 JSONL。做一个 shell runtime 和回放器。验证进程失败、超时、用户插话和 finish 都有显式事件。

### 练习二：Mock LLM 集成测试

固定三步输出：查看文件、运行测试、finish。不要调用真实模型，测试 controller 是否严格执行三步并保存完整轨迹。再让第二步超时，检查异常是否可恢复。

### 练习三：状态一致性故障注入

在 edit observation 写入后，模拟 runtime 重启或外部修改文件。设计 reconciliation：比较事件中的文件 hash 与实际 hash，冲突时要求 agent 重新读取。

## 19. 读完后的检查题

1. Agent、Controller、Runtime 各自持有什么状态，为什么不应合成一个类？
2. Event Stream 能重放哪些东西，不能重放哪些东西？
3. shell 与 notebook 都持久化时，怎样避免隐藏状态失控？
4. 为什么 benchmark adapter 是平台的一部分，而不是一次性脚本？
5. 多 agent 共享工作树时，最先需要解决的冲突是什么？

## 20. 最终要带走的观点

OpenHands 把 Code Agent 的重点从“一条聪明轨迹”提升到“一个能长期承载轨迹的系统”：**决策、事件、执行和评测必须解耦，完整历史必须可观测，真实执行必须隔离，工具和 benchmark 必须能复用。** 没有这些平台层能力，模型分数越高，系统也可能越难调试、恢复和安全交付。
