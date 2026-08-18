# mini-SWE-agent 源码实验

这些实验不要求真实模型额度。优先使用项目中的 Test Model 或为 Protocol 写一个固定响应的 Fake Model，才能把 Harness 行为与模型随机性分开。

## 实验 1：验证超时是否清理子进程

目标：证明 `killpg`不是无关实现细节。

1. 构造 Action，启动会持续写心跳文件的子进程；
2. 让父 shell 等待，使命令触发 Environment timeout；
3. 超时后检查心跳文件是否继续增长；
4. 在临时分支把进程组清理改成只 `process.kill()`，重复实验；
5. 记录两个版本是否留下子进程。

验收证据包括命令返回结构、父子 PID、超时后进程列表和心跳文件大小。实验完成后恢复源码，不要把故意回归提交到主分支。

## 实验 2：格式错误的费用一致性

构造 Fake Model：第一次抛出带 `extra.cost=0.02`的 `FormatError`，第二次返回提交 Action。检查：

- `n_calls`是否包含两次请求；
- `cost`是否包含失败请求；
- Trajectory 是否同时出现纠错消息与最终 exit；
- 达到 `max_consecutive_format_errors`时 exit status 是否改变。

再加入“错误、成功、错误”的序列，验证成功一步会重置连续错误计数。

## 实验 3：区分容器状态与 shell 状态

在 Docker Environment 连续执行：

```bash
mkdir -p /tmp/mini-state && cd /tmp/mini-state && export DEMO_FLAG=yes && touch kept.txt
pwd; printf '%s\n' "$DEMO_FLAG"; test -f /tmp/mini-state/kept.txt; echo $?
```

预期：文件保留，但第二次 Action 的 cwd 回到配置值，`DEMO_FLAG`不存在。然后显式传递 cwd，观察执行位置如何改变。

## 实验 4：输出截断是否改变决策

准备一个命令，在长输出中间而不是头尾放置唯一错误线索。设置两组 Observation Policy：

- A：默认头尾截断；
- B：提取错误行、退出码和附近上下文。

使用固定规则 Agent 比较能否定位线索，并保存模型实际看到的 Observation。这个实验说明：工具执行正确不等于 ACI 有效，Observation 形状会改变 Agent 可用信息。

## 建议提交物

```text
labs/mini-swe-agent/
├── fake_model.py
├── test_format_cost.py
├── test_process_group_cleanup.py
├── test_container_state.py
├── fixtures/
└── RESULTS.md
```

`RESULTS.md`应包括源码 commit、系统环境、执行命令、预期、实际结果和失败解释。不要只放终端截图；结构化结果才能在上游升级后重新运行。
