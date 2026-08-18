# DeepSeek Harness 源码解读

> 固定版本：[`99f6f02f`](https://github.com/deepseek-ai/deepseek-harness/tree/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca)（0.1.0-rc.7 附近）
>
> 阅读范围：Cordis 组合、Core Agent/Loop/Session/Tools、Base 与 Headless Bundle
>
> 注意：项目处在快速演进期，本文结论只对固定 commit 负责

DeepSeek Harness 最值得研究的不是某个具体工具，而是它对“核心”的重新定义：模型适配器、Agent Loop、Session、Tool Registry、Sandbox 和 UI 都作为插件挂到 Cordis Context，不存在必须修改的单一特权内核。

## 先建立三个概念

1. **Context**：插件共享服务和事件的作用域；
2. **Effect**：注册服务、监听器或资源时产生的可撤销副作用；插件卸载时逆序清理；
3. **Composition**：Profile 叠加 Bundle 和用户 Patch，最终得到实际运行的插件树。

“Everything is a plugin”只有在生命周期、作用域和冲突都可控时才有意义，否则只是全局 Service Locator。

## 源码地图

| 路径 | 作用 |
| --- | --- |
| [`docs/architecture.zh.md`](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/docs/architecture.zh.md) | 官方架构约束与事件域 |
| [`bundle/base/cordis.patch.yml`](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/bundle/base/cordis.patch.yml) | 默认模型、Session、工具、沙箱、审批等真实组合 |
| [`core/agent-loop/src/agent.ts`](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/core/agent-loop/src/agent.ts) | `ReactLoopAgent`状态机 |
| [`core/session/src/index.ts`](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/core/session/src/index.ts) | Append-only SessionEvent、Surface 与投影 |
| [`core/tools/src/index.ts`](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/core/tools/src/index.ts) | 作用域工具注册和执行 Pipeline |
| [`bundle/headless/src/index.ts`](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/bundle/headless/src/index.ts) | 最短的一次性产品调用链 |

## 推荐阅读

1. [Cordis、Profile 与能力组合](./01-Cordis-and-Composition.md)
2. [Turn、SessionEvent 与 Tool Pipeline](./02-Turn-Session-and-Tools.md)
3. [源码实验](./03-Labs.md)

## 读完应能回答

- 为什么 Bundle 的 YAML 比某个 `main.ts`更能说明产品包含哪些能力？
- 为什么“模型可见即已记录”是 Session 的强不变量？
- 为什么 SessionEvent 与实时 `agent/*`事件不能合并为一种？
- 为什么 Tool Pipeline 同时需要 waterfall、guard 和 scope？
- 插件卸载时，怎样证明它注册的工具、监听器和后台资源都已撤销？

这套架构适合能力组合和产品变体，但它把复杂度从类继承转移到了插件图、事件语义和生命周期所有权。阅读重点应该是“谁拥有副作用”，而不是只数 package 数量。
