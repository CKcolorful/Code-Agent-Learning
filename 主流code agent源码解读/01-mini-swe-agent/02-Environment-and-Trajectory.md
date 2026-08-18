# Environment 与 Trajectory：极小系统仍然需要工程语义

mini-SWE-agent 只有 Bash Action，但“执行 Bash”并非一个 `subprocess.run()`就结束。Environment 定义了进程、工作目录、隔离、超时、环境变量、提交信号和序列化语义。

## 1. Local Environment

[`environments/local.py`](https://github.com/SWE-agent/mini-swe-agent/blob/25941c89cfbc91eb40b3f8756348c91d9977d57e/src/minisweagent/environments/local.py)使用 `subprocess.Popen`，把 stderr 合并进 stdout，并以 UTF-8 replacement 处理非法字节。

关键点是 `start_new_session=os.name == "posix"`。超时时，POSIX 上调用 `killpg(process.pid, SIGKILL)`杀死整个进程组，而不只是 shell 父进程。否则启动后台服务的命令可能留下孤儿进程，继续占用端口、CPU 或修改文件。

Local 后端不是沙箱。它继承宿主环境变量，并以当前用户权限执行命令。源码把它描述为本地执行环境，而不是安全隔离层；对不可信任务应使用容器或额外系统沙箱。

## 2. Docker Environment

[`environments/docker.py`](https://github.com/SWE-agent/mini-swe-agent/blob/25941c89cfbc91eb40b3f8756348c91d9977d57e/src/minisweagent/environments/docker.py)在初始化时启动一个长寿命容器，Action 通过 `docker exec`进入同一容器。

```text
Environment.__init__
  → docker run -d ... image sleep 2h

Environment.execute(action)
  → docker exec -w cwd container bash -lc command

Environment.cleanup
  → docker stop；失败则 docker rm -f
```

这产生两种同时成立的状态语义：

- 文件系统和容器级进程状态可以跨 Action 保留；
- 每次 `docker exec ... bash -lc`创建新 shell，所以 `cd`、普通 shell 变量和未导出的函数不会自然继承。

默认 prompt 明确提醒目录和环境变量变化不持久，这是 ACI 对真实执行语义的补偿。模型如果误以为上一轮 `cd repo`仍有效，下一条命令就会在错误目录运行。

## 3. Observation 截断属于模型视图

Environment 返回完整的 output、returncode 和 exception_info。默认 YAML 的 `observation_template`才决定模型看到什么：低于 10,000 字符时完整发送；否则保留头尾各 5,000 字符，并报告省略字符数。

把截断放在格式化层有两个好处：执行器保持提供原始结果的简单职责；不同 Model 或任务可以采用不同观察策略。但如果格式化器不额外保存 raw output，长输出中间部分不会出现在主消息轨迹。生产可观测性系统应分别保存 raw artifact 和 model-visible observation。

## 4. Trajectory 不是调试日志

`DefaultAgent.serialize()`保存：模型调用数与费用、Agent/Environment 配置和类型、版本、退出状态、submission、完整 messages，以及模型和环境附加的序列化数据。格式字段为 `mini-swe-agent-1.1`。

每轮 `finally`都会调用 `save()`，所以后续步骤崩溃时，前面的轨迹仍大概率已经落盘。不过 Trajectory 不是完整 Checkpoint：默认 `run()`启动时会清空 messages，也没有从文件恢复 Environment 的标准路径。它适合分析和评测，不等于可继续执行的 Session。

## 5. 三种状态不要混淆

| 状态 | 所在位置 | 是否持久 | 用途 |
| --- | --- | --- | --- |
| 对话状态 | `agent.messages` | 写入 Trajectory | 下一次模型请求 |
| 世界状态 | 本地目录或 Docker 容器 | 取决于环境生命周期 | 真实代码和进程 |
| 运行统计 | cost、calls、elapsed | 写入 Trajectory | 预算和评测 |

恢复 Agent 不能只恢复 messages：如果对应的工作树、容器或 revision 不一致，旧 Observation 就变成对另一个世界的描述。这个问题在 Codex 的 Rollout、Thread Store 和工作区状态中会更明显。

## 6. 安全边界

- `cwd`只是执行起点，不限制命令访问其他路径；
- Local 后端默认继承 `os.environ`，可能暴露凭据；
- Docker 隔离强度取决于挂载、网络、capability 和容器配置；
- `forward_env`应采用显式 allowlist；
- timeout 控制时长，但不是 CPU、内存、磁盘或网络配额。

因此 Environment 是“执行抽象”，不自动等于 Sandboxed Executor。阅读任何 Agent 时都应追问：策略最终是否由操作系统或容器边界强制执行？
