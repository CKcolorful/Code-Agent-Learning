# Editing Engine：从“模型想改什么”到可审计 Patch

Tool Router 决定调用哪个工具，Sandboxed Executor 决定工具在哪里运行，但它们都没有回答：**模型用什么编辑表示表达修改，系统如何把这个表示安全地应用到不断变化的工作树？**

一个编辑工具返回成功，只能说明字节发生了变化。它没有证明改对了文件、匹配了正确位置、保留了用户修改、生成了最小 diff，更没有证明语义正确。Editing Engine 的工作，是把概率性的修改意图转换成确定、可预览、可回滚、可验证的补丁事务。

## 一、编辑协议的四层

```text
Edit Intent      模型希望改变的行为和范围
    ↓
Edit Program     replace / patch / AST operation 等机器可执行表示
    ↓
Patch Transaction 版本检查、应用、格式化、回滚、冲突处理
    ↓
Workspace Delta 绑定 before/after revision 的实际文件变化
```

混淆这四层会产生典型错误：模型说“添加校验”被当成可执行指令；patch 应用成功被当成语义成功；格式化造成的大 diff 被误认为必要修改。

## 二、一个统一的数据模型

```python
@dataclass
class EditPrecondition:
    path: str
    base_hash: str
    expected_symbol: str | None
    expected_text: str | None

@dataclass
class EditOperation:
    kind: Literal["create", "delete", "replace", "unified_diff", "ast"]
    path: str
    payload: dict
    preconditions: list[EditPrecondition]

@dataclass
class PatchTransaction:
    transaction_id: str
    base_revision: str
    operations: list[EditOperation]
    allowed_paths: list[str]
    formatter_policy: str
    rollback_on_failure: bool = True

@dataclass
class PatchResult:
    status: Literal["applied", "conflict", "rejected", "rolled_back"]
    changed_files: list[str]
    diff: str
    diagnostics: list[str]
    before_hashes: dict[str, str]
    after_hashes: dict[str, str]
```

关键字段是 `base_revision` 和 `base_hash`。没有乐观并发控制，Agent 在阅读之后、应用之前遇到用户或另一个 Agent 修改同一文件时，可能静默覆盖新内容。

## 三、五种编辑表示

### 1. 整文件重写

优点是简单，模型不需要精确定位；缺点是 Token 高、容易改写换行和格式、覆盖未读内容、扩大 review 面积。

适合新建小文件或生成物，不适合修改大型已有文件。系统至少应要求模型先读完整文件，并限制最大文件大小。

### 2. 精确字符串替换

```json
{
  "path": "src/token.py",
  "old": "if now > expires_at:",
  "new": "if now >= expires_at:",
  "expected_occurrences": 1
}
```

它便于校验和重试，但必须检查匹配次数。`old` 出现零次是陈旧上下文；出现多次是歧义，不能默认替换第一个。

### 3. Unified Diff

Diff 同时表达上下文、删除和新增，天然适合 review 和 Git。它的问题是模型容易生成错误行号、缺失上下文、重复 hunk，工作树轻微变化也可能导致应用失败。

安全做法是：忽略模型行号作为绝对真相，以 hunk 上下文定位；应用前 `--check`；失败时返回结构化冲突，不要自动使用过宽 fuzzy match。

### 4. 结构化范围编辑

通过 `path + symbol + anchor + replacement` 定位函数、类或配置项，比裸字符串更稳定。例如：

```json
{
  "kind": "replace_symbol_body",
  "path": "src/cache.py",
  "symbol": "Cache.get",
  "expected_signature": "def get(self, key: str) -> Value | None",
  "body": "..."
}
```

系统用解析器确认符号唯一、签名未漂移，再生成文本 patch。

### 5. AST/CST Transformation

AST 操作适合机械重构、导入、签名迁移和大规模 API 更新。CST 能更好保留注释与格式。代价是每种语言和语法版本都要适配，动态语言语义也不能仅靠 AST 保证。

它不应取代自由形式 patch，而应成为高频、可形式化编辑的专用工具。

