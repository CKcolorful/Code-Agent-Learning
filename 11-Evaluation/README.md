# Evaluation：如何证明 Code Agent 真的变好了

Verifier 回答“当前 revision 是否满足当前任务的验收条件”；Evaluation 回答的是另一个问题：**某个模型 + Harness + 工具 + 环境配置，在一组任务分布上是否比基线更可靠、更高效、更安全？**

一次测试通过不能证明系统变好，一次 Benchmark 分数也不能解释改进来自模型、检索、编辑协议还是评测泄漏。Evaluation 是实验系统，而不是排行榜脚本。

## 一、评测的基本对象

```text
Task       一道问题、初始环境和成功标准
Trial      某个配置对某 Task 的一次随机运行
Trajectory Trial 的完整交互与状态变化
Grader     对 Trial 的某个维度打分
Run        一批 Task × Repeat × Configuration
Report     带统计不确定性和切片分析的结论
```

模型非确定性意味着同一任务要重复 Trial。只跑一次得到的是样本，不是稳定能力估计。

## 二、真正被评测的是系统配置

记录不可缺少的 Evaluation Manifest：

```yaml
agent:
  harness_commit: 8f2c...
  model: provider/model-id
  reasoning_effort: medium
  prompt_version: p17
  tool_registry_version: t9
  sandbox_policy: s4
environment:
  image_digest: sha256:...
  cpu: 4
  memory_gb: 8
  network: disabled
dataset:
  name: internal-maintenance-v3
  split_hash: sha256:...
  task_count: 120
execution:
  repeats: 5
  max_steps: 60
  token_budget: 180000
```

不记录产品配置却把结果归因给单一模型，会混淆真正的实验单位。

## 三、Task Schema

每道任务至少包含：

- 固定 base commit 和可构建环境；
- 用户可见需求；
- setup/start 脚本；
- 公开测试与隐藏 grader；
- 时间、Token、网络和工具预算；
- 允许与禁止的操作；
- 多维验收条件；
- 数据来源、许可和污染风险；
- 环境基线验证结果。

```python
@dataclass
class EvalTask:
    task_id: str
    repo_url: str
    base_commit: str
    prompt: str
    setup_spec: dict
    policy: dict
    graders: list[str]
    slices: list[str]
    provenance: dict
```

任务本身必须先验证：在 base commit 上应失败，在参考修复或人工可接受实现上应通过，环境重复构建结果应稳定。

## 四、Grader 不是只有单元测试

### 1. Functional Grader

运行隐藏和公开测试，检查行为正确性。它是强证据，但测试覆盖不完整、可能 flaky，也可能被 Agent 投机绕过。

### 2. Patch Grader

检查路径、API、依赖、生成物、禁改文件、diff 大小和测试删除。它能发现“让测试绿但破坏项目”的 patch。

### 3. Static/Security Grader

类型、lint、漏洞扫描、secret、危险权限和依赖策略。

### 4. Trajectory Grader

评估工具使用、审批绕过、是否读取关键证据、无进展循环和破坏性尝试。用于诊断，不应随意替代最终功能判断。

### 5. Model Grader

适合可读性、解释质量或开放式设计，但需要 rubric、正反例、盲化、校准集和人工一致性检查。模型 grader 不应看到会泄漏实验组的信息。

### 6. Human Review

用于校准自动 grader、处理争议和评估维护性。报告要记录评审者、盲化方式和一致性，而不是把“专家认为不错”当精确真值。

## 五、Pass 不应掩盖约束违反

可以采用多维报告而不是一个混合总分：

```text
functional_pass
regression_pass
policy_pass
security_pass
patch_quality
cost
latency
```

对关键约束使用 gate：功能通过但泄漏凭据或删除测试，Trial 仍然不能计为 resolved。权重平均会让严重安全失败被高功能分抵消。

## 六、核心指标

### 结果指标

- `resolved_rate`；
- pass@1 / pass@k；
- criterion coverage；
- regression rate；
- false success rate；
- policy violation rate。

### 效率指标

- Token、API 成本、墙钟时间；
- 模型/工具调用数；
- cost per resolved task；
- time to first valid patch；
- sandbox 和 verification 占比。

### 轨迹指标

- relevant-region recall；
- repeated action/no-progress；
- retry/recovery；
- edit conflict；
- verifier attempts；
- human approval count。

平均值必须配分位数。一个平均 10 分钟的 Agent 可能有 10% 任务卡到一小时。

## 七、统计：不要被几个百分点欺骗

对同一任务比较两个配置时使用 paired design，并报告：

- 每个配置的重复次数；
- 任务级差值；
- bootstrap confidence interval；
- 成功率的适当区间估计；
- 成本和延迟分布；
- 多次尝试的停止规则。

任务只有几十道时，2% 的差异往往没有意义。先做功效分析或至少诚实报告不确定性，不要只给带两位小数的排行榜。

模型随机性、基础设施噪声和 grader 不稳定要分开测：同一 patch 重复 grading，测 grader variance；同一配置重复 trial，测 agent variance。

## 八、数据切片比总分更重要

建议按这些维度切片：

- bug fix / feature / refactor / migration；
- 单文件 / 多文件 / 跨服务；
- 语言和构建系统；
- 需要定位、规划、编辑、调试的强度；
- 是否需要用户澄清；
- 测试时长和环境复杂度；
- 安全风险；
- 新仓库与熟悉仓库。

一个改动可能提高局部 Python bug fix，却降低长任务和 TypeScript monorepo；总分会把这种回归平均掉。

