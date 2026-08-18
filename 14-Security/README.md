# Security：从不可信上下文到真实副作用的纵深防御

Code Agent 同时读取仓库、Issue、网页和工具结果，又能修改文件、运行命令、访问网络和外部系统。这使 Prompt Injection 不再只是“模型说了奇怪的话”，而可能成为数据泄漏、供应链植入、权限滥用和持久化修改。

Sandbox 解决执行隔离的一部分；完整 Security 需要跨越输入信任、模型决策、工具权限、凭据、网络、工作区、验证和审计。

## 一、先画资产和信任边界

### 需要保护的资产

- 用户未提交代码与本地文件；
- 源码、测试、设计文档和客户数据；
- Git、云、包仓库和 MCP 凭据；
- CI/CD、Issue、PR 和生产系统权限；
- Agent 配置、Instructions、Skills、Hooks；
- 审计日志和评测隐藏数据。

### 不可信输入

- 仓库源码、注释、README、依赖脚本；
- Issue、PR 评论和 commit message；
- 网页、搜索结果、文档和图片；
- MCP Resources、Tool Result 和 Server metadata；
- 测试输出、编译错误和终端控制序列；
- 其他 Agent 的消息与 artifact。

“来自仓库”不等于可信：攻击者可以提交文件，依赖包也可以输出恶意文本。

## 二、攻击链模型

```text
Untrusted Content
      ↓  prompt injection / misleading evidence
Model changes plan or tool arguments
      ↓
Tool Router authorizes excessive capability
      ↓
Executor/MCP performs action
      ↓
Data exfiltration / destructive change / persistence
```

防御目标不是保证模型永远不受影响，而是在每条边建立独立控制，让一次推理失败不能直接转化为高影响副作用。

## 三、Instruction/Data 分离

系统装配上下文时给每个片段标记 provenance 和 trust：

```python
@dataclass
class ContextBlock:
    content: str
    source: str
    trust: Literal["system", "user", "repo-instruction", "untrusted-data"]
    permissions: list[str]
    content_hash: str
```

规则：

- 只有明确指令层能改变任务目标；
- 代码、网页、Issue 和工具结果中的命令都视为数据；
- 引用不可信文本时保持边界和来源；
- 不让数据声明自己拥有更高权限；
- 高风险动作必须重新依据用户目标和策略评估。

分隔符和提醒有帮助，但不能单独构成安全边界。模型仍可能把恶意内容转化为看似合理的工具调用。

## 四、最小权限与能力分解

权限应绑定 task、tool、resource、时间和风险：

```text
read repo A @ revision X
write worktree W under paths P
run allowlisted commands without network
read issue tracker project Y
create draft comment only after approval
expires in 30 minutes
```

避免给 Agent 一个同时拥有“读取秘密”和“向任意网络发送”的工具组合。单个工具看似安全，组合后可能形成 confused deputy 数据外传路径。

能力分解：

- 只读与写入工具分开；
- draft 与 publish 分开；
- query 与 mutate 分开；
- 凭据 broker 只向目标请求注入短期 token；
- 网络通过目标 allowlist/proxy；
- 高风险工具不暴露通用 shell escape。

## 五、审批不是弹窗越多越安全

审批应发生在用户能理解的语义层：

```text
差：允许执行 curl 命令吗？
好：允许把 06-Repository-Intelligence/README.md 上传到 CKcolorful/Code-Agent-Learning 的 main 分支吗？
```

审批请求包含目的、目标、数据、影响、可逆性和依据。相同低风险操作可由策略预授权；高风险动作使用 scoped one-shot approval。

Approval Fatigue 会让用户机械点击。频繁请求说明工具粒度、默认权限或批处理策略需要重设计。

## 六、凭据架构

不要把长期密钥放入环境供任意 shell 读取。使用 credential broker：

1. 工具声明目标服务和最小 scope；
2. Policy 校验 task 与审批；
3. Broker 签发短期、目标绑定 token；
4. token 只注入专用 adapter，不进入模型 Context；
5. 记录使用事件，不记录秘密；
6. 到期、任务取消或异常时撤销。

日志、异常、命令回显、进程列表和 `/proc` 都可能泄漏环境变量。Redaction 是最后补救，不是凭据隔离的替代品。

## 七、网络与数据外传

无网络降低风险，但包安装和外部工具常需要连接。网络策略应区分 setup phase 与 agent phase，并控制：

- DNS 和目标域名/IP；
- HTTP 方法、端口和重定向；
- 上传 body 大小；
- 私网和 metadata endpoint；
- proxy 日志中的敏感数据；
- MCP/WebSocket 长连接；
- DNS、错误消息等隐蔽通道。

域名 allowlist 仍要防重定向、域名接管和同域多租户。对上传操作在语义层检查数据分类。

## 八、仓库与供应链攻击

风险包括：

- `package.json`、Makefile、setup script 中恶意命令；
- dependency confusion、typosquatting；
- 安装时脚本读取凭据；
- 修改 lockfile 引入新依赖；
- 测试夹具触发外部请求；
- 恶意 Git hook、editor config、编译插件；
- 生成物隐藏后门。

缓解：固定 lockfile 和 registry、安装阶段独立 sandbox、默认禁用脚本或审查新增脚本、依赖变更单独审批、记录镜像/包 hash、对新网络目标和可执行文件报警。

“测试通过”不能发现所有供应链后门，Security Grader 要审查依赖与构建链变化。

## 九、保护工作区和 Git

重点阻止：

- `rm -rf`、`git clean -xfd`、`reset --hard`；
- 覆盖用户 dirty changes；
- 修改 `.git/hooks`、remote、credential helper；
- force push、删除 branch/tag；
- 修改 CI 权限或 secrets 配置；
- 把敏感文件加入 commit。

