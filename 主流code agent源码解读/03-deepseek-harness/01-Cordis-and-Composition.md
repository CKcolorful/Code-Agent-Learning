# Cordis、Profile 与能力组合

## 1. 产品是一棵插件树

DeepSeek Harness 启动时不是实例化一个巨大 `Harness`类，而是把配置层依次应用到空插件列表：

```text
profile 声明的 bundles（按顺序）
  → profile/cordis.patch.yml
  → home/cordis.patch.yml
  → CLI --patch overlays
  → Cordis 加载最终插件树
```

Patch 通过稳定 `id`定位条目，后层可以替换 config 或插入能力。运行 `dsh --profile web --dump-config`得到的有效树，才是实际产品，而不是 README 中的默认能力清单。

## 2. Base Bundle 是可执行架构图

[`dsh-base/cordis.patch.yml`](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/bundle/base/cordis.patch.yml)真实挂载了 LLM、Session、Agent、Agent Loop、持久化、Shell、Sandbox、Approval、FS、Compaction、Skills、MCP、Subagent、Telemetry 等插件。

阅读方式不是从头记住几百行，而是按能力追踪三类角色：

```text
Service Definition：能力接口，例如 shell/fs/sandbox
Service Provider：本地、远程或平台实现
Consumer：暴露给模型的 tool 或其他业务插件
```

例如替换文件系统提供方后，文件工具使用同一接口进入新的执行世界；如果 Shell、PTY 和 LSP 也共享该世界，它们可以整体移动到远程沙箱，而不必 fork 每个工具。

## 3. Context 不是普通 DI Container

插件从 Context 读取服务、注册服务并订阅类型化事件。关键差异是作用域和生命周期：Agent 可以拥有 `agent.ctx`，在该 Context 注册的工具或策略只对这个 Agent 可见；插件卸载时，它通过 Effect 注册的资源应被清理。

作用域解决两个生产问题：

- 同一进程中不同 Agent 可以拥有不同工具和策略；
- 子 Agent 可以继承父层能力，同时在自己的层增加受限能力。

如果注册都落到全局 Map，就无法安全地表达 per-agent variant，也很难在 HMR/卸载时知道该删除谁。

## 4. Effect 是所有权协议

`ctx.effect()`可以注册 disposer，或用 generator 让初始化与清理写在同一处。它表达：这个插件创建的定时器、监听器、服务、Worker 或连接由谁负责回收。

评价一个插件时应检查：

- 初始化中途失败，已经注册的副作用是否回滚；
- disposer 是否可重复调用；
- 异步清理是否被等待；
- 子 Context 释放是否误删父层服务；
- 后台任务是否继续向已卸载 Context 发事件。

插件化系统真正难的不是 `apply(ctx)`，而是失败和卸载路径。

## 5. 三类事件域

架构文档把事件分为：

| 事件域 | 是否持久 | 适合表达 |
| --- | --- | --- |
| Session Event | 是 | 对话中已经发生、恢复后仍成立的事实 |
| Agent Event | 否 | 活跃 Agent 的请求、状态、拦截和续跑 |
| Capability Event | 通常否 | `tools/*`、`fs/*`等能力的策略与适配 |

一条安全决策如果恢复后仍要审计，应产生 SessionEvent；一次 `tools/pre-execute`策略检查则是实时控制点。把两者混用会造成两类错误：把大对象/AbortSignal 塞进持久日志，或把重要事实只广播不落盘。

## 6. Waterfall 与 Observer

Waterfall 监听器必须调用 `next()`才能委托下游，并可替换结果，适合策略链和请求改写；普通 emit/serial 适合观察事实。若把 observer 写成 waterfall 却忘记 `next()`，会意外截断核心行为；若把审批写成普通 observer，它就没有阻止工具的能力。

事件模式本身就是权限语义，不能只靠命名约定。

## 7. 组合的代价

- 有效行为分散在配置和多个插件，静态搜索一个方法不一定看全；
- 加载顺序、service availability 和 scope 影响最终实现；
- 类型声明合并提升扩展体验，也让协议变更跨 package 扩散；
- 大量 package 增加版本和测试矩阵；
- Debug 必须能输出有效配置、服务提供者和监听链。

因此 DeepSeek Harness 需要 `--dump-config`、配置目录、事件生产消费图和大量 invariant tests。高度可组合系统必须同时高度可观测，否则灵活性会变成不可解释性。
