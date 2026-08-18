# CodeAct 详读：为什么“可执行代码”可以成为 Agent 的动作语言

论文：[Executable Code Actions Elicit Better LLM Agents](https://proceedings.mlr.press/v235/wang24h.html)

官方代码：[xingyaoww/code-act](https://github.com/xingyaoww/code-act)

发表：ICML 2024｜作者：Xingyao Wang、Yangyi Chen、Lifan Yuan 等

## 一句话结论

CodeAct 的价值不只是“让模型写 Python 调工具”，而是把工具调用从一个个离散 API，提升为带变量、分支、循环和异常反馈的可编程动作空间。它减少了复杂工具组合所需的 Agent Loop 轮次，但也把类型检查、权限隔离和可审计性从 Tool Router 推向了代码执行沙箱。

## 1. 论文真正挑战的假设

常见 Agent 把动作写成 JSON 或约定文本：

```json
{"tool": "search", "arguments": {"query": "..."}}
```

这种接口容易解析，也便于逐工具授权，但一次动作通常只表达一次调用。若任务需要“搜索多个关键词，将结果去重后再分别查询详情”，模型需要多轮地产生动作，harness 还要替它保存中间变量。

CodeAct 改成：

```python
queries = ["agent benchmark", "software engineering agent"]
items = []
for query in queries:
    items.extend(search(query))
unique = deduplicate(items)
print([get_detail(x.id) for x in unique[:5]])
```

这里代码不只是另一种序列化格式。循环是控制流，变量是数据流，函数组合是工具编排，解释器错误又天然形成 Observation。也就是说，动作本身变成了一个小程序。

## 2. CodeAct 在 Agent Loop 中的位置

论文将交互分为 Agent、User、Environment 三类角色。模型可以向用户输出自然语言，也可以向环境输出可执行代码：

```text
User instruction
      ↓
LLM: Thought + Python Action
      ↓
Interpreter / packages / external APIs
      ↓
stdout + result + exception
      ↓
LLM revises the next action
```

第 `t` 轮策略仍可写成：

```text
a_t ~ πθ(a | user_request, a_1, o_1, ..., o_t)
```

不同在于 `a_t` 不再是一个有限工具名，而是解释器可接受的程序。动作空间表达力显著增大，Tool Router 的工作从“选择某个工具并填参数”变为“向执行器暴露受控函数和库，并运行一段组合逻辑”。

## 3. 为什么代码动作可能更有效

论文给出四个互相关联的理由：

1. **预训练先验**：模型在预训练阶段见过大量代码，而特定 JSON tool schema 往往需要额外微调。
2. **控制流与数据流**：分支、循环、变量和函数组合是语言原生能力，不必为每种组合重新定义工具。
3. **软件生态复用**：在权限允许时，模型可直接调用成熟 Python 包，不必将每个能力包装成独立 API。
4. **自动反馈**：语法错误、类型错误和 traceback 已是结构化环境反馈，可支持多轮 self-debug。

但“表达力更强”不等于“任何任务都更安全”。当动作只是 `get_weather(city)` 时，JSON schema 的约束反而有价值；当动作需要跨多工具计算，代码的优势才明显。动作空间应该按任务复杂度分层，而不是全局二选一。

## 4. 实验一：先隔离掉组合能力

为了判断优势是否只来自循环与组合，论文先在 API-Bank Level-1 上比较原子调用：每个样本只需调用一次工具，分别输出 Python、JSON 或文本格式。

结果并非 CodeAct 全胜：

- 17 个模型中，CodeAct 在 8 个模型上是最佳格式，JSON 为 5 个，文本为 4 个；
- 开源模型中 CodeAct 或文本更常占优，JSON 明显偏弱；
- 部分闭源模型的 JSON 更好，合理推测是它们针对 function calling 做过专门训练。

这个对照很重要。它说明代码格式本身没有神奇优势；模型训练分布与接口熟悉度会改变结果。CodeAct 的核心收益应该在需要组合的任务上验证。

## 5. 实验二：M3ToolEval 测什么

作者构造了 M3ToolEval：82 个人工任务，覆盖网页浏览、金融、旅行规划、科学和信息处理等领域。任务通常需要多次调用多个工具，最多允许 10 轮交互，不提供 few-shot 示例。

关键结果：

- CodeAct 在 17 个模型中的 12 个取得最高成功率，也在 12 个模型上使用最少平均轮次；
- GPT-4-1106-preview 使用 CodeAct 达到 74.4%，文本为 53.7%，绝对提升 20.7 个百分点；
- 同一模型平均轮次从文本的 7.7 降到 CodeAct 的 5.5；
- 最好的开源模型仅 13.4%，同期最好闭源模型为 74.4%，说明动作语言不能补偿底层任务能力差距。

这组数据支持的是：**当模型已经具备较强代码和规划能力时，可编程动作能把多次工具调用压缩进一次动作**。它不能推出 Python 对所有模型、所有任务都优于 schema 化工具。

## 6. 少轮次为什么不等于低成本

一次 Python Action 可能包含十次 API 调用。于是：

```text
Agent turns ↓  ≠  Tool calls ↓  ≠  wall time ↓  ≠  dollar cost ↓
```

工程评测至少要分别记录：模型轮次、解释器内工具调用次数、输入输出 token、执行时间、外部 API 成本与失败重试。否则“少 30% actions”可能只是把动作藏进解释器内部。

Code Agent 中尤其如此：一条 shell/Python 动作可以递归搜索整个仓库、启动完整测试或安装大量依赖。预算管理不能只放在 Agent Loop 外层，还必须插入执行器与网络层。

## 7. CodeActInstruct 训练了什么

作者进一步构造约 7,000 条多轮 CodeActInstruct 轨迹，并与通用对话数据混合微调 Llama 2 和 Mistral 7B，得到 CodeActAgent。数据覆盖信息检索、软件包使用、外部记忆和机器人规划，并有意保留“执行失败—读取错误—修正代码”的过程。

这里最值得迁移的不是 7k 这个数字，而是轨迹筛选原则：

- 训练目标不是只复刻最终答案，而是学习动作与真实 Observation 的条件关系；
- 需要保留能够从错误恢复的轨迹，而不只是一次成功的干净程序；
- 还要混合一般对话数据，避免模型只会对环境发代码、不会与用户沟通。

## 8. 对 Code Agent harness 的直接启示

CodeAct 会重新划分五个核心模块的责任：

| 模块 | 使用 CodeAct 后新增的责任 |
| --- | --- |
| Agent Loop | 区分自然语言回复与代码动作，限制轮次并处理解释器异常 |
| Context Manager | 保存变量摘要、关键 stdout、异常与文件系统副作用，而非机械保留全部日志 |
| Tool Router | 向解释器注入白名单函数、类型包装、调用计数与授权策略 |
| Sandboxed Executor | 限制文件、网络、进程、CPU、内存、时间和依赖安装 |
| Verifier | 检查最终环境状态和测试结果，不能把“代码执行成功”当作任务成功 |

一个可落地的折中是“双层动作空间”：搜索、读取、编辑、测试等高频操作保留显式工具；只有需要组合数据流时才进入受限 Python。这样既保留审计边界，又避免 Tool Router 膨胀成数百个细粒度函数。

## 9. 论文没有解决的风险

1. **任意代码执行风险**：代码动作可以读取凭据、发起网络请求、启动子进程或制造资源耗尽，必须默认不可信。
2. **可审计性下降**：一个 JSON call 容易逐次审批，一段程序的真实调用图要运行后才完全显现。
3. **状态漂移**：交互式解释器的变量、导入和工作目录会跨轮次残留，重放轨迹时必须恢复同一状态。
4. **依赖不稳定**：直接调用软件包扩大能力，也引入版本、平台和供应链差异。
5. **评测边界有限**：M3ToolEval 只有 82 个任务，且不是仓库级软件维护；不能直接等价为 Code Agent 修复能力。

## 10. 最小复现实验

在同一模型、同一任务集上实现三种动作协议：

```text
A. JSON: 每轮只能调用一个工具
B. Code: 可在受限 Python 中调用白名单工具
C. Hybrid: 简单操作用 JSON，复杂编排用 Python
```

准备 30 个任务，其中一半只需单工具，一半必须做循环、过滤或组合。记录成功率、解析错误率、模型轮次、真实工具调用数、总 token、执行时长和越权尝试。再关闭 Code 模式的循环或持久变量，分别做消融。

如果 Code 只在组合任务上提高成功率并降低模型轮次，而原子任务差异很小，你就复现了论文最核心的因果结论。若 Hybrid 在安全违规和成功率之间更平衡，则得到比“照搬 CodeAct”更有工程价值的结果。

## 11. 读完应能回答

1. CodeAct 与把 function calling 写成 Python 语法有什么本质差别？
2. 为什么 API-Bank 原子调用实验必须先做？
3. 一次代码动作包含多次工具调用时，预算应在哪几层统计？
4. traceback 是 Observation，但为什么不是 Verifier？
5. 你的 harness 中哪些工具适合显式 schema，哪些适合可编程组合？