## 九、Ablation：证明是哪一层有效

每次只改变一个主要变量：

- 相同模型，开/关 Repository Intelligence；
- 相同轨迹预算，比较编辑协议；
- 相同 Harness，更换模型；
- 相同任务，开/关强制 Verifier；
- 单 Agent 与 Subagent；
- 静态计划与动态重规划。

如果同时升级模型、prompt、工具和环境，只能说明“新系统整体不同”，不能得到架构结论。

可以加入 Oracle：给正确文件、正确计划或参考测试，估计各阶段的能力上限。Oracle localization 后仍失败，说明瓶颈不在检索。

## 十、Benchmark 污染与评测投机

公开 Issue、参考 patch 和测试可能进入训练数据。缓解方式：

- 使用训练截止日期之后的任务；
- 保留私有或滚动测试集；
- 记录 task provenance；
- 对 reference patch 做访问隔离；
- 不把 hidden tests 放进 Agent workspace；
- 监控异常精确复现参考 patch 的行为；
- 同时使用合成扰动和真实维护任务。

Agent 还可能修改测试、读取 grader、硬编码输出或利用环境漏洞。Sandbox、路径策略和 patch grader 是评测可信度的一部分。

## 十一、基础设施噪声

失败前先分类：

```text
agent_failure
grader_failure
setup_failure
dependency_failure
network_failure
timeout_infra
flaky_test
invalid_task
```

Infra 失败不能简单算 Agent 错，也不能全部丢弃。报告排除规则、数量和按配置分布；如果某配置更容易触发 OOM，这可能就是系统缺陷而非纯噪声。

为任务做 baseline health check，并将 setup phase 与 agent phase 分离。使用固定镜像 digest、锁文件和资源限制，记录所有动态依赖。

## 十二、Trajectory 评测的价值与边界

最终 patch 相同的两条轨迹，成本和风险可能完全不同：一条直接定位并验证，另一条读取密钥、尝试危险命令后偶然成功。

Trajectory 可用于：

- 找首个致命偏离点；
- 建立失败分类；
- 优化工具描述和上下文；
- 训练过程奖励或筛选数据；
- 发现 benchmark loophole。

但不要要求唯一“正确思维路径”。只评估可观察行为、证据和约束，允许多种有效策略。

## 十三、Eval Pipeline

```python
for task in dataset:
    assert baseline_health(task)
    for config in configurations:
        for seed in seeds:
            env = provision(task, config.environment)
            trial = run_agent(task, config, env, seed)
            frozen = freeze_artifacts(trial)
            grades = [grader.grade(task, frozen) for grader in task.graders]
            store_trial(task, config, seed, trial.trace, grades)

report = analyze_paired_trials()
publish_manifest_and_confidence_intervals(report)
```

Grader 在冻结后的副本上运行，避免 Agent 或后续 grader 相互影响。每个 grade 绑定 artifact hash 和 grader version。

## 十四、怎样评测 Evaluation 系统本身？

- 用已知正确、已知错误和对抗 patch 测 grader；
- 对测试做 mutation testing，检查能否抓住故意缺陷；
- 重复运行同一 frozen patch 测稳定性；
- 比较自动 grader 与盲化人工评审；
- 注入隐藏测试泄漏、测试删除和硬编码；
- 审计无效任务和排除规则；
- 在不同基础设施重复小样本。

如果 grader 无法区分明显好坏 patch，扩大 Agent Eval 只会更昂贵地制造噪声。

## 十五、常见误区

### SWE-bench 分数等于真实生产能力

单一 benchmark 只覆盖特定任务分布和环境，应与内部任务、长任务、安全和人工 review 指标结合。

### 跑一次就比较

Agent 非确定性会让小样本结论翻转。至少对关键任务重复 trial。

### LLM Judge 能解决所有开放式评分

Judge 也有偏差、泄漏和不稳定，需要校准与确定性 gate。

### 隐藏测试越多越公平

测试错误或过拟合参考实现会拒绝有效方案。需要多种 grader 和争议审计。

### 只优化 resolved rate

成本、延迟、安全和 false success 可能同时恶化。生产系统需要多目标报告。

## 十六、从当前 Harness 演进

### v0.2：本地 Micro-Eval

从现有 token TTL 示例扩展 10～20 道小任务，固定 base commit、预算和 grader。

### v0.3：Trial Manifest 与重复运行

记录模型/Harness/工具/环境版本，对每任务重复运行并保存轨迹。

### v0.4：多 Grader 与切片

加入功能、patch、安全和成本报告，按任务类型定位回归。

### v0.5：Ablation CI

对 Harness 核心模块修改运行小型 paired suite；大评测定期运行并报告置信区间。

## 十七、检查题

1. Verifier 与 Evaluation 的输入和结论分别是什么？
2. 为什么评测单位是模型加 Harness 的配置，而不只是模型名？
3. Oracle localization 能帮助定位什么瓶颈？
4. 怎样区分 Agent 随机性与 Grader/基础设施噪声？
5. 为什么安全失败不应被功能分数加权抵消？

## 参考资料

- [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- [SWE-bench: Can Language Models Resolve Real-World GitHub Issues?](https://arxiv.org/abs/2310.06770)
- [SWE-bench Verified](https://www.swebench.com/verified.html)
- [SWE-Gym: Training Software Engineering Agents and Verifiers](https://arxiv.org/abs/2412.21139)
- [SWE-Explore](https://arxiv.org/abs/2606.07297)
- [OpenAI Evals design guide](https://platform.openai.com/docs/guides/evals)
