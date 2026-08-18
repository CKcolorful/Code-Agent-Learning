# Pi Agent 源码实验

Pi 的实验重点不是重新实现 Agent，而是验证事件、队列、Session 与扩展契约。优先使用仓库已有 Vitest 和 Mock Stream，减少真实模型噪声。

## 实验 1：重建一次 Event Timeline

订阅低层 Agent 事件，用固定模型产生“文本 + 两个工具调用 + 最终文本”。记录：

```text
sequence | event type | message/tool id | state.isStreaming | pendingTools
```

分别在 `toolExecution=parallel`与顺序模式运行。验证：

- `agent_start/end`是否各一次；
- 每个 message 是否有 start/end；
- `turn_end`是否等待工具结果；
- 并行完成顺序是否影响写回消息顺序；
- listener 返回 Promise 时 Agent 何时变成 idle。

## 实验 2：Steering 与 Follow-up 竞态

用可控 Deferred Promise 暂停模型流：

1. Agent 正在生成时 enqueue steering；
2. 释放流，检查 steering 在哪次请求前进入；
3. Agent 即将结束时 enqueue follow-up；
4. 对比 queue mode 为 one-at-a-time 与 all；
5. 取消当前 Run，检查剩余队列的处理方式。

结果应给出实际 message 序列，不能只断言“成功”。

## 实验 3：Session Tree 与 Compaction 投影

构造一棵至少包含两个分支的 Session：主分支产生 compaction，另一分支保留原历史。分别选择两个 leaf，输出：

- active path Entry ID；
- model-visible message；
- latest compaction；
- usage/cost 总计。

随后故意把 compaction 的 `firstKeptEntryId`指向非 active path，验证加载或投影是否拒绝不一致状态。这个实验能暴露“文件中的 Entry”和“当前上下文”不是同一概念。

## 实验 4：写一个 Verifier Extension

实现扩展：当 Agent 准备结束且工作树存在 diff 时，要求最近一次测试命令 exit code 为 0，否则追加反馈消息而不是接受结束。

至少覆盖：

- 无 diff：不强制测试；
- 有 diff、没测试：阻止；
- 测试成功后又编辑：旧证据失效；
- 测试失败：阻止并返回摘要；
- Extension 自身异常：记录诊断，不伪装成验证成功。

这里不要求把规则贡献到 Pi 核心，而是借 Extension API 验证其扩展边界。

## 实验 5：Compaction 回归

准备一个包含早期约束、若干文件修改和长工具输出的 Session。压缩前后提出同一组检索问题：

- 任务目标是否保留；
- 修改过哪些文件；
- 当前失败测试是什么；
- 哪些细节只能从精确尾部回答；
- summary 是否引入不存在的结论。

同时测量 Token 降幅。好的 Compaction 不只是更短，而是在指定恢复问题上保持足够状态。

## 建议提交物

```text
labs/pi-agent/
├── event-timeline.test.ts
├── queue-race.test.ts
├── session-tree.test.ts
├── verifier-extension.ts
├── compaction-fixtures/
└── RESULTS.md
```

这些实验可以直接转化为简历证据：实现的不是又一个聊天 UI，而是可重复的并发、会话与扩展契约测试。
