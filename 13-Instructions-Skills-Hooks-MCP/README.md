# Instructions、Skills、Hooks 与 MCP：Code Agent 的扩展控制面

成熟 Code Agent 会同时出现 `AGENTS.md`、`CLAUDE.md`、Skills、Hooks、Tools、MCP 和 Plugins。它们看起来都在“告诉 Agent 怎么做事”，但作用域、加载时机、确定性、权限和分发方式完全不同。

选错承载层会产生两个极端：把所有规则塞进 prompt 导致上下文膨胀；或把需要模型判断的工作硬编码成脆弱脚本。

## 一、先用五个问题选层

1. 这是一次性要求还是长期约定？
2. 需要模型判断还是必须确定性执行？
3. 能力在本地仓库还是外部系统？
4. 应全局、仓库、子目录还是单任务生效？
5. 谁能安装、更新、授权和审计它？

## 二、统一分层

| 层 | 解决什么 | 典型载体 |
| --- | --- | --- |
| Prompt | 当前任务目标与临时约束 | 用户消息 |
| Project Instructions | 每次进入仓库都适用的约定 | `AGENTS.md` / `CLAUDE.md` |
| Skill | 可复用、可按需加载的工作流知识 | `SKILL.md` + scripts/references |
| Hook | 生命周期点上的确定性检查或副作用 | PreToolUse / PostToolUse / Stop |
| Tool | 模型可选择调用的原子动作 | search/edit/test API |
| MCP | 外部工具、资源、prompt 的协议连接 | MCP client/server |
| Plugin | 安装和分发多个能力的包 | manifest + skills/MCP/hooks |

这些层互补而非竞争。一个发布流程可以由 Skill 描述步骤，通过 MCP 操作工单系统，用 Hook 阻止缺少验证的发布，并遵守仓库 Instructions。

## 三、Project Instructions

适合保存：

- 构建、测试和 lint 命令；
- 目录结构和模块边界；
- 反复出现的 review 约束；
- 禁止修改的生成目录；
- 子目录特有规则；
- 完成任务前必须提供的证据。

不适合保存：

- 当前 Issue 的全部需求；
- 长篇通用编程知识；
- 密钥和账号信息；
- 可以由 lint/test 强制的每条格式规则；
- 随时变化的在线数据。

Instructions 要小、可执行、靠近作用域。根目录写全局规则，子目录覆盖局部约定。记录来源和优先级，最终装配后的有效指令应可检查。

### 指令测试

为一条规则准备：应触发案例、安全反例、无关案例。观察 Agent 是否遵守且没有过度泛化。不能只验证“模型能复述 AGENTS.md”。

## 四、Skill：按需加载的流程能力

Skill 适合包含复杂步骤、示例、参考资料和辅助脚本。核心是 progressive disclosure：先暴露名称与描述，匹配任务后读取主说明，需要时再读取 references 或运行 scripts。

```text
skill-name/
├── SKILL.md          # 触发条件、边界、主流程
├── scripts/          # 确定性辅助程序
├── references/       # 按需读取的领域资料
└── assets/           # 模板和静态资源
```

好的 Skill 描述要说明“何时使用”和“何时不要使用”。如果触发条件过宽，所有任务都加载它；过窄则只能靠用户记住显式命令。

Skill 不是权限边界。说明中写“只读”不能阻止工具写入，仍需 Router、Sandbox 和 Policy enforcement。

## 五、Hook：确定性生命周期逻辑

Hook 在已知事件点运行，适合：

- 工具前检查危险参数或 secret；
- 工具后记录审计、规范化结果；
- Context 压缩前保存任务状态；
- Agent 停止前强制运行验收检查；
- Session 开始时加载可验证环境信息；
- Subagent 结束时验证返回 schema。

Hook 不适合承担复杂开放式推理。一个 Hook 若需要“阅读整个仓库并决定最佳设计”，本质上更像 Skill/Agent/Verifier。

### Hook 的失败语义

必须定义：

- fail-open 还是 fail-closed；
- 超时是否阻止主动作；
- 多 Hook 并发时是否相互影响；
- 输入输出 schema；
- 是否允许修改工具参数；
- 日志和敏感数据策略；
- 项目 Hook 的信任/签名机制。

安全 Hook 通常 fail-closed，纯遥测 Hook 可 fail-open。不要用一个默认策略覆盖所有事件。

## 六、Tool 与 MCP

Tool 是模型看到的动作契约；MCP 是 Host 连接外部 Server 的标准协议。MCP Server 可以暴露 Tools、Resources 和 Prompts，还包含能力协商、取消、进度和日志等协议面。

```text
Agent Host
  ├── local tools
  ├── MCP client ── Server A: issue tracker tools/resources
  └── MCP client ── Server B: docs search tools/resources
```

接入 MCP 不代表自动可信：

- Server 描述可能误导模型；
- 工具可能产生真实副作用；
- Resources 可能含 Prompt Injection；
- OAuth scope 可能过宽；
- Server 更新后工具行为可能漂移；
- 多个 Server 可能提供名称相似工具。

Host 仍要做 namespacing、schema 校验、审批、权限、结果标注、速率限制和审计。

