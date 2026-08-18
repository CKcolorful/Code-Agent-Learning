# Terminal-Bench 2.0 详读：从代码补丁扩展到真实终端工作

论文：[Terminal-Bench: Benchmarking Agents on Hard, Realistic Tasks in Command Line Interfaces](https://arxiv.org/abs/2601.11868)

官方资源：[Terminal-Bench](https://www.tbench.ai/)｜[Harbor 运行教程](https://www.harborframework.com/docs/tutorials/running-terminal-bench)｜[实验配置](https://github.com/laude-institute/terminal-bench-experiments)

发表：ICLR 2026｜作者：Mike A. Merrill、Alexander G. Shaw、Nicholas Carlini 等

## 一句话结论

Terminal-Bench 2.0 把 Code Agent 的评测目标从“在给定仓库提交 patch”扩展为“在隔离终端中把最终系统状态做对”。89 个任务覆盖软件工程、机器学习、系统构建、逆向工程等长程工作；结果表明模型与 scaffold 必须一起报告，更多轮次和更多 token 都不会自动换来更高成功率，而执行一致性和验证能力成为主要瓶颈。

## 1. 为什么 SWE-bench 还不够

SWE-bench 的任务结构相对统一：issue、历史仓库、patch、测试。真实技术工作却可能要求：

- 编译并启动一个复杂系统；
- 训练达到指定指标的模型；
- 重实现论文算法；
- 修复操作系统或编译链；
- 逆向文件格式、二进制或密码算法；
- 生成文件、服务、数据库等多种交付物。

这些任务的答案不一定能表示为一个 git diff。Terminal-Bench 因此把评测对象定义为**容器的终局状态**。

## 2. 一个任务的最小契约

每个任务包含：

```text
instruction
Docker environment
tests / verifier
human-written oracle solution
time limit
```

Agent 在容器中探索和修改环境。测试只检查指令要求的结果是否成立，不检查 agent 使用了哪些命令或终端输出。因此多个实现路径都可以正确：

```text
success = verifier(final_container_state)
```

这比逐命令匹配更符合真实工作，也对 verifier 提出更高要求：测试必须覆盖所有必要属性，又不能把一种实现方式误当成唯一答案。

## 3. Outcome-based verification 的难点

论文把任务质量拆成三项：

- **Specificity**：指令描述的可接受终局与测试接受的终局一致；
- **Solvability**：人工 oracle solution 能让测试全部通过；
- **Integrity**：Agent 不能利用未来 git 历史、测试泄漏或环境漏洞作弊。

229 个社区贡献任务最终只保留 89 个。每个入选任务经过三位有经验审核者、多轮自动检查、模型试跑和对抗 exploit agent；平均约投入三小时人工复核。

这个成本说明：高难 Agent benchmark 最贵的部分通常不是写 instruction，而是证明 verifier 不漏、不误判、不可被绕过。

## 4. 数据集的任务跨度

89 个任务来自真实工作灵感，软件工程是最大类别但不到多数。示例包括：

- 把 COBOL 程序重写为 Python，并保持输入输出等价；
- 实现能正确处理 KeyboardInterrupt 和清理逻辑的异步并发；
- 构建 Linux、实现路径追踪器、做差分密码分析；
- 处理视频、科学计算和系统配置。

作者估计，约 48.6% 的任务专家可在一小时内完成，47.3% 需一小时到一天；而初级工程师多数需一小时到一天，部分需数天。人类时间只是主观估计，但它帮助揭示任务的真实 horizon，而非把十分钟脚本包装成长程任务。

## 5. Harbor：Benchmark 与运行时解耦

Terminal-Bench 2.0 使用 Harbor task format 与 Harbor harness。Harbor 负责：

- 拉取任务与构建容器；
- 启动 Agent adapter；
- 统一超时、并行度和 sandbox provider；
- 注入任务、收集 trajectory 与执行测试；
- 将其他 benchmark 通过 adapter 转换到统一格式。

论文实验在 Daytona 上并行运行 32–100 个容器。官方教程可以用 oracle 先校验本机环境，再替换为 Claude Code、Codex CLI 或自己的 agent。

这里的工程价值在于接口边界：Task 规定“环境和正确性”，Agent adapter 规定“怎样行动”，Harness 规定“怎样调度和记录”。这三层不应缠在一起。

## 6. 为什么还要一个 Terminus 2

评测交互式 agent 时，模型和 scaffold 很难分离。Claude Code、Codex CLI、OpenHands 等具有不同工具、上下文策略、prompt 和工程优化，且原生 agent 往往对自家模型最友好。

论文创建 Terminus 2 作为中性基线：只有一个 headless terminal 工具，动作全部是 Bash。它不追求最佳产品体验，而用于在相对一致的接口下比较模型。

完整实验覆盖 6 类 Agent 与 16 个前沿模型，至少对每个支持组合运行 5 次，总计 32,155 个 trial。报告必须明确：

```text
score(model, agent, task set, budget, environment)
```

只写 model name 或只写 agent name 都是不完整的。

## 7. 主结果怎么读

论文版本中最高平均 resolution rate 为 Codex CLI + GPT-5.2 的 62.9%（约写作时结果）；Terminus 2 + Claude Opus 4.5 为 57.8%，Terminus 2 + Gemini 3 Pro 为 56.9%。开源权重模型中，Terminus 2 + Kimi K2 Thinking 为 35.7%。

这组榜单最重要的不是某个即时排名，而是三个观察：

1. 同一 Agent 换模型可以产生巨大差异，例如 Codex CLI 的 GPT-5.2 与 GPT-5-Nano 相差约 52 个百分点；
2. 同一模型换 scaffold 也可能显著变化，例如 Gemini 2.5 Pro 配 Terminus 2 比配 OpenHands 高约 17 个百分点；
3. 即使选每个模型的最佳 scaffold，所有系统仍低于 65%，且存在无人解决任务。

论文同时提醒 benchmark 可能很快饱和，所以长期价值仍在任务生产和评测框架，不是静态榜单截图。

## 8. 成本、轮次和 token 的反直觉结果

跑完整 benchmark 的模型成本可能从 1 美元到 100 美元量级不等。多数任务尝试少于 20 分钟，但极端轨迹可持续两小时、调用数百次，单任务接近一亿 token。

然而平均轮次与成功率几乎没有相关性，更高输出 token 也不必然更好。原因包括：

- 大量动作可能是重复、错误恢复或无效探索；
- 强模型用更少动作就能定位关键步骤；
- 不同 Agent 对“turn”的定义不同；
- 长上下文可能包含越来越多噪声，而不是更多有效状态。

因此评测 Code Agent 不能把“自主运行更久”当成能力指标。更合理的是同时看 success、cost、wall time、有效状态变化与 Pareto frontier。

## 9. 失败分类比总分更有用

论文将 trajectory-level failure 归为三大类：

| 类别 | 典型问题 |
| --- | --- |
| Execution | 违反任务要求、重复步骤、不知道何时停止 |
| Coherence | 上下文丢失、任务跑偏、推理与动作不一致 |
| Verification | 过早结束、没有验证、验证范围太弱 |

失败轨迹由两位人工标注者校准，再使用 GPT-5 high-reasoning 作为 judge；在 120 条人工标注轨迹上约 90% 一致率。闭源前沿模型更常由 execution error 主导，论文所分析的开源模型错误更均衡。

这里不能把 LLM judge 标签当绝对真值，但它能把改进方向从“换更大模型”细化为：命令契约、循环检测、上下文压缩、停止条件或 verifier 覆盖。

## 10. 对最小 harness 的映射

Terminal-Bench 让五模块的责任更加具体：

```text
Agent Loop      -> 长程计划、停止与失败恢复
Context Manager -> 对命令、文件、服务和关键证据做状态化摘要
Tool Router     -> 终端/编辑/外部 Agent adapter 的统一事件协议
Sandbox         -> 容器、网络、资源、超时和可重置快照
Verifier        -> 只看最终状态，使用 agent 不可篡改的测试
```

尤其要把 verifier 放在 Agent workspace 之外，或在提交后再注入测试。若 agent 可以读取/修改评分脚本，outcome-based evaluation 会退化为“修改裁判”。

## 11. 局限与安全边界

1. 为允许安装依赖和检索资料，任务可访问互联网；Agent 理论上可能找到公开 oracle solution。
2. Docker 镜像、包版本和依赖被固定，但外部 URL、API 和网络行为仍会变化。
3. 社区众包提高多样性，也增加任务定义与测试缺陷风险。
4. 任务集公开后仍有训练污染风险；canary string 有助于无意污染检测，不能防止故意训练。
5. 89 个任务规模小，按类别切分后置信区间更大；不能过度解释单个类别排名。
6. 最佳 model-agent 配对与统一 scaffold 回答的是不同问题，不能混成一个排行榜。

## 12. 最小复现实验

先不跑完整 89 题。选择 5 个任务，完成：

1. 用 oracle agent 验证任务可解；
2. 用 dummy/no-op agent 验证不会误通过；
3. 分别接入你的最小 harness 与一个现成 CLI agent；
4. 每个组合运行 3 次，保存全轨迹和最终容器 diff；
5. 统计 success、成本、时间、命令错误、重复步骤和验证覆盖；
6. 给其中一个任务写 exploit agent，尝试读取测试或伪造产物，再修补隔离边界。

“能接 Harbor”只是适配工作；“能发现并修补 verifier exploit，同时做模型/scaffold 配对分析”才是有含金量的实践项目。

## 13. 读完应能回答

1. 为什么终局状态测试比命令序列匹配更合理？
2. Task、Agent adapter 与 Harness 应如何解耦？
3. 为什么更多 turns/tokens 不能直接代表更强能力？
4. 统一 scaffold 与最佳原生 scaffold 分别在测什么？
5. 如何防止 agent 篡改或定位隐藏 verifier？
