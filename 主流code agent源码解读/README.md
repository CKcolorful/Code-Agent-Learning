# Code Agent 源码阅读路线

这一部分不做“功能介绍”或逐行翻译，而是沿真实调用链回答五个问题：请求从哪里进入、运行状态由谁持有、模型与工具怎样往返、上下文怎样持久化、系统凭什么停止。

源码会持续变化，因此每套解读都固定到一个 commit。文中的路径用于建立导航，链接默认指向固定版本而不是易漂移的 `main`。解读只引用少量必要接口，其余使用流程图和伪代码重新表达；如需复制上游代码，请继续遵守各项目许可证。

## 阅读对象与固定版本

| 项目 | 固定 commit | 语言 | 最值得研究的主线 | 许可证 |
| --- | --- | --- | --- | --- |
| [SWE-agent 家族](./01-mini-swe-agent/README.md) | mini [`25941c8`](https://github.com/SWE-agent/mini-swe-agent/tree/25941c89cfbc91eb40b3f8756348c91d9977d57e) / classic [`3ea751c`](https://github.com/SWE-agent/SWE-agent/tree/3ea751c087f32b16e039a2233dd6eefecef325d5) | Python | 极小基线与经典 ACI、History Processor、SWE-ReX | MIT |
| [Pi Agent](./02-pi-agent/README.md) | [`e5dde9a`](https://github.com/earendil-works/pi/tree/e5dde9a76bfec3c4eff764d1b6db3b60e5dd0b30) | TypeScript | 流式 Agent Core、Session Tree、Compaction、Extension | MIT |
| [DeepSeek Harness](./03-deepseek-harness/README.md) | [`99f6f02`](https://github.com/deepseek-ai/deepseek-harness/tree/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca) | TypeScript | Cordis 插件树、事件溯源、可替换能力 seam | MIT |
| [Codex](./04-codex/README.md) | [`f5e9d66`](https://github.com/openai/codex/tree/f5e9d66851a20311b8385204686990c6c5960014) | Rust | Thread/Session/Turn、工具编排、审批与系统沙箱 | Apache-2.0 |
| [横向比较](./05-cross-agent-comparison/README.md) | 上述四个版本 | — | 控制面、状态、扩展、安全与复杂度 | — |

> 固定版本是本系列的“可复现阅读基线”，不代表项目最新版本。升级文章时应进行一次版本审计，不能只替换 SHA。

## 建议顺序

```text
最小 Harness
   ↓
mini-SWE-agent：看清最小闭环
   ↓
Pi：看闭环如何长出交互、会话与扩展
   ↓
DeepSeek Harness：看整个产品如何由插件组合
   ↓
Codex：看生产级安全、恢复和并发如何改变结构
   ↓
横向比较：从项目名抽象回设计选择
```

不要一开始从 Codex 仓库根目录顺序阅读。大型 Agent 的复杂度主要来自生命周期交叉：一次工具调用会同时经过协议、策略、审批、沙箱、进程、事件和持久化。先在 mini-SWE-agent 中建立最小心智模型，再逐步增加维度，阅读成本会低很多。

## 每套解读包含什么

- `README.md`：版本、源码地图、最短阅读路径和关键结论；SWE-agent 额外比较 classic 与 mini；
- `01-*`：入口、对象关系与一次完整调用链；
- `02-*`：该项目最有辨识度的机制和失败边界；
- `03-Labs.md`：通过 trace、故障注入和小修改验证理解；
- 横向比较：把相同概念映射到四套源码，避免被类名和语言差异干扰。

## 源码阅读的证据标准

一篇可信的源码分析至少要同时给出：

1. **静态证据**：入口、关键类型、调用者与被调用者的固定版本链接；
2. **动态证据**：实际运行日志、事件序列、Trajectory 或测试结果；
3. **反事实实验**：改变一个条件，观察行为是否符合解释；
4. **边界说明**：哪些结论来自源码，哪些是作者推断，哪些未覆盖；
5. **版本边界**：commit、日期、许可证和上游迁移提示。

只画架构图容易把设计愿望误当成真实实现；只贴代码又看不出模块为何存在。有效做法是：先提出行为问题，再沿数据和控制流寻找证据，最后用实验让解释可以被证伪。

## 与 01–14 架构系列的对应

| 理论模块 | mini-SWE-agent | Pi | DeepSeek Harness | Codex |
| --- | --- | --- | --- | --- |
| Agent Loop | `DefaultAgent` | `agent-loop.ts` | `ReactLoopAgent` | `session/turn.rs` |
| Context Manager | `messages` 列表 | Session + Compaction | SessionEvent 投影 | `ContextManager` + Compaction |
| Tool Router | Model Action 解析 | `AgentTool` 调度 | `ctx.tools` Pipeline | `ToolRouter` + Orchestrator |
| Sandboxed Executor | Environment 后端 | 工具执行器，由用户隔离 | Sandbox/Shell/FS seam | 跨平台 Sandbox + Permission Profile |
| Verifier | Submit 协议，外部评测 | Hook/Extension 可加门禁 | 事件与插件组合 | Task、Hook、Review 与完成事件 |
| Observability | Trajectory JSON | Agent/Session Event | Append-only SessionEvent | Protocol Event + Rollout + Telemetry |

完成本系列后，读者应该能够拿到一个陌生 Code Agent 仓库，先定位入口、状态真源、模型边界、工具路径和终止协议，而不是从 prompt 文件猜它的架构。