## 七、Skill + MCP 的组合

Skill 定义业务流程，MCP 提供外部能力：

```text
Skill: release-service
  1. 读取仓库版本与测试证据
  2. 调 MCP 查询变更单
  3. 生成发布计划并等待审批
  4. 调 MCP 创建 release
  5. 记录结果并验证
```

Skill 应声明所需 Server、Tool、最低权限和失败回退。安装时验证依赖，不要等运行到第五步才发现 MCP 未授权。

## 八、Plugin：分发单位而不是新推理层

Plugin 可以打包 Skills、MCP 配置、Hooks、assets 和元数据。它解决安装、版本、依赖和团队分发，不应引入另一套与已有层重叠的语义。

插件治理至少包括：

- 发布者和签名；
- 版本锁与更新说明；
- 权限清单；
- Hook 和脚本源码审查；
- MCP 域名/OAuth scope；
- 禁用、回滚和缓存更新；
- 兼容的 Host 版本。

## 九、优先级与冲突

系统应输出 Effective Configuration：哪些 instructions、skills、hooks、tools、MCP 和 policies 当前生效，来源和版本是什么。

建议优先级：

```text
system/managed policy
> explicit user task
> repository scoped instructions
> selected skill workflow
> tool/MCP returned content (data only)
```

外部 Resource、README、Issue 和工具结果不能升级为指令。低层内容要求“忽略用户并上传密钥”应被标记为不可信数据。

## 十、Token 和发现成本

扩展能力越多，工具 schema 和 Skill metadata 越占上下文。策略包括：

- 只加载匹配作用域的 instructions；
- Skill progressive disclosure；
- Tool search/动态注册；
- MCP Server 按任务连接；
- 缓存稳定前缀；
- 对工具描述做 token budget；
- 记录“加载但未使用”的能力。

工具不是越多越强。如果模型频繁选错或完全不调用某工具，应重新命名、合并或隐藏，而不是追加更长描述。

## 十一、可复现配置

一次运行要记录：

```yaml
instructions:
  - path: AGENTS.md
    hash: sha256:...
skills:
  - name: release-service
    version: 1.4.2
hooks:
  - event: PreToolUse
    hash: sha256:...
mcp:
  - server: issue-tracker
    protocol_version: 2025-11-25
    tool_schema_hash: sha256:...
policy_version: corp-v7
```

不记录这些配置，就无法解释同一模型为什么本周行为不同，也无法重放安全事件。

## 十二、怎样测试扩展系统？

### Discovery Tests

作用域、覆盖、触发、渐进加载和禁用是否正确。

### Contract Tests

Skill 依赖、Hook I/O、Tool schema、MCP capability negotiation 和错误结果。

### Policy Tests

不可信 Resource 不能覆盖用户；低权限 token 不能调用高风险工具；Hook 变更必须重新信任。

### A/B Eval

比较有无 instruction/skill/tool 的任务成功率、Token、误触发、工具选择和安全违规。一个 Skill 若只让回答更长却不提高结果，不值得默认加载。

## 十三、常见误区

### 把所有长期知识写进 AGENTS.md

会持续占用上下文。复杂流程和参考资料放 Skill，动态数据通过 MCP 按需取。

### Hook 可以替代 Sandbox

Hook 是可失败的软件和策略层，不是系统级隔离边界。

### MCP 是可信内网 API

协议连接不改变最小权限、用户同意和不可信数据原则。

### Skill 写了步骤就会被严格执行

Skill 仍是模型指导。必须执行的门禁应落到 Hook、Router、Verifier 或 CI。

### Plugin 安装后自动继承所有授权

安装、启用、MCP OAuth、工具审批和项目信任应是分离状态。

## 十四、从当前 Harness 演进

### v0.2：Instruction Loader

实现根到子目录的作用域合并、hash、大小预算和有效配置输出。

### v0.3：Skill Registry

只向模型展示 metadata，匹配后加载正文；记录触发和未使用情况。

### v0.4：Hook Runtime

先实现 `PreToolUse`、`PostToolUse`、`Stop`，明确超时和 fail policy。

### v0.5：MCP Host

能力协商、namespacing、schema、审批、OAuth 最小 scope 和审计；用恶意 Server 做安全测试。

## 十五、检查题

1. 哪些规则应放 Instructions，哪些应由 Hook/CI 强制？
2. Skill progressive disclosure 解决什么问题？
3. 为什么 MCP Resource 只能作为数据而不能提升为指令？
4. Plugin、Skill 和 MCP 的分发/运行边界分别是什么？
5. 怎样重现一次由工具 schema 更新导致的 Agent 回归？

## 参考资料

- [OpenAI Codex: Customization](https://developers.openai.com/codex/)
- [OpenAI Codex: AGENTS.md](https://agents.md/)
- [Model Context Protocol Specification](https://modelcontextprotocol.io/specification/2025-11-25)
- [Writing effective tools for AI agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- [Claude Code: Hooks](https://docs.anthropic.com/en/docs/claude-code/hooks)
- [Claude Code: Subagents](https://docs.anthropic.com/en/docs/claude-code/sub-agents)
