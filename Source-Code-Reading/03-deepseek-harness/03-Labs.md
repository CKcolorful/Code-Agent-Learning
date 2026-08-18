# DeepSeek Harness 源码实验

这些实验围绕“组合是否可解释、作用域是否隔离、卸载是否完整、日志是否可重放”设计。固定 commit 后再运行，避免开发预览期的接口漂移。

## 实验 1：打印最小插件图

以 headless profile 为基线执行 `--dump-config`，把条目归为 Model、Agent、Session、Tool、Execution、Policy、Persistence、UI 八类。然后用 overlay：

- 替换一个配置；
- 禁用一个工具插件；
- 增加一个自定义插件；
- 对比有效配置，而不是只对比 YAML 输入。

验收结果要解释“最后哪个 layer 赢了”以及为什么。

## 实验 2：插件副作用回滚

写一个插件，同时注册工具、事件 listener、timer 和临时服务。覆盖三条路径：正常卸载、初始化到一半抛错、重复 reload。

卸载后断言：

- 工具 schema 不再进入 prompt；
- listener 不再收到事件；
- timer/后台 Promise 不再运行；
- 服务从该 scope 消失但父 scope 不受影响；
- disposer 只执行一次且按逆序释放。

这比“插件能加载”更能检验框架质量。

## 实验 3：Per-agent 工具隔离

创建两个 Agent，在 A 的 `agent.ctx`注册同名专用工具，B 不注册。检查两者 System Prompt 的工具 schema 和实际 execute：A 可见并可调用，B 应得到 unknown/不可见结果。

再尝试在全局重复注册同名工具，确认系统明确报冲突，而不是静默覆盖。

## 实验 4：Session Replay 等价性

使用 scripted LLM 运行一次包含 chunk、tool call、tool result 和 completed turn 的会话，flush 到 JSONL，重新加载并比较：

- `deriveMessages()`结果；
- Session Surface 顺序；
- request header；
- turn end reason；
- 最后 assistant 文本。

故意制造 seq 缺口、非法 JSON 值和缺少 surface metadata 的事件，确认问题在恢复边界失败，而不是晚到下一次模型请求才暴露。

## 实验 5：Tool Pipeline 故障注入

对同一 Fake Tool 分别注入：参数 getter 抛错、pre-execute deny、approval cancel、guard deny、tool body 抛错、post-execute 改写、执行中 Abort。

输出统一表格：

```text
case | body invoked | post-execute seen | result code | session event | deferred context
```

重点验证执行前取消和执行中取消的结果不同，以及被拒绝的动作不会进入 tool body。

## 建议提交物

```text
labs/deepseek-harness/
├── plugin-lifecycle.spec.ts
├── scoped-tools.spec.ts
├── session-replay.spec.ts
├── tool-pipeline.spec.ts
├── patches/
└── RESULTS.md
```

如果实验失败，应先判断是文章理解错误、固定版本真实缺陷，还是测试绕过了官方组合入口。源码解读的价值就在于结论可以被这些实验推翻和修正。
