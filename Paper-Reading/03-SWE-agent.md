# SWE-agent 详读：工具接口本身就是模型能力

论文：[SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering](https://arxiv.org/abs/2405.15793)

官方代码：[SWE-agent/SWE-agent](https://github.com/SWE-agent/SWE-agent)

项目文档：[swe-agent.com](https://swe-agent.com/)

作者：John Yang 等｜首次提交：2024 年 5 月｜发表于 NeurIPS 2024

## 一句话结论

SWE-agent 证明：固定底层模型，只改变它浏览代码、搜索、编辑和接收反馈的方式，就能显著改变仓库级修复成功率。Agent-Computer Interface（ACI）不是模型外面的便利包装，而是决定模型能否有效行动的能力层。

## 1. 研究问题：为什么 shell 还不够

理论上，一个能调用 shell 的模型已经可以完成所有软件操作：`find` 搜文件、`grep` 搜符号、`sed` 改代码、`pytest` 跑测试。但“计算上完备”不等于“模型容易使用”。

shell 对语言模型有几个具体摩擦：

- 命令语法脆弱，转义、管道和路径很容易写错；
- `cat` 或递归 `grep` 可能一次返回数万 token；
- 行号会随编辑变化，模型却可能依据旧观察继续修改；
- 命令失败常只返回模糊错误，恢复成本高；
- 一个低级操作需要多轮拼装，误差沿长轨迹累积。

论文类比人类使用 GUI/IDE：我们不因为键盘和系统调用理论上能完成一切，就否认编辑器、搜索面板和错误提示的价值。语言模型也需要按其认知特点设计的界面，这就是 ACI。

## 2. ACI 的完整定义

ACI 不只是工具列表。它至少定义五件事：

1. **Action space**：模型可以发出哪些动作，每个动作有哪些参数。
2. **Parser**：模型输出怎样被稳定解析成单个动作。
3. **Execution semantics**：动作在容器和工作树中具体做什么。
4. **Observation format**：成功、失败、截断与状态变化怎样反馈。
5. **History policy**：哪些旧观察保留、折叠或丢弃后进入下一轮 prompt。

所以可以把 agent 的有效策略写成：

```text
next_action = LLM(
  issue,
  tool_documentation,
  retained_history,
  current_observation
)
```

改变任何一项都会改变模型真正看到的状态与能稳定表达的动作，即使 LLM 权重、温度和问题完全相同。

## 3. 论文总结的四条 ACI 原则

### 3.1 动作应简单

命令名、参数和返回格式要容易从少量示例学会。参数越多、语法分支越多，模型越可能产生 malformed action。

“简单”不等于动作必须低级。一个接受少量稳定参数的高阶 `edit`，可能比让模型组合 `python -c`、正则与 shell 转义更简单。

### 3.2 动作应紧凑高效

一次调用应完成一个有意义的操作单位。若查找文件需要 `pwd → find → grep → head` 四轮，任何一轮失败都会浪费模型调用，并把无关文本写入历史。

紧凑动作还能缩短 credit assignment：模型更容易知道哪次动作带来了有效证据。

### 3.3 反馈应信息充分但简洁

Observation 必须回答：动作是否成功、当前状态是什么、下一步恢复需要什么。与此同时，它不能把所有 stdout 原样塞回上下文。

一个好反馈可能包含：

```text
exit_code: 1
summary: 1 failed, 27 passed
primary_error: AssertionError in tests/test_x.py:83
output_truncated: true
```

而不是数千行依赖安装日志。

### 3.4 Guardrail 应阻止错误扩散

模型犯错不可避免，ACI 的目标是让错误可逆。编辑后的语法检查、失败自动回滚、唯一文本匹配和明确错误消息，能阻止一次坏动作污染后续十轮。

四条原则存在张力：更高阶的动作更高效，却可能隐藏状态；更完整的反馈更易诊断，却增加上下文噪声。ACI 设计本质上是信息带宽与操作可靠性的权衡。

## 4. SWE-agent 的系统结构

论文把系统分成三个主要部分。

### Environment

Environment 在 Docker 容器中准备目标仓库、执行动作并返回观察。它持有真正的外部状态：当前目录、文件内容、进程、依赖和 git diff。

### Agent

Agent 负责构造 prompt、调用语言模型、解析动作、维护历史与判断终止。模型输出不能直接当 shell 任意执行，而要先经过动作解析和格式检查。

### Logging

系统保存每个实例的 trajectory：提示、动作、观察、token/成本、最终 patch 与评测结果。没有轨迹，只看 resolved rate 无法知道失败来自模型、工具还是环境。

一次循环可以写成：

```text
while budget_remaining:
    prompt = build_prompt(issue, tools, processed_history)
    model_output = llm(prompt)
    action = parse(model_output)
    observation = environment.step(action)
    log(action, observation)
    if action == submit:
        break
```

真正的研究贡献主要藏在 `tools`、`parse`、`step` 与 `processed_history` 中，而不是 `while` 循环本身。

## 5. 搜索接口：为什么输出形状很重要

SWE-agent 提供文件查找、目录搜索和文件内搜索等命令。它们与原生 `find/grep` 最大的区别，不是检索算法更先进，而是输出被规范化和限长。

理想搜索结果应给出：

- 命中的文件路径；
- 稳定行号与少量上下文；
- 命中数量；
- 是否因上限被截断；
- 查询范围。

如果结果太多，应告诉模型缩小查询，而不是静默丢掉后半段。若没有截断标记，模型会错误地把“前 50 条结果”理解成“全部结果”。

论文对比 summarized search 与更迭代、冗长的搜索方式。Lite 上前者为 18.0%，迭代式搜索约 12.0%。这不是证明任何一步式检索都优于迭代检索，而是说明：在固定预算下，低价值工具轮次和冗余观察会明显伤害 agent。

## 6. File Viewer：100 行为何优于 30 行和整文件

Viewer 以固定窗口显示带行号的代码，并支持打开文件、跳到行号、上下滚动。它解决的是“上下文局部性”：模型既需要看目标行，也需要函数签名、相邻分支和调用约束。

论文消融结果大致为：

| Viewer 设置 | SWE-bench Lite resolved |
| --- | ---: |
| 30 行窗口 | 14.3% |
| 100 行窗口 | 18.0% |
| 整个文件 | 12.7% |

这张表说明信息量存在倒 U 型关系：

- 30 行太窄，模型可能只看到报错行，看不到类定义或前置条件；
- 整文件太宽，无关代码稀释注意力并消耗上下文；
- 100 行在论文设置中取得较好平衡。

不要把“100”当成普适常数。真正可迁移的设计是：窗口要有当前位置感、支持廉价移动，并让模型知道文件总长和当前范围。

## 7. File Editor：最有价值的接口

专用 editor 允许模型根据当前文件窗口执行多行修改。论文中的关键设计包括：

- 用明确范围或旧文本定位修改；
- 编辑后展示变更附近的新内容；
- 自动运行 lint/语法检查；
- 若检查失败则回滚；
- 反馈错误、拟修改内容与原始内容，帮助模型恢复。

为什么不能只让模型用 `sed`？因为 `sed` 同时要求它正确处理行号、转义、shell 语法和多行文本。任何一项错误都可能产生静默破坏。

消融是论文最强的因果证据之一：

| 编辑接口 | SWE-bench Lite resolved |
| --- | ---: |
| 专用 edit + lint | 18.0% |
| 专用 edit，去掉 lint | 15.0% |
| 去掉专用 edit | 10.3% |

固定模型下，移除 editor 带来 7.7 个百分点绝对下降。它说明大量“模型不会改代码”的表象，其实来自模型无法稳定把修改意图落到文件。

lint guardrail 的收益也值得单独看：它不让模型更聪明，只是让语法类错误在当前步暴露并回滚，避免污染后续状态。

## 8. Observation 与历史裁剪

ReAct 循环会不断累积观察。若完整保留，prompt 中可能同时出现：旧文件版本、已修复错误、重复搜索结果和长测试日志。

SWE-agent 使用 history processor 折叠旧 Observation。论文比较“保留最近 5 个观察”与“完整历史”：前者 18.0%，后者约 15.0%。

这个结果反驳了一个直觉：上下文窗口更长，就应该把所有内容都留下。对 agent 来说，旧观察可能已经过期；它们不是知识，而是带时间戳的状态快照。

一个现代实现可以分三层保存：

1. **永不丢弃的结构化状态**：issue、约束、当前假设、已修改文件、测试结论。
2. **最近原始观察**：用于精确引用当前代码和错误。
3. **可检索的完整轨迹**：保存在外部日志，需要时再取回。

论文还讨论 malformed model output 的处理。无效格式如果直接原样回灌，会让 prompt 充满解析错误；接口应给出短、可操作的纠正说明，并允许模型立即重试。

## 9. 一条成功轨迹的阶段结构

论文分析轨迹后发现，成功修复并非均匀地“想—改—测”，而常呈现阶段性。

### 阶段一：复现与定位

agent 搜索错误符号、阅读测试、运行最小复现。此时搜索和查看动作占主导，过早编辑往往意味着尚未理解契约。

### 阶段二：形成局部修复假设

模型把 issue、调用链和失败输出组合起来，选定责任位置。好轨迹会说明修改为何应放在这一层，而非只看到哪行报错就改哪行。

### 阶段三：编辑—测试迭代

中后期编辑与执行交替出现：做小修改、跑窄测试、读错误、再修正。一次写大 patch 后直接提交更难恢复。

### 阶段四：提交

agent 输出最终 patch。论文系统允许模型决定终止，但实际产品更适合加入提交门禁：存在非空 diff、相关测试已运行、没有未处理语法错误。

## 10. 主结果与正确解释

使用 GPT-4 Turbo 时，论文报告：

- 完整 SWE-bench：12.47%；
- SWE-bench Lite：18.0%；
- Lite 上的 shell-only agent：11.0%。

18.0 相对 11.0 约为 64% 的相对提升：

```text
(18 - 11) / 11 ≈ 63.6%
```

应同时看到三个限定：

1. 这是论文当时特定模型、数据版本与预算下的结果；
2. 绝对成功率仍然不高，ACI 没有解决所有推理问题；
3. shell-only 基线的实现质量会影响差距，不能把 64% 当作所有工具系统的固定收益。

论文更有价值的证据是同一框架内的消融，因为它更接近回答“哪个接口设计导致变化”。

## 11. Agent 为什么会迷路、循环和过早提交

### 迷路

搜索返回过宽、Viewer 没有位置感、模型在目录之间来回切换，却没有维护“已排除区域”。解决方法是有限结果、路径/行号稳定显示和结构化定位状态。

### 循环

相同查询或测试重复执行，Observation 没有新信息。系统可对动作指纹和工作树状态做去重；连续无进展时要求重写假设。

### 编辑漂移

模型根据几轮前看到的内容修改当前文件。编辑接口应要求 old text 唯一匹配或文件版本一致，否则拒绝执行。

### 过早提交

预算压力、错误的成功判断或过于容易调用 `submit` 都会触发。提交动作应返回检查清单，而不是无条件结束。

### 输出淹没

一次测试输出占满上下文，真正失败堆栈反而被截掉。执行接口需要先落盘完整日志，再返回结构化摘要、首个失败与截断标记。

## 12. 一个现代 ACI 的最小协议

```text
search(query, path?, max_results)
  -> matches[], total_count, truncated

view(path, start_line, end_line)
  -> content, file_length, file_version

edit(path, expected_old_text, new_text, file_version)
  -> applied, diff, syntax_status, current_version

run(command, timeout, max_output)
  -> exit_code, stdout_summary, stderr_summary,
     duration, truncated, log_handle

diff()
  -> changed_files, patch, stats

submit()
  -> accepted only if submission policy passes
```

除了 schema，还应定义语义：路径相对哪个根目录、命令是否共享进程状态、超时后如何杀子进程、edit 失败是否保证原子性、日志句柄能保存多久。

## 13. 论文没有解决的部分

- **定位仍以词面搜索和模型判断为主**，没有完整程序分析或学习式 retriever。
- **验证较弱**，agent 仍可能没有复现 bug 就提交。
- **单 agent 长轨迹成本高**，每个无效动作都增加推理费用。
- **上下文压缩可能丢证据**，保留最近 5 个 Observation 是经验设置，不是状态一致性的理论保证。
- **ACI 与模型耦合**，对 GPT-4 Turbo 有效的命令文档和输出形状不一定对更小模型最优。
- **安全边界不是论文重点**，生产环境还需网络、凭据、文件系统和危险命令隔离。

## 14. 与 ReAct、Agentless、OpenHands 的关系

- ReAct 提供抽象循环；SWE-agent 把 Action/Observation 具体化为代码工具。
- SWE-agent 相信在闭环中边探索边修改；Agentless 则质疑复杂自主循环，改用明确的定位—修复—验证 pipeline。
- OpenHands 把 SWE-agent 式交互扩成平台级 Event Stream、Runtime 与多种 agent 接口。
- SWE-Gym 进一步把这类工具轨迹当作监督数据和 policy rollout。

## 15. 源码怎么读

官方项目此后经历过重构，当前目录名可能与论文版本不完全一致。建议优先 checkout 论文对应 release/tag，再按数据流追踪：

1. [`sweagent/`](https://github.com/SWE-agent/SWE-agent/tree/main/sweagent)：主包与 agent/environment 实现。
2. [`config/`](https://github.com/SWE-agent/SWE-agent/tree/main/config)：工具、prompt 与运行配置入口。
3. [项目文档中的 configuration](https://swe-agent.com/latest/config/overview/)：理解当前版本怎样声明 agent 和 tools。
4. 搜索 `history_processor`：看旧 Observation 如何被处理。
5. 搜索 `submit`、`edit` 与 shell tool 实现：看动作解析、执行和错误反馈。

源码阅读任务不是“找到论文里的 prompt”，而是回答：

```text
模型文本
  -> 哪个 parser
  -> 哪个 action object
  -> 哪个环境调用
  -> 哪种 observation
  -> 怎样进入下一轮上下文
  -> 最终 patch 保存在哪里
```

## 16. 常见误读

- **“SWE-agent 的创新是 GPT-4 写代码更强。”** 论文固定模型研究 ACI，创新重点不在新模型。
- **“给模型完整 shell 最灵活，所以一定最好。”** 灵活性会带来语法、输出和恢复成本。
- **“100 行是最佳通用窗口。”** 它只是该实验设置下的经验结果。
- **“保留完整历史总不会有坏处。”** 消融结果明确显示可能下降。
- **“lint 能判断修复正确。”** lint 只拦截一类低级错误，不能验证 issue 行为。
- **“有专用工具就不需要 prompt。”** 工具文档、动作示例和错误反馈仍是 ACI 的组成部分。

## 17. 可复现练习

### 练习一：editor 消融

固定模型和 30 个任务，比较：原生 shell 编辑、文本替换工具、带 old-text 校验与语法回滚的 editor。记录 patch 应用成功率、语法错误率、恢复轮数和最终 resolved rate。

### 练习二：Observation 带宽实验

让测试工具分别返回完整 stdout、最后 200 行、结构化摘要 + 日志句柄。比较 token 成本、首个失败定位率与重复运行次数。

### 练习三：循环检测

为 `(action, normalized_args, git_tree_hash)` 建指纹。连续两次相同指纹时返回“无状态进展”观察，并要求模型选择新假设。测量无效步数是否下降，以及是否误伤必要重试。

## 18. 读完后的检查题

1. 为什么一个专用 edit 能在模型权重不变时提高成功率？
2. Viewer 窗口过小和过大分别制造哪类错误？
3. lint rollback 改善的是推理能力，还是错误恢复成本？
4. 为什么旧 Observation 可能是有害信息？
5. 你设计的 `run` 工具如何同时保留完整日志与控制上下文占用？

## 19. 最终要带走的观点

SWE-agent 最重要的判断是：**不要只问模型够不够强，还要问环境是否以模型能稳定理解和操纵的方式暴露了状态。** 可靠的编辑原语、恰当的代码窗口、明确的截断信号和可逆错误，常常比再堆一段复杂 prompt 更能提高端到端修复率。
