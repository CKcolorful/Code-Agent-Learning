# 架构决策矩阵：从源码选择自己的 Harness

源码阅读的终点不是模仿某个产品，而是形成决策能力。下面用约束反推设计。

## 场景 A：SWE-bench 研究基线

优先选择：mini-SWE-agent 风格。

```text
Model Protocol + Environment Protocol + 线性 Trajectory + 外部 Grader
```

理由：变量少，容易替换模型和环境；Trial 可批量运行。不要过早加入复杂 Session Tree、插件热加载或人工审批，否则 Harness 变化会干扰实验归因。

必须补齐：容器资源限制、revision 绑定、原始输出 Artifact、失败分类和可重试基础设施错误。

## 场景 B：个人终端 Agent

优先选择：Pi 风格。

```text
通用流式 Agent
  + AgentSession
  + parent-linked JSONL
  + Extension API
  + Project Trust
```

理由：用户重视交互、恢复、分支和定制，单机 JSONL 足够透明。扩展默认不能视作安全边界；执行不可信仓库仍要配合容器或 OS Sandbox。

## 场景 C：同一内核组装 Web、Headless 和企业变体

优先选择：DeepSeek Harness 风格。

```text
Scope-aware Context
  + reversible effects
  + typed event domains
  + Profile/Bundle/Patch
  + capability seams
```

理由：产品差异可以通过组合表达，而不是复制分支。代价是需要有效配置检查器、插件图诊断、生命周期测试和兼容性治理。

## 场景 D：在开发者主机上执行真实命令

优先选择：Codex 风格的控制面。

```text
Thread protocol
  + Session-owned concurrency
  + per-turn policy snapshot
  + approval state machine
  + OS-enforced sandbox
  + process supervision
```

理由：UI 断线、用户 steering、后台进程、权限升级和恢复都必须有确定性语义。只在 prompt 中写“不要访问敏感文件”不能作为安全控制。

## 关键选择题

### 1. 线性历史还是事件日志？

若只需一次 Trial，线性消息足够；若需要 fork、resume、多 UI、异步控制事实，就需要 Entry/Event 与 model view 分离。

### 2. 类替换还是插件树？

只有少数实现变体时，显式构造和 Protocol 更易读；能力由第三方组合、需要热卸载和 per-agent scope 时，插件系统才值得。

### 3. Hook 还是 Policy Engine？

格式化、遥测、附加上下文可以用 Hook；决定命令能否越权执行的规则应进入确定性 Policy，并由 Sandbox 强制。安全关键 Hook 还要定义 fail-open/closed。

### 4. 摘要还是结构化状态？

自然语言 summary 适合压缩讨论；任务目标、文件集合、验证 revision、预算和权限属于结构化状态。不要让压缩模型成为恢复安全状态的唯一来源。

### 5. 工具并行还是顺序？

只读、互不依赖调用可以并行；写文件、进程控制和共享 cwd 默认应顺序执行或声明冲突域。模型一次发出多个 Tool Call 不代表它们可以安全并发。

## 最小演进路线

```text
阶段 1：mini Loop + Trace
阶段 2：Verifier + Policy + Environment isolation
阶段 3：Session/Event 与 Resume
阶段 4：Context Compaction + structured state
阶段 5：Extension/Plugin 与 scope
阶段 6：多宿主协议、审批、OS Sandbox、进程监督
```

每个阶段都应由真实失败推动。没有分支需求就不引入树；没有第三方生态就不引入 HMR；没有不可信执行就不假装一个 cwd 检查是沙箱。
