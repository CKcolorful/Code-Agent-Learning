# Session Tree、Compaction 与 Extension

## 1. Session 不是 Message 数组

[`SessionManager`](https://github.com/earendil-works/pi/blob/e5dde9a76bfec3c4eff764d1b6db3b60e5dd0b30/packages/coding-agent/src/core/session-manager.ts)保存多种 Entry：message、model change、thinking level change、compaction、branch summary、custom entry 和 session info 等。每条 Entry 有 `id`、`parentId`与 timestamp。

```text
root message
   ├─ assistant A
   │    └─ tool result A
   │         └─ current leaf
   └─ assistant B
        └─ alternate leaf
```

当前上下文不是“整个文件最后 N 行”，而是从当前 leaf 沿 parent 链回到 root 的一条路径。这让 fork/树形导航不必复制全部历史，切换分支也不会删除原分支。

## 2. Append-only 带来的约束

切换模型、压缩、扩展自定义状态都作为新 Entry 追加。好处是历史决策可审计，坏处是“当前有效状态”需要 fold/projection 计算。任何只读文件尾部的脚本都可能误解分支；统计工具必须先选择 active path。

## 3. Compaction 不是删除旧消息

Compaction Entry 至少保存 summary、`firstKeptEntryId`和 `tokensBefore`。构造当前上下文时：

1. 找 active path 上最新 compaction；
2. 以 summary 代表被压缩的前缀；
3. 保留从 `firstKeptEntryId`开始的精确尾部；
4. 加入 compaction 之后的新 Entry。

```text
[被摘要的旧前缀] [需要精确保留的最近消息] [压缩后新增消息]
        ↓                    │                  │
   compaction summary -------┴------------------┘
```

`firstKeptEntryId`比数组下标稳定：追加新 Entry 或加载分支后，逻辑边界仍指向同一身份对象。

## 4. 三类自动压缩

`AgentSession`区分：

- **overflow**：模型明确报告上下文溢出，移除失败 assistant，压缩后最多重试一次；
- **truncated response**：输出因长度截断，可压缩并尝试恢复；
- **threshold**：使用量接近阈值，响应完成后预防性压缩，不必重跑已完成回答。

它还检查 assistant usage 是否位于最新 compaction 之后，避免拿旧 usage 触发“刚压完又压一次”。这体现了 Context 数据的时效性：Token 统计必须绑定产生它的历史版本。

## 5. Manual 与 Auto Compaction 共用纯函数

`/compact`、RPC 和 Extension 走手动入口；阈值/溢出走自动入口。两条路径都可以先触发 `session_before_compact`，允许扩展取消或提供自定义 summary，最终共用底层 [`compact()`](https://github.com/earendil-works/pi/blob/e5dde9a76bfec3c4eff764d1b6db3b60e5dd0b30/packages/coding-agent/src/core/compaction/compaction.ts)。

把“选择何时压缩”留在 Session，把“给定路径如何切分与摘要”放进较纯的模块，有利于测试。副作用边界也更清楚：SessionManager 负责追加 Entry，压缩函数不直接控制 UI。

## 6. ExtensionRunner 的能力面

[`ExtensionRunner`](https://github.com/earendil-works/pi/blob/e5dde9a76bfec3c4eff764d1b6db3b60e5dd0b30/packages/coding-agent/src/core/extensions/runner.ts)把核心动作绑定给 Extension Runtime，包括：

- 注册工具、命令、快捷键和 Provider；
- 发送 user/custom message；
- 读取或切换模型和 thinking level；
- 获取/切换 active tools；
- 触发 compact、fork、new session、reload；
- 订阅 Session、Agent 与工具生命周期事件；
- 在支持的模式下注入 UI。

工具同名时采用确定性规则，诊断冲突，而不是静默让加载顺序产生不可见覆盖。扩展报错通过 error listener 汇总，避免一个 UI 扩展直接摧毁主循环。

## 7. 扩展性不等于安全性

Extension 与 Agent 运行在同一 Node.js 进程，能获得宿主授予它的 JavaScript 能力。项目资源还涉及 trust 判断，但这不构成操作系统安全隔离。

因此应区分：

- Extension API 限制“通过官方上下文能做什么”；
- Project Trust 决定“是否加载项目提供的代码”；
- OS/container sandbox 决定“恶意代码最终能访问什么”。

前两者不能代替第三者。对外部分发 Extension 时还要考虑来源、版本锁、审计和撤销。

## 8. Pi 的核心取舍

Pi 选择“有观点的最小默认能力 + 强扩展宿主”，而不是把每种工作流放进核心。这降低核心功能膨胀，但把兼容压力转移到事件、Session Entry 和 Extension API。API 一旦成为生态契约，修改事件时序或 Entry 语义就需要迁移策略。