## 四、编辑策略不是固定选择

可以根据任务和文件选择协议：

| 场景 | 推荐表示 | 原因 |
| --- | --- | --- |
| 新建小文件 | 整文件 | 无并发基线，表达直接 |
| 单点逻辑修复 | 精确替换 / 小 diff | 易审计、影响面小 |
| 多处相邻修改 | Unified Diff | 保留整体上下文 |
| API 机械迁移 | AST/CST | 可保证结构匹配 |
| 配置文件 | schema-aware edit | 防止类型和层级错误 |
| 用户同时编辑 | 带 hash 的事务 | 冲突优先于覆盖 |

Router 可以提供统一 `apply_edit` 工具，但 Editing Engine 内部仍要根据 `kind` 调用不同 adapter。

## 五、Patch Transaction

一次任务往往需要多个文件同时变化。逐个文件立即提交会留下半完成状态：实现更新了，测试或接口没更新。事务流程应当是：

1. 解析并校验全部操作；
2. 确认路径、权限、文件 hash 和预期锚点；
3. 在临时快照或内存中试应用；
4. 解析修改后的所有文件；
5. 计算 diff、路径集合和大小；
6. 执行格式化策略；
7. 再次计算最终 diff；
8. 原子落盘，或在任何失败时回滚；
9. 返回可验证的 before/after 证据。

```python
def apply_transaction(tx: PatchTransaction) -> PatchResult:
    snapshot = workspace.snapshot(tx.allowed_paths)
    try:
        assert_revision(tx.base_revision)
        validate_preconditions(tx.operations)
        staged = apply_in_staging_area(snapshot, tx.operations)
        parse_check(staged.changed_files)
        format_only_changed_regions(staged, tx.formatter_policy)
        enforce_diff_policy(staged.diff)
        workspace.commit(staged)
        return build_result("applied", snapshot, staged)
    except EditConflict as exc:
        workspace.restore(snapshot)
        return build_conflict(exc, snapshot)
    except Exception:
        workspace.restore(snapshot)
        raise
```

“原子”至少意味着 Harness 不会因为第三个文件失败而保留前两个文件的未预期改动。底层可以使用临时目录、Git index、文件系统快照或逐文件备份实现。

## 六、最小 Diff 是控制面，不是审美偏好

小 diff 有三种价值：

- 降低引入无关回归的概率；
- 让 Verifier 和人类更容易聚焦；
- 减少 Agent 利用大规模重写绕过任务约束。

但“行数越少越好”也会鼓励难读的一行式代码或遗漏必要测试。Diff Policy 应检查的是：

- 修改路径是否在预期范围；
- 是否出现整文件换行/编码变化；
- 删除与任务无关的大段代码；
- 生产修改是否缺少相应测试或迁移；
- 自动生成文件是否由正确生成器产生；
- patch 复杂度是否与任务规模大致匹配。

## 七、格式化、生成代码和锁文件

格式化应是单独阶段并记录命令。否则无法区分模型修改与格式器修改。建议：

- 优先格式化变更文件或变更区域；
- 在格式化前后分别保存 diff；
- 生成代码只通过仓库声明的生成命令更新；
- 锁文件变动必须能追溯到依赖变更；
- 检测 CRLF/LF、编码和文件 mode 的意外改变。

不要让模型手写大型生成物，因为那会绕过源码与生成规则之间的契约。

## 八、冲突不是普通工具错误

冲突意味着模型依据的世界已经过期。正确反馈应包括：

```json
{
  "status": "conflict",
  "path": "src/cache.py",
  "expected_hash": "abc...",
  "actual_hash": "def...",
  "overlap": [42, 61],
  "next_action": "re-read-region-and-replan"
}
```

Agent 必须重新阅读重叠区域并重新推理。自动三方合并只适用于能证明不重叠的机械编辑；语义冲突不能靠文本合并解决。

并行 Agent 应使用独立 worktree 或 overlay。共享目录中的“不同文件”也可能通过格式器、代码生成或依赖锁文件发生隐式冲突。

