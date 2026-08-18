# Code-Agent-Learning

一个面向 Code Agent 的学习与实践仓库。主要记录 Code Agent 相关的经典论文解读、最小 Harness 实现，以及 Tool Use、Agent Loop、Context Compaction、Memory、Subagent、Evaluation 等核心机制。希望通过论文、代码与实验，从零理解一个基础模型如何在 Harness 的帮助下，逐步具备代码理解、工具调用、文件修改和任务执行能力。

## 内容

- [Code Agent 论文阅读路线](./Paper-Reading/README.md)：从 ReAct、SWE-bench 到 SWE-Gym，理解交互、工具、平台、训练与验证的研究主线。
- [从零构建一个 Code Agent：最小 Harness 实践](./最小Code%20Agent%20Harness实践/README.md)：用约 300 行 Python 跑通搜索、阅读、编辑、测试与轨迹记录。
- [Code Agent 核心架构：从最小 Harness 到可信执行系统](./Core-Architecture/README.md)：深入 Agent Loop、Context Manager、Tool Router、Sandboxed Executor 与 Verifier。

## 建议学习顺序

先运行最小 Harness，建立对完整闭环的直觉；再阅读核心架构系列，理解一个教学原型走向可靠系统时必须补齐的控制面；最后带着“状态、动作、观察、环境、验证和预算”六个问题回看论文，会更容易区分模型能力与 Harness 设计带来的改进。
