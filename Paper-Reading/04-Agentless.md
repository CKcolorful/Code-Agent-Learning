# Agentless 详读：复杂自主循环未必是最优解

论文：[Agentless: Demystifying LLM-based Software Engineering Agents](https://arxiv.org/abs/2407.01489)

官方代码：[OpenAutoCoder/Agentless](https://github.com/OpenAutoCoder/Agentless)

作者：Chunqiu Steven Xia 等｜首次提交：2024 年 7 月

## 一句话结论

Agentless 把仓库级修复明确拆成 Localization → Repair → Validation 三阶段，用多次结构化模型调用代替一个自由漫游的 autonomous loop。论文的关键发现不是“不要 agent”，而是定位召回、候选多样性和验证选择往往比长程自主规划更决定结果。

## 1. 它在反驳什么默认假设

SWE-agent 展示了工具闭环的价值，但自主 agent 也会产生新的成本：

- 一边搜索一边修改，错误假设容易污染工作树；
- 轨迹长、Observation 多，状态会过期或互相矛盾；
- 同一动作循环，token 与执行预算不可预测；
- 最终系统难以判断失败究竟来自定位、生成还是验证；
- 不同任务的轨迹差异大，不容易批量并行。

Agentless 的问题是：对于 SWE-bench 这类输入和输出都相对明确的任务，是否真的需要一个自由度很高的 agent loop？如果把软件修复拆成几个可测量阶段，再在每阶段使用强模型，会不会更简单、更便宜、更容易分析？

“Agentless”是带立场的命名。它并非完全没有决策或模型调用，而是没有让一个模型在环境中持续自主选择任意工具；控制流主要由程序预先规定。

## 2. 总体数据流

```text
Issue + Repository
        |
        v
1. Localization
   仓库 -> 文件 -> 类/函数 -> 编辑位置
        |
        v
2. Repair
   结构化上下文 + 多次采样 -> 多个候选 patch
        |
        v
3. Validation
   过滤不可应用/回归候选 + 复现测试 + 排序
        |
        v
   Final patch
```

三阶段分别优化不同条件概率。设真实位置为 `L*`，正确 patch 为 `p*`：

```text
P(success)
≈ P(L* in localized context)
  × P(correct patch generated | L*)
  × P(correct patch selected | candidates)
```

这个分解让系统能独立测量：定位是否覆盖 gold location、候选集合中是否已有正确答案、selector 是否把它选出来。

## 3. 阶段一：分层 Fault Localization

完整仓库无法直接塞入 prompt。Agentless 采用从粗到细的分层定位。

### 3.1 文件级定位

论文比较两条路线：

- 让 LLM 阅读仓库结构和 issue，直接预测相关文件；
- 用 embedding 根据语义相似度召回文件。

报告的文件级 top-k 覆盖率约为：

| 方法 | Localization rate |
| --- | ---: |
| LLM prompt | 78.7% |
| Embedding | 67.7% |
| 二者组合 | 81.7% |

组合只比 LLM 单独高 3 个百分点，却说明两者错误不完全一致。embedding 擅长语义近似与稳定批处理；LLM 能利用目录名、架构常识和 issue 中的因果线索。

这里的指标不是最终 resolved rate，而是 gold patch 相关文件是否被候选集合覆盖。高召回优先于高精度：漏掉责任文件，后面再强的 repair 都无能为力；多带一两个无关文件则主要增加上下文成本。

### 3.2 文件 skeleton

相关文件仍可能很长。Agentless 把代码压缩成 skeleton：保留类、函数、方法签名和层级结构，去掉大部分函数体。

论文报告，这种表示可把超过 3,000 行的代码压缩到 800 行以内。Skeleton 的目的不是让模型直接修复，而是回答：

- 哪个类拥有目标职责？
- 哪个函数名与 issue 语义相关？
- 类/函数之间的嵌套和邻接关系是什么？

它利用了一个程序结构事实：定位阶段通常先需要“地图”，而非每个房间里的全部物品。

### 3.3 符号级与位置级定位

模型基于 skeleton 预测相关 class/function，再查看这些位置的具体实现，最终输出待编辑的行或代码片段。

从 coarse-to-fine 的好处是每轮 prompt 任务单一：

```text
仓库级：哪些文件？
文件级：哪些符号？
符号级：哪些具体位置？
```

缺点是误差级联。第一层漏掉文件，后两层无法恢复；第二层 skeleton 去掉了关键动态逻辑，也可能选错函数。

## 4. 阶段二：Repair 为什么要多候选

定位结果和 issue 一起构成 repair prompt。模型不是一次生成一个 patch，而是对多个定位样本、多次采样。

论文设置中大致使用 4 组 location samples，每组生成 10 个 patch，形成最高约 40 个原始候选。多候选利用了两个事实：

- 定位存在不确定性，不应把全部预算押在一个位置上；
- 即使位置正确，修改逻辑、边界处理和 patch 格式也存在采样方差。

### 4.1 Search/Replace diff

Agentless 让模型输出结构化 search/replace：给出文件、旧代码片段和新代码片段。应用器要求旧片段能在当前文件中匹配。

相比自由 unified diff，这种格式：

- 降低手算行号的需求；
- 让应用失败更易诊断；
- 可检查旧片段是否唯一匹配；
- 适合批量生成和去重。

它也有局限：旧片段过短可能多处匹配，过长则容易因空格或上下文差异应用失败；大范围重构不适合简单替换。

### 4.2 为什么候选多样性比“写更长计划”有时更有效

长轨迹把预算投入同一条假设并不断修正；多候选则把预算分散到多条相互独立的假设。若模型常在早期锁定错误方案，独立采样能降低路径依赖。

但候选数量只有在 selector 有能力时才有价值。否则正确 patch 虽在集合中，也可能被一个看起来合理但不完整的 patch 排在后面。

## 5. 阶段三：Patch Validation 的三层筛选

### 5.1 基础过滤

先去掉无法应用、无实际变更、语法明显错误或重复的候选。这层不判断语义正确，只减少垃圾候选。

### 5.2 Regression tests

运行仓库已有测试，排除破坏既有行为的 patch。论文的选择结果中，仅靠多数投票约解决 77 个任务，加入回归信息后约为 81 个。

回归测试只能证明“没破坏被覆盖的旧行为”，不能证明 issue 已修复。一个什么都没做的 patch 也可能通过全部旧测试。

### 5.3 Reproduction tests

系统根据 issue 生成复现测试，并在两个状态运行：

```text
Base repository: Issue reproduced
Candidate patch:  Issue resolved
```

只有修复前能暴露问题、修复后转为通过的测试，才具有区分力。若测试在 base 上本来就通过，它没有复现 bug；若在所有候选上都失败，它可能写错或环境不完整。

加入 reproduction tests 后，论文在 SWE-bench Lite 上选择到 96/300 个正确任务，即 32%。这比回归验证的 81 个明显提升，说明面向 issue 的动态证据比代码表面相似度更有判别力。

## 6. 主结果应该怎样读

Agentless 在论文设置下解决 SWE-bench Lite 的 96/300，即 32%，平均成本约 0.70 美元/issue。

这支持三个结论：

1. 简单、固定的 pipeline 可以成为强基线，复杂 autonomous loop 不是性能的必要条件。
2. 把预算用于多位置、多 patch 和执行选择，可以胜过把同样预算集中在一条长轨迹。
3. 模块化系统更容易并行和缓存，例如所有 localization 可以批量完成，候选生成也可并行。

它不支持“agent 永远不如 pipeline”。论文比较受具体模型、预算和工具设计影响；对需要安装探索、交互调试、非标准运行环境或需求澄清的任务，自主循环仍可能更适合。

## 7. 最关键的 Oracle 分析：Selector Gap

论文统计，所有生成候选中理论上可解决约 126/300 个任务，即 42%；最终验证流程选择并提交的只有 96/300，即 32%。

这 10 个百分点是 selector gap：

```text
candidate recall = 42%
selected success = 32%
selection gap = 10 percentage points
```

它改变了优化优先级。如果候选集中已存在大量正确 patch，继续提高采样数量的边际收益可能小于改进 verifier。

还要注意，42% 是“事后用隐藏 benchmark 判据判断候选是否正确”的 oracle，线上系统无法直接知道。研究目标就是用可见测试、静态特征、模型 verifier 或多信号排序逼近这个 oracle。

## 8. Benchmark 人工分析带来的提醒

论文对 SWE-bench Lite 实例做了人工分析，指出部分任务可能：

- issue 中包含接近答案的提示；
- 描述不足，无法唯一推导开发者意图；
- gold patch 涉及非必要改动；
- 测试覆盖有限，使投机修复也能通过；
- 对某些系统存在数据泄漏或可记忆性。

这不是说 benchmark 无效，而是说 resolved rate 同时测量 agent 能力与任务判据质量。研究者应报告具体 patch 和轨迹，而不是只引用一个百分比。

## 9. 与 SWE-agent 的正确对照

| 维度 | SWE-agent | Agentless |
| --- | --- | --- |
| 控制流 | 模型动态选择下一动作 | 程序预先规定三阶段 |
| 搜索 | 交互式，边看边改 | coarse-to-fine 批量定位 |
| 修复 | 一条轨迹迭代 | 多位置 × 多次采样 |
| 验证 | agent 自己运行和判断 | 独立 validation pipeline |
| 优点 | 灵活，能响应实时错误 | 可并行、可测量、成本稳定 |
| 风险 | 循环、状态漂移、预算不稳 | 误差级联、缺少环境适应 |

二者不是互斥架构。一个现代系统可以：先用 Agentless 式定位与候选生成，再让 agent 对最有希望的候选做交互调试；或先让 agent 生成复现，再用批量 repair/validation 扩展候选。

## 10. 三阶段的失败归因框架

对失败实例，不要只写“模型没修好”。按下面归因：

### Localization failure

gold 文件未进入候选、函数选错、skeleton 丢失关键动态逻辑。此时扩大生成次数几乎无效。

### Generation failure

位置正确但所有候选都不满足行为；常见原因是误解契约、修改不完整、跨文件影响遗漏。

### Application failure

修改意图可能合理，但 search/replace 无法唯一匹配、生成语法错误或触碰错误路径。

### Validation failure

正确候选已存在却未被选中；复现测试不区分、回归信号不足或排序偏好表面简洁。

### Benchmark/environment failure

容器、依赖、测试超时或任务歧义导致结果无法可信判断。

## 11. 论文方法的边界

- Pipeline 步骤固定，遇到安装失败或意外错误时缺少动态恢复。
- Skeleton 静态保留声明，对运行时注册、元编程和配置驱动逻辑可能不够。
- 文件级错误会级联，后续阶段不能主动回到全仓库重新搜索。
- 生成 reproduction tests 本身是困难问题，错误测试会误导 selector。
- 多候选降低路径依赖，却增加推理与执行总量；0.70 美元是特定价格与配置下的历史数字。
- 投票偏好常见答案，不保证选择语义正确但少数的 patch。

## 12. 官方源码怎么读

仓库结构直接对应论文阶段：

1. [`agentless/fl/`](https://github.com/OpenAutoCoder/Agentless/tree/main/agentless/fl)：fault localization 逻辑。
2. [`agentless/repair/`](https://github.com/OpenAutoCoder/Agentless/tree/main/agentless/repair)：候选 patch 生成与应用。
3. [`agentless/test/`](https://github.com/OpenAutoCoder/Agentless/tree/main/agentless/test)：测试生成与验证相关代码。
4. [`get_repo_structure/`](https://github.com/OpenAutoCoder/Agentless/tree/main/get_repo_structure)：仓库结构和代码表示准备。
5. [`README_swebench.md`](https://github.com/OpenAutoCoder/Agentless/blob/main/README_swebench.md)：按 SWE-bench 流水线运行的命令与产物。

建议选一个 instance id，追踪它在各阶段生成的 JSON/JSONL：文件候选 → 符号位置 → raw patches → normalized patches → test results → final selection。Agentless 最适合以“数据产物”而非“调用栈”方式阅读。

## 13. 常见误读

- **“Agentless 完全不用 agent 技术。”** 它仍使用 LLM 做定位、生成和测试，只是控制流不是开放式 loop。
- **“32% 证明 pipeline 永远优于 autonomous agent。”** 只能证明该设置下 pipeline 是强且经济的方案。
- **“有 40 个候选就有 40 倍成本。”** 部分阶段可批量、并行与缓存，但成本确实随采样增长。
- **“回归测试通过就能选出正确 patch。”** 原论文从 81 到 96 的提升正说明 reproduction test 很关键。
- **“42% candidate recall 就等于系统能力。”** 这是事后 oracle 上界，线上还要解决 selection。
- **“Localization 只需找 gold patch 文件。”** 理解问题还可能需要调用方、测试和配置等非修改文件。

## 14. 可复现练习

### 练习一：建立阶段漏斗

在 100 个任务上分别记录 file recall、function recall、patch applicable rate、candidate oracle success、selected success。画出漏斗，找损失最大的阶段。

### 练习二：候选数曲线

将每个位置采样数设为 1、2、5、10，比较 Pass@k、最终 Best@k、成本与重复 patch 比例。若 Pass@k 上升而 Best@k 不变，瓶颈在 selector。

### 练习三：验证复现测试

对每个生成测试先执行 base/gold 双状态检查。只有 base 失败且 gold 通过的测试才能进入候选排序。统计被过滤测试的原因，避免把测试生成失败误判成 patch 失败。

## 15. 读完后的检查题

1. 为什么 localization 阶段优先追求召回，而不是精度？
2. Skeleton 删除函数体后还能支持什么判断，又会丢失什么？
3. 回归测试与复现测试分别排除哪类候选？
4. 42% 到 32% 的差距为何指向 verifier，而非 generator？
5. 哪些任务特征会让 autonomous loop 比固定 pipeline 更合适？

## 16. 最终要带走的观点

Agentless 的最大价值是把 Code Agent 从“一个模型是否足够聪明”改写成可诊断的系统问题：**先让真实位置进入上下文，再让正确 patch 进入候选集，最后用可靠证据把它选出来。** 自主性只是控制流选择，不是目标；最终目标始终是以可控成本提高这三个阶段的联合成功率。