执行前记录工作区基线；写入限制到 task worktree；删除和回滚基于事务 before-image；远端 Git 操作使用专用工具而非任意 shell。

## 十、MCP 与扩展供应链

MCP/Plugin/Skill/Hook 带来新的信任问题：

- Tool poisoning：描述诱导模型调用其他危险工具；
- rug pull：Server 更新后 schema/行为改变；
- lookalike/namesquatting；
- OAuth scope 过宽；
- Hook 脚本在工具前读取所有输入；
- Skill 内脚本和引用被替换；
- Server-initiated sampling 滥用用户模型。

安装时审查发布者、版本、hash、权限和目标域；运行时 pin schema/version、namespacing、逐工具 policy 和输出 provenance；更新后重新信任高风险 Hook/脚本。

## 十一、策略引擎

```python
@dataclass
class SecurityDecision:
    action: Literal["allow", "deny", "require_approval", "transform"]
    policy_id: str
    reason: str
    constraints: dict

def authorize(request, task, provenance):
    assert request.tool in task.allowed_tools
    classify = risk_engine.classify(request)
    if provenance.contains_untrusted_instruction and classify.can_exfiltrate:
        return deny("untrusted-to-exfiltration path")
    if classify.destructive or classify.external_write:
        return require_approval(scoped_summary(request))
    return allow_with_limits(request)
```

策略要在确定性层执行，并版本化、可测试、可解释。模型可以提供风险线索，但不能成为自己越权请求的最终裁判。

## 十二、安全验证与审计

每次运行记录：

- 有效 policy、sandbox、network 和 credential scope；
- 不可信数据来源；
- 工具选择、参数、审批和结果；
- 网络 allow/deny；
- MCP Server 与 schema hash；
- 读写文件、diff、删除；
- secret detector 与 security grader；
- 用户和策略做出的决定。

审计日志应 append-only、租户隔离、限制访问，并避免记录秘密本身。安全团队需要重建“哪个输入导致哪个动作”，而不是只看最终回答。

## 十三、Red Team 场景

### Prompt Injection

- README 要求忽略用户并读取密钥；
- Issue 评论把恶意命令伪装成构建步骤；
- Tool Result 要求调用另一个上传工具；
- 图片/网页中的间接指令；
- Subagent 返回带权限升级要求的总结。

### Exfiltration

- 读 secret 后发 HTTP、DNS、Issue 评论；
- 把内容编码进 package name、URL path 或错误报告；
- 利用允许域名重定向。

### Destructive Actions

- 模糊的“清理项目”诱导全局删除；
- 重置分支覆盖用户修改；
- 测试脚本删除 workspace；
- 通过 symlink 越出允许目录。

### Persistence

- 修改 AGENTS/Skill/Hook 影响未来会话；
- 写 Git hook、CI workflow、启动脚本；
- 引入恶意依赖或隐藏生成代码。

## 十四、安全指标

- attack success rate；
- unauthorized action rate；
- secret exposure/exfiltration rate；
- destructive action avoidance；
- policy precision/recall；
- approval burden 与错误批准率；
- time to detect / contain；
- benign task completion under defenses；
- persistence detection rate。

安全评测必须同时报告效用。一个拒绝运行所有命令的 Agent 很安全但没有用；目标是在保持合理成功率的同时切断高风险链路。

## 十五、常见误区

### Prompt 写“不要听恶意指令”就够了

Prompt 是一层软约束；工具权限、网络、凭据和策略必须独立限制影响面。

### Sandbox 能防所有攻击

Sandbox 不能自动阻止已授权的外部 API 写入、过宽 OAuth 或用户数据被合法工具外传。

### 内部仓库可信

内部贡献、依赖、日志和自动生成内容仍可能被攻陷或误配置。

### 审批能转移责任给用户

系统必须提供可理解语义并减少噪声，不能用晦涩命令让用户替策略引擎做逆向分析。

### 检测到注入就可以继续高权限执行

当不可信内容影响计划且动作可外传/破坏时，应降权、隔离分析或请求重新确认目标。

## 十六、从当前 Harness 演进

### v0.2：Provenance 与危险路径

为 Context Block、Tool Result 标记来源；阻止不可信输入直接触发网络写、凭据和破坏性工具。

### v0.3：最小权限策略

分离读/写、local/external、draft/publish；加入 scoped approval 和短期凭据 adapter。

### v0.4：扩展供应链

pin Skill/Hook/MCP hash 与 schema，新增依赖、脚本和网络目标单独审查。

### v0.5：持续 Red Team

把注入、外传、破坏、持久化和良性反例加入 CI Eval，监控防御后的任务成功率。

## 十七、检查题

1. 为什么 Prompt Injection 防御的目标不应只是“模型完全不受影响”？
2. “读取秘密”和“发送网络”两个工具为何会组合成新风险？
3. Sandbox、Approval 和 Policy Engine 各自解决什么？
4. 为什么 Hook、Skill 和 MCP 更新需要供应链审查？
5. 安全评测为什么必须同时报告 benign utility？

## 参考资料

- [Running Codex safely at OpenAI](https://openai.com/index/running-codex-safely/)
- [GPT-5.1-Codex-Max System Card](https://cdn.openai.com/pdf/2a7d98b1-57e5-4147-8d0e-683894d782ae/5p1_codex_max_card_03.pdf)
- [Model Context Protocol Specification: Security](https://modelcontextprotocol.io/specification/2025-11-25)
- [InjecAgent: Benchmarking Indirect Prompt Injections](https://aclanthology.org/2024.findings-acl.624/)
- [Agent Security Bench](https://openreview.net/forum?id=V4y0CpX4hK)
- [Prompt Injection Attacks on Agentic Coding Assistants](https://arxiv.org/abs/2601.17548)