## 九、保护用户工作

Editing Engine 开始前应记录：

- `git status --porcelain`；
- 未跟踪文件；
- 目标文件 hash；
- 用户已有 diff；
- 当前 branch 和 HEAD。

回滚只能撤销该事务创建的 delta，不能使用 `git reset --hard` 或覆盖整个工作区。一个简单规则是：**没有 before-image，就没有删除或恢复权限。**

## 十、编辑后的分层检查

Editing Engine 不取代 Verifier，但应执行廉价结构检查：

1. 文件可解析；
2. patch 已完整应用；
3. 没有冲突标记；
4. 没有超出允许路径；
5. diff 大小和文件类型符合策略；
6. 格式器没有失败。

类型检查、目标测试、回归测试和行为验收由 Verifier 负责。边界清晰能避免每次工具调用都运行全套测试。

## 十一、怎样评测 Editing Engine？

将相同修改意图转换成多种编辑协议，至少重复运行多次：

### 协议指标

- `apply_success_rate`；
- `parse_success_rate`；
- 平均编辑输出 Token；
- 冲突检测召回率；
- 错误位置修改率；
- 无关 diff 比例；
- 回滚完整率。

### 下游指标

- 测试通过率和 resolved rate；
- 用户修改保留率；
- 人工 review 时间；
- 冲突后的恢复成功率；
- 格式化噪声占比。

### 故障注入

- 在读取和应用之间修改目标文件；
- 让 `old` 文本出现两次；
- 只让事务最后一个文件失败；
- 注入无效 UTF-8、只读文件和符号链接；
- 让格式器修改大量无关行；
- 在文件中预先放置用户未提交改动。

## 十二、常见误区

### Patch 能应用就是编辑成功

应用成功只代表语法协议成立；语义成功需要独立验证。

### Fuzzy 越强，成功率越高

过宽的模糊匹配会把“应该冲突”变成“改错位置”。匹配置信度不足应返回冲突。

### AST 编辑天然安全

AST 保证结构，不保证业务语义、类型正确或兼容性，也可能丢失注释和格式。

### 回滚就是 Git Reset

全局 reset 会删除用户工作。事务必须只撤销自己创建的变更。

### 大模型不需要专门编辑接口

模型越能处理复杂任务，越需要稳定、低歧义的 Agent-Computer Interface 来减少无谓失败。

## 十三、从当前 Harness 演进

### v0.2：精确替换前置条件

增加 `expected_occurrences`、文件 hash、路径策略和结构化冲突结果。

### v0.3：Patch Transaction

支持多文件试应用、解析检查和事务回滚，保存 before/after diff。

### v0.4：结构化编辑 Adapter

为高频语言加入 symbol edit、import edit 和配置 schema edit。

### v0.5：协议 A/B Eval

使用同一批任务比较整文件、字符串替换、Unified Diff 和 AST 操作，分开统计协议失败与语义失败。

## 十四、检查题

1. 为什么编辑请求必须绑定文件 hash 或仓库 revision？
2. Unified Diff 应用失败为什么不应该总用 fuzzy match 修复？
3. Editing Engine 和 Verifier 的检查边界在哪里？
4. 怎样只回滚 Agent 的修改而保留用户原有 diff？
5. 哪类编辑适合 AST/CST，哪类仍需要自由形式 patch？

## 参考资料

- [SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering](https://arxiv.org/abs/2405.15793)
- [Agentless: Demystifying LLM-based Software Engineering Agents](https://arxiv.org/abs/2407.01489)
- [Git apply documentation](https://git-scm.com/docs/git-apply)
- [Tree-sitter](https://tree-sitter.github.io/tree-sitter/)
- [Language Server Protocol Specification](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/)
- [GPT-5.1-Codex-Max System Card: destructive-action avoidance](https://cdn.openai.com/pdf/2a7d98b1-57e5-4147-8d0e-683894d782ae/5p1_codex_max_card_03.pdf)
