# 四类 Code Agent Harness 横向比较

比较 Harness 不能只列“是否支持 MCP/沙箱/多 Agent”。真正影响行为的是：状态真源在哪里、输入何时进入、工具如何受控、失败如何收敛、历史如何变成下一次模型请求。

本章基于本系列固定版本比较，不宣称代表后续版本。

## 1. 核心控制对象

| 项目 | 最小控制对象 | 产品级控制对象 | 一次工作的边界 |
| --- | --- | --- | --- |
| mini-SWE-agent | `DefaultAgent` | CLI/Benchmark Runner | 从 system/user 到 `role=exit` |
| classic SWE-agent | `DefaultAgent` + `SWEEnv` | RunSingle/Batch | 一个 problem attempt |
| Pi | `Agent` | `AgentSession` | Agent Run，可被 follow-up 续起 |
| DeepSeek Harness | `ReactLoopAgent` | Cordis 插件树 | Turn，含多个 Step |
| Codex | `run_turn` | Thread + Session + Task | Turn，受 Session 控制 |

代码越成熟，“Agent”越不等于一个类。产品层还需要会话、审批、持久化、输入队列、UI 协议和资源所有权。

## 2. 状态真源

| 项目 | 模型历史 | 持久轨迹 | 世界状态 | 可恢复性 |
| --- | --- | --- | --- | --- |
| mini | `messages` | Trajectory JSON | Local/Docker FS | 偏分析，不是完整 resume |
| classic SWE-agent | History Processor 投影 | `.traj` | SWE-ReX + repo revision | 面向 attempt/replay |
| Pi | active Session path | JSONL Session Tree | cwd + tools | Session/fork/compaction |
| DeepSeek Harness | SessionEvent Surface 投影 | Append-only SessionEvent | 可替换 FS/Shell/Sandbox seam | event replay/fork |
| Codex | ContextManager prompt view | Rollout/Thread Store/Event | workspace + process + environment | Thread resume/recover |

最强的状态原则来自 DeepSeek Harness：“模型可见即已记录”。Codex 的实现更复杂，因为还要兼容多个宿主、协议 item、权限状态与平台环境。Pi 则用 parent-linked Entry 在简单文件中表达树。

## 3. 输入调度

```text
mini：下一步只来自工具 Observation
classic：下一步来自 ACI Observation
Pi：prompt + steering queue + follow-up queue
DeepSeek：Inbox(next-step / next-turn)，inject 可不唤醒
Codex：Submission Op + active-turn Input Queue + start/steer/recover
```

调度越丰富，越需要原子归属和取消语义。用户在工具执行中途补一句话，系统必须知道它属于当前 Step、下一 Turn，还是单独的控制回答。

## 4. 工具控制面

| 项目 | Schema/解析 | Policy | Approval | Execution | Result |
| --- | --- | --- | --- | --- | --- |
| mini | Model Adapter | Prompt 为主 | 无内置强门禁 | Environment | Observation template |
| classic | ToolConfig + Parser | Blocklist/guard | 非核心 | SWE-ReX | Step Observation |
| Pi | AgentTool schema | before/after hook | 可由扩展实现 | 顺序/并行 | ToolResultMessage |
| DeepSeek | Scoped ToolRuntime | waterfall + monotonic guards | ask service | Provider seam | canonical immutable result |
| Codex | Turn ToolRegistry | Exec policy + permissions | 协议化审批 | Orchestrator + OS sandbox | ResponseItem output/event |

从左到右不是单纯“功能越来越多”，而是信任边界改变：Benchmark 容器可以接受简单 Environment；在用户电脑上运行的 Agent 必须把 prompt 建议升级为确定性策略和 OS 强制。

## 5. 上下文策略

- mini：保持消息线性，Observation 模板做长度控制；
- classic：保留原始 history，History Processor 生成请求视图；
- Pi：Session Tree 保留事实，Compaction Entry 替代旧前缀并保留精确尾部；
- DeepSeek：SessionEvent → Surface → deriveMessages，Compaction 作为插件化事件；
- Codex：ContextManager 维护规范化 ResponseItem、history version、Token 和 World State baseline，本地/远程压缩重写历史。

共同趋势是把 durable truth 与 model view 分开。上下文窗口只是模型视图的预算，不应决定系统丢弃审计事实。

## 6. 扩展哲学

| 项目 | 主要扩展点 | 适合 |
| --- | --- | --- |
| mini | Python Protocol/替换类 | 教学、研究原型 |
| classic SWE-agent | Config、Tool Bundle、Hook、History Processor | ACI 实验 |
| Pi | Extension API、Skills、Prompt、Package | 个人化终端产品 |
| DeepSeek Harness | Cordis Plugin、Service、Event、Profile/Bundle | 多产品组合与热替换 |
| Codex | MCP、Skills、Plugins、Hooks、动态工具、Core crate | 受控生态与多宿主 |

Pi 倾向“稳定核心 + 丰富宿主 API”；DeepSeek 把核心本身也插件化；Codex 在生产内核中保留强约束，并通过协议扩展外部能力。三者没有绝对优劣，取决于谁被允许替换安全关键路径。

## 7. 安全成熟度不等于默认安全

- mini Local Environment 和 Pi Extension 都以宿主进程权限运行，必须额外隔离；
- classic SWE-agent 多用于 Benchmark Deployment，容器隔离边界由 SWE-ReX 配置决定；
- DeepSeek Harness 已组合 Sandbox/Approval seam，但最终强度仍取决于所选 Provider 和 Profile；
- Codex 将 Permission Profile、Approval、Network 与平台 Sandbox 串联，仍需正确配置和用户理解授权范围。

评价时要检查 enforcement 点，不要因为类型名叫 Sandbox 就默认安全。

## 8. 应该借鉴什么

- 做教学 Harness：借 mini 的三个 Protocol 和可读闭环；
- 做 ACI 研究：借 classic SWE-agent 的 ToolConfig 与 History Processor 消融；
- 做可定制 CLI：借 Pi 的通用 Agent Core、Session Tree 与 Extension Runner；
- 做多形态产品平台：借 DeepSeek 的 Profile/Bundle、Scope 和可逆 Effect；
- 做本地生产 Agent：借 Codex 的 Thread/Session 协议、审批与 OS Sandbox 分层。

不要把五套设计全部塞进一个项目。每个抽象都要支付配置、迁移、测试和 Debug 成本；只有出现对应问题时才值得引入。

继续阅读：[架构决策矩阵](./01-Architecture-Decision-Matrix.md)与[版本升级协议](./02-Version-Upgrade-Protocol.md)。
