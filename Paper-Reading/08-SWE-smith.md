# SWE-smith 详读：把真实仓库变成可规模化训练的 SWE Gym

论文：[SWE-smith: Scaling Data for Software Engineering Agents](https://arxiv.org/abs/2504.21798)

官方代码：[SWE-bench/SWE-smith](https://github.com/SWE-bench/SWE-smith)

发表：NeurIPS 2025 Datasets & Benchmarks Track Spotlight｜作者：John Yang、Kilian Lieret、Carlos E. Jimenez 等

## 一句话结论

SWE-smith 最重要的创新是把 SWE-bench 的“先找到历史任务，再为每个任务恢复环境”反过来：**先为一个仓库建立可靠环境，再在同一环境中合成数百个会破坏既有测试的 bug**。这一反转把环境成本从按任务支付变为按仓库摊销，使可执行训练数据真正具备扩展性。

## 1. 为什么 SWE Agent 缺的不是普通代码数据

普通 PR 或代码提交可以提供 `issue -> patch`，但缺少稳定的执行环境，就无法判断另一种 patch 是否也正确，更无法给多轮 agent trajectory 提供可靠奖励。

训练 Agent 需要的是：

```text
issue + clean repository + dependency environment
  -> interactive trajectory
  -> candidate patch
  -> executable tests
  -> reward
```

SWE-Gym 提供了 2,438 个可执行真实任务，但环境约占数 TB，仓库数也有限。SWE-smith 追问的不是“再收集一点 PR”，而是怎样把环境构建变成可复用基础设施。

## 2. Environment-first 的关键反转

两种数据构建路线可以这样对比：

```text
SWE-bench style:
历史 issue/PR -> 找 base commit -> 为该版本装依赖 -> 验证该任务

SWE-smith:
选一个当前仓库 -> 建一个可运行环境 -> 合成很多 bug -> 用同一测试套件筛选
```

SWE-smith 先让 SWE-agent 尝试安装仓库和运行测试，再由人工确认安装/测试命令，并要求超过 80% 的既有测试通过。之后，同一仓库镜像可服务数百个任务。

论文从 PyPI 下载量前 5,000 的包出发，按 GitHub stars 排序，过滤低于 1,000 stars 的项目，并排除 12 个 SWE-bench 评测仓库，最终覆盖 128 个 Python 仓库。

## 3. 四类 bug 生成策略

每种策略输出一个候选 diff，随后都要经过真实测试验证。

### 3.1 LM Modify 与 LM Rewrite

- **LM Modify**：给模型完整函数，要求引入错误修改；
- **LM Rewrite**：只给函数头和 docstring，让模型重新实现，错误自然来自不完整重建。

前者更容易制造 bug，后者更像开发者错误，但生成成本和变更规模更大。

### 3.2 Procedural Modification

解析 AST 后机械删除条件/循环、替换运算符等，共包含十余类变换。它成本低、可控、可解释，却可能产生缺乏真实语义动机的错误。

### 3.3 Combine Bugs

单函数变更的复杂度有限，因此把同一文件或模块中的多个候选 patch 组合成多点故障。这能拉长定位与修复链路，但也可能制造现实中较少出现的“同时独立坏多处”。

### 3.4 PR Mirror

收集修改 Python 文件的历史 PR，让模型在当前版本中反向撤销这些变更。它最接近真实软件演化，但并不 checkout 原 PR 的 base commit，因为旧版本可能与已经构建的共享环境不兼容。

## 4. 测试不仅验证答案，也负责生成数据

候选 bug 被应用到仓库后，SWE-smith 运行测试，只保留至少破坏一个原本通过测试的 patch，并丢弃运行超过两分钟的候选。

这个过程把测试从终局 verifier 提升为数据生成过滤器：

```text
candidate bug
   ├─ no test breaks        -> 丢弃：不可观测
   ├─ test timeout          -> 丢弃：成本不可控
   └─ 1+ passing test fails -> 保留：可执行训练任务
```

它证明 bug 存在，却不证明 issue 描述自然、修复唯一或任务与真实用户需求同分布。可执行性只是数据质量的一维。

## 5. Issue 文本如何生成，以及泄漏风险

作者把 bug diff、一个随机 F2P 测试源码和测试日志交给模型，让其生成带复现代码的 GitHub issue 风格描述。

消融显示，模型生成 issue 的训练效果可接近原始 PR issue；直接把失败测试内容暴露给 agent 虽然让老师更容易成功，却使学生更少主动写复现脚本，最终泛化下降。论文统计中，使用生成 issue 训练的模型在 500 个 Verified 任务里有 379 次尝试复现，而使用 test-based issue 的模型只有 127 次。

这给数据工程一个重要原则：**训练标签可以由测试构造，但用户可见问题描述不应直接泄漏 verifier 的实现细节**。否则模型会学会对着答案修，而不是从症状定位。

## 6. 数据规模为何能扩大

论文版本报告：

- 50,137 个任务、128 个仓库，平均每仓库 381 个任务；
- pandas 单仓库最多生成 2,277 个任务；
- 共享仓库环境约 295 GB；论文估计若按 SWE-bench 每任务镜像方式扩到 50k，可能需 50–150 TB；
- 数据构建约花费 1,360 美元与约 20 小时人工，人工主要用于确认仓库级安装、测试命令和日志解析。

今天官方仓库中的数据量可能继续增长，所以复现时应记录 dataset revision，而不要把论文数字与最新仓库数字混用。

## 7. 从任务到专家轨迹

作者使用 SWE-agent + Claude 3.7 Sonnet 对任务 rollout，最多 75 步、2 美元，然后只保留测试成功的轨迹。整体过程包括：

- 对 8,686 个独立任务发起 17,906 次尝试；
- 获得 6,457 条成功尝试，成功率约 36%；
- 限制同一任务最多出现 3 条轨迹，得到最终 5,016 条训练轨迹；
- 用这些轨迹微调 Qwen2.5-Coder-Instruct 7B/32B。

限制同一简单任务的成功轨迹数量很关键。否则训练集会被“老师每次都能解”的短路径主导，学生学到的是重复模式而非任务覆盖。

## 8. 结果应该怎样读

SWE-agent-LM-32B 在 SWE-bench Verified 上达到 40.2% Pass@1，Lite 为 30.7%；同 scaffold、单次尝试、没有 test-time best-of-N。只用 500 条成功轨迹训练时，Verified 已达到 28.2%，比论文引用的同规模 SWE-Gym 模型高 8.2 个百分点、比 R2E-Gym 高 0.7 个百分点。

更有解释力的消融是：

- 训练轨迹越多，整体表现持续上升；
- PR Mirror 最有效，但 Procedural 和 LM Rewrite 已接近它；
- LM Modify 明显较弱，说明“容易生成且容易破坏测试”不等于高价值训练分布；
- 固定模板 issue 使轨迹动作更加同质，动作多样性下降。

40.2% 不能只归因于合成任务数量。老师模型、SWE-agent ACI、轨迹过滤、任务类型配比与学生模型共同构成结果。

## 9. 轨迹分析暴露出的失败模式

训练后的 32B 模型平均约 24.9 步，老师约 29.1 步；但学生存在明显重复动作问题。论文观察到超过四分之一的学生轨迹包含长度至少 10 的重复序列，而 Claude 老师低于 4%；出现这种重复时约 89% 最终失败。

约 53% 的失败触及成本或步数上限，很多甚至在真正编辑之前就耗尽预算，说明瓶颈主要在定位和循环控制，而不只是 patch 生成。

因此，只训练成功轨迹仍有缺口：模型会模仿成功路径，却没直接学习“重复搜索十次是一种坏状态”。后续 RL 或过程 verifier 应显式惩罚无信息增益的循环。

## 10. 局限与数据风险

1. **Synthetic-to-real gap**：AST 删除和多 bug 组合不一定符合真实开发者错误分布。
2. **测试覆盖偏差**：只有能破坏既有测试的 bug 才能进入数据；未覆盖但重要的行为被系统性排除。
3. **Issue 生成泄漏**：模型看到 diff 与 F2P 测试后生成描述，可能透露过强的定位线索。
4. **成功轨迹选择偏差**：rejection sampling 主要蒸馏老师能解决的路径，不教授失败恢复。
5. **仓库相关性**：同仓库的数百个任务共享代码和环境，随机按任务划分会高估跨仓库泛化。
6. **共享环境漂移**：PR Mirror 使用当前环境而非历史环境，真实性与可运行性之间做了取舍。

## 11. 对实践项目的启示

一个可写进简历的复现不必重建 50k 数据。选择 3 个不在 SWE-bench 的 Python 仓库，实现：

1. `RepoProfile`：Dockerfile、安装命令、测试命令、日志解析器；
2. 两类 AST mutation 与一种 LM Rewrite；
3. 自动执行 clean/broken/fixed 三态验证；
4. 基于失败测试生成 issue，但隐藏测试源码；
5. 用同一小 agent 分别跑 synthetic task 与真实历史 issue；
6. 报告 candidate yield、任务成功率、定位步数、重复率、环境存储/任务。

如果还能做 repository-held-out 切分，并分析哪些 mutation 能迁移到真实 issue，这个项目就从“造 bug 脚本”升级为完整的 Agent 数据研究。

## 12. 读完应能回答

1. Environment-first 为什么比 task-first 更容易扩展？
2. “至少破坏一个测试”证明了什么，又没有证明什么？
3. 为什么直接给失败测试反而可能降低学生泛化？
4. 合成任务应按任务随机切分，还是按仓库切分？
5. 如何利用失败轨迹训练模型退出重复循环？
