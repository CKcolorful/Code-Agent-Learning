# Sandboxed Executor：让不可信代码安全地产生真实反馈

> Code Agent 必须执行仓库里的代码才能获得编译器、测试和运行时反馈；但仓库代码、依赖、构建脚本和模型生成的命令都不能默认信任。Sandboxed Executor 的职责，是在可复现、可回收、可审计的边界内执行这些动作。

## 一、为什么“限制工作目录”不是沙箱？

最小 Harness 做了两件有价值的事情：

1. 文件工具通过 `Path.resolve()` 阻止路径逃逸；
2. `run_command` 使用首词 allowlist、`shell=False`、人工确认和超时。

这些措施能减少误操作，却不能提供系统级隔离。下面的命令首词都可能在 allowlist 中：

```text
python -c "..."
pytest                     # 导入并执行测试与应用代码
npm test                   # 执行 package.json scripts
git ...                    # 访问配置、hooks、credential helper 和远程
cargo test                 # 执行 build.rs 与依赖构建脚本
```

即使 Harness 自己的文件 API 只允许工作区路径，子进程仍可能直接使用操作系统 API：

- 读取 `~/.ssh`、云凭据和环境变量；
- 修改 shell 配置或其他仓库；
- 启动后台进程；
- 访问 Docker socket；
- 连接网络并外传数据；
- fork 大量进程或占满磁盘；
- 通过依赖安装执行恶意脚本；
- 利用内核或容器配置缺陷逃逸。

因此：

```text
路径检查 ≠ 进程隔离
命令 allowlist ≠ 行为 allowlist
人工批准 ≠ 安全执行
容器 ≠ 自动安全
```

## 二、先写威胁模型，再选技术

Sandbox 不是一个布尔开关。要先回答保护谁、抵御什么。

### 需要保护的资产

- 宿主文件和其他项目；
- SSH、Git、云服务与包仓库凭据；
- 用户隐私数据；
- 内网服务；
- Git 远程和生产环境；
- CPU、内存、磁盘、进程与费用预算；
- 评测任务的隐藏测试和答案；
- Harness 自己的配置、日志与控制通道。

### 需要假设不可信的输入

- 模型生成的命令；
- 当前仓库代码；
- README、issue 和日志中的指令；
- 第三方依赖与安装脚本；
- 编译器插件、Git hooks、测试 fixture；
- MCP server 和外部工具结果；
- 下载的二进制与缓存。

### 攻击者或失败来源

1. 模型无意生成危险操作；
2. 仓库内容通过 prompt injection 诱导模型；
3. 恶意或被入侵的依赖；
4. 有意构造的 benchmark task；
5. 用户误批准过宽权限；
6. Sandbox 配置、内核或运行时漏洞。

不同场景需要不同强度。个人可信仓库中的辅助开发，与批量运行来自互联网的 SWE-bench 任务，不能使用同一信任假设。

## 三、Executor 与 Sandbox 的模块边界

Sandbox 提供隔离边界；Executor 提供运行协议。二者组合后至少负责：

```text
prepare  创建环境、挂载代码、安装依赖
execute  启动命令、传入 stdin、流式收集输出
control  超时、取消、资源限制、审批与网络策略
observe  退出码、signal、stdout/stderr、文件变更
snapshot 保存或恢复工作区状态
cleanup  终止进程、卸载资源、销毁临时环境
```

一个清晰接口可以是：

```python
class SandboxedExecutor(Protocol):
    async def create(self, spec: SandboxSpec) -> SandboxHandle: ...
    async def exec(self, handle, request: ExecRequest) -> ExecResult: ...
    async def snapshot(self, handle) -> SnapshotRef: ...
    async def restore(self, handle, snapshot: SnapshotRef) -> None: ...
    async def destroy(self, handle) -> None: ...
```

Agent Loop 不应该知道底层是 macOS Seatbelt、Linux bubblewrap、Docker、远程容器还是 microVM。像 [SWE-ReX](https://github.com/SWE-agent/swe-rex)这样的运行时层，价值就在于把 Agent 逻辑与本地/云端/Docker 执行环境解耦，并统一 shell session、退出码和并行环境接口。

## 四、隔离必须覆盖六个维度

### 1. Filesystem

需要明确：

- 哪些路径可读；
- 哪些路径可写；
- 工作区是 bind mount、copy 还是 overlay；
- `/tmp`、缓存和用户目录是否独立；
- 符号链接怎样处理；
- `.git` 是否可写；
- 设备文件和 Unix socket 是否可见。

推荐的默认边界：

```text
workspace       read-write
base image      read-only
system paths    read-only or invisible
home            empty ephemeral home
secrets         invisible during agent phase
network sockets invisible unless explicitly granted
```

仅做 `resolve()` 路径检查仍可能遇到 TOCTOU：校验路径以后，攻击者在使用前替换符号链接。真正的强边界应由 OS mount namespace、Seatbelt、Landlock、bubblewrap、容器或 VM 强制，而不是只靠应用层先检查一次。

### 2. Network

关闭网络是最简单、最强的默认值。需要联网时，考虑：

- 域名/IP allowlist；
- DNS 是否受控；
- 是否允许内网和 metadata service；
- HTTP/HTTPS 代理；
- TLS 是否检查；
- 上传和下载大小；
- 请求日志；
- 凭据绑定的目标与权限。

只允许 `github.com` 仍可能提供数据外传通道。域名级代理如果不检查 TLS 内容，也不能证明请求只用于下载依赖。网络策略需要与实际威胁模型匹配。

Codex 的公开安全文档描述了两阶段云环境：setup 阶段可以安装依赖，agent 阶段默认离线，setup secrets 在 agent 阶段前移除。这是一种值得借鉴的生命周期分离：**需要凭据的准备动作与处理不可信仓库的自主执行，不应共享同一阶段。** [Codex approvals and security](https://learn.chatgpt.com/docs/agent-approvals-security.md)

### 3. Process

需要限制：

- 可见的进程；
- 最大进程数；
- 后台进程生命周期；
- signal 传播；
- ptrace；
- privileged syscall；
- setuid/capabilities；
- Docker daemon 与宿主 socket。

超时时只杀父进程不够。测试可能启动子进程或守护进程，应终止整个 process group/cgroup，并在销毁环境时二次清理。

### 4. Resource

至少限制：

```text
wall clock time
CPU time / shares
memory
process count
open files
disk bytes / inode count
stdout + stderr bytes
network bytes
```

输出限制不能简单“超过后关闭读取”。如果子进程继续写满 pipe，可能永久阻塞。可以持续消费并把超额部分丢弃或落盘，同时给模型返回截断元数据。

### 5. Credentials

默认不要继承宿主完整环境变量。构造最小环境：

```python
env = {
    "PATH": SAFE_PATH,
    "HOME": EPHEMERAL_HOME,
    "LANG": "C.UTF-8",
    "CI": "1",
}
```

需要凭据时采用：

- 最小 scope；
- 短期 token；
- 只在必要阶段注入；
- 绑定目标服务；
- 不写入工作区和日志；
- 命令结束后撤销；
- 输出脱敏。

把 API key 放入环境，然后让 Agent 任意运行 `env`、测试和网络命令，相当于把秘密交给整个依赖树。

### 6. Time and persistence

环境要有明确生命周期：

- 每任务新建还是跨步骤复用；
- 何时 checkpoint；
- 崩溃后是否恢复；
- 任务结束是否保留 artifact；
- 临时文件、缓存和进程何时清理；
- 环境最长存活时间。

完全每步重建最干净，却会丢失安装和编译状态；全程复用最高效，却可能积累不可见污染。常见折中是每个任务一个隔离环境，步骤间复用，关键点快照，任务结束销毁。

## 五、Permissions 与 Sandbox 是互补层

Claude Code 的公开设计把二者明确分开：权限规则决定工具能否使用，Sandbox 使用 OS 机制限制 Bash 及其子进程可访问的文件和网络。[Sandboxing](https://code.claude.com/docs/en/sandboxing)文档强调 filesystem 与 network 两者都需要：只有文件隔离，进程仍可能从网络下载恶意脚本；只有网络隔离，进程仍可能修改宿主配置形成持久化。

可以把关系写成：

```text
Effective Capability
    = User Intent
    ∩ Tool Policy
    ∩ Approval Scope
    ∩ Sandbox Boundary
    ∩ External Service IAM
```

任意一层都不应扩大上一层权限。

### 为什么批准不能替代 Sandbox？

用户看到的是命令表面，未必知道：

- `npm test` 会运行哪些 scripts；
- `pytest` 会加载哪些 fixture/plugin；
- `make` 最终调用什么；
- 依赖安装是否含 post-install hook；
- 命令是否读取凭据并访问网络。

批准表达意图，Sandbox 限制最坏后果。

### 为什么 Sandbox 也不能替代批准？

即使动作被限制在工作区内，它仍可能：

- 删除用户未提交代码；
- 大范围改写文件；
- 创建错误 commit；
- 修改测试掩盖 bug；
- 使用已授权的外部 API 发送消息。

Sandbox 回答“最多能做什么”，批准回答“这次应该做什么”。

## 六、本地 OS Sandbox、容器和 VM 怎么选？

| 方案 | 隔离强度 | 启动成本 | 环境一致性 | 适用场景 |
| --- | --- | --- | --- | --- |
| 应用层路径/命令检查 | 弱 | 最低 | 依赖宿主 | 教学、可信微型任务 |
| OS Sandbox（Seatbelt/bwrap 等） | 中 | 低 | 接近宿主 | 本地交互式开发 |
| 容器 | 中到强，取决于配置 | 中 | 好 | CI、评测、批量任务 |
| microVM/VM | 强 | 较高 | 好 | 不可信代码、高价值资产 |
| 独立远程机器 | 取决于网络和身份配置 | 高 | 可定制 | 长任务、特殊硬件、企业隔离 |

容器不是天然安全边界。危险配置包括：

- `--privileged`；
- 挂载 `/var/run/docker.sock`；
- 挂载宿主 home；
- 共享 host network；
- root 用户和过多 capabilities；
- 可写系统目录；
- 无资源限制；
- 长期复用含秘密的容器。

强度选择应基于资产和输入可信度，而不是“大家都用 Docker”。

## 七、可复现环境也是 Executor 的职责

Verifier 的结果只有在环境可复现时才有意义。一次运行至少记录：

```yaml
base_commit: b3f6bd9
workspace_patch_hash: sha256:...
image_digest: sha256:...
platform: linux/amd64
executor_version: 0.2.0
setup_commands:
  - pip install -r requirements.txt
environment_allowlist:
  - LANG
  - CI
network_policy: offline
resource_limits:
  cpu: 2
  memory_mb: 4096
  disk_mb: 8192
  timeout_seconds: 120
```

不要只记录镜像 tag，如 `python:3.12`，因为 tag 可能漂移；应记录 digest。依赖也尽量锁定版本和哈希。时间、locale、timezone、随机种子和架构都可能影响测试。

### Setup 失败与 Test 失败要区分

```text
environment_setup_failed  环境未建立，不能评价 patch
command_execution_failed  命令无法启动或被杀
test_failed               测试成功运行，发现代码行为错误
verification_passed       指定检查全部满足
```

如果依赖安装失败，却被统计成“Agent patch 错误”，评测结论会失真。

## 八、工作区快照、Diff 和回滚

每次大动作前保存恢复点：

- Git worktree + diff；
- copy-on-write filesystem snapshot；
- overlay layer；
- 文件级 checkpoint；
- VM snapshot。

快照至少与以下事件绑定：

- 第一次编辑前；
- 批量 patch 前；
- 安装或升级依赖前；
- verifier 通过时；
- 人工接管前；
- 任务暂停或上下文 handoff 前。

回滚不应只恢复 tracked files。Agent 可能创建新文件、修改权限、启动进程、更新缓存或改变数据库。快照边界必须与任务需要一致。

### 并行 Agent 必须隔离写入

多个 Agent 共享同一工作区会产生：

- 文件覆盖；
- 测试结果对应错误 patch；
- `git status` 相互污染；
- 一个 Agent 删除另一个的临时文件；
- 依赖安装竞争。

Git worktree 适合隔离源代码修改，但共享的数据库、端口、缓存和外部服务仍需独立命名空间。不要把“不同目录”误当作完整环境隔离。

## 九、一个 SandboxSpec 应包含什么？

```python
@dataclass(frozen=True)
class SandboxSpec:
    base_image_digest: str
    source_snapshot: str
    writable_mounts: tuple[Mount, ...]
    readable_mounts: tuple[Mount, ...]
    denied_paths: tuple[str, ...]
    network_policy: NetworkPolicy
    environment: dict[str, str]
    secret_refs: tuple[ScopedSecret, ...]
    cpu_limit: float
    memory_bytes: int
    disk_bytes: int
    pids_limit: int
    command_timeout_seconds: int
    total_lifetime_seconds: int
    stdout_limit_bytes: int
    stderr_limit_bytes: int
    run_as_uid: int
```

这些配置应进入事件日志和 verifier 报告。否则，同一个命令今天通过、明天失败时无法判断是代码变化还是环境漂移。

## 十、执行协议：不要只用 subprocess.run

生产执行器需要处理流式、取消和子进程树：

```python
async def exec(handle, request):
    execution_id = new_id()
    await events.append(ExecutionStarted(execution_id, request))

    process = await handle.spawn(
        argv=request.argv,
        cwd=request.cwd,
        env=minimal_env(request.env),
        new_process_group=True,
    )

    try:
        stdout_ref, stderr_ref = await collect_bounded_streams(
            process,
            limits=request.output_limits,
            on_chunk=request.on_output,
        )
        exit_status = await wait_with_timeout(process, request.timeout)
    except TimeoutError:
        await terminate_process_group(process)
        exit_status = ExitStatus.timeout()
    except CancelledError:
        await terminate_process_group(process)
        raise

    changes = await handle.diff_since(request.workspace_revision)
    result = normalize(exit_status, stdout_ref, stderr_ref, changes)
    await events.append(ExecutionFinished(execution_id, result))
    return result
```

需要考虑的边缘情况：

- 输出为非 UTF-8；
- 程序等待 stdin；
- 交互式终端需要 PTY；
- 测试超时但产生部分结果；
- 进程退出后子进程仍存活；
- 命令修改文件后被取消；
- 日志中包含 ANSI 控制符和秘密；
- 环境在结果事件落盘前崩溃。

## 十一、安全测试应该主动攻击边界

### Filesystem 测试

- `../`、绝对路径和 Unicode 路径；
- 指向外部的 symlink；
- 校验后替换 symlink；
- 写入 `.git/hooks`、shell rc 和 PATH 目录；
- 读取 SSH、云凭据、浏览器数据；
- 创建超大文件和大量 inode。

### Network 测试

- 直接 IP；
- DNS rebinding；
- localhost 和云 metadata IP；
- 非标准端口；
- 允许域名上的上传；
- 通过包管理器或 Git 间接联网。

### Process/Resource 测试

- fork bomb 的安全缩小版；
- 无限循环；
- 内存和磁盘耗尽；
- 后台守护进程；
- 超大 stdout/stderr；
- 访问 Docker socket；
- signal 与取消传播。

### Prompt Injection 测试

在 README、测试失败和依赖输出中放置诱导指令，确认即使模型尝试执行，权限与沙箱仍能阻止访问秘密和外传。

测试通过标准不是“模型没有上当”，而是“即使上当也无法突破边界”。

## 十二、怎样评测 Sandboxed Executor？

| 维度 | 指标 |
| --- | --- |
| 安全 | 逃逸测试通过率、越权读取/写入/联网阻止率 |
| 正确 | 命令退出码和文件变更捕获准确率 |
| 可复现 | 相同 snapshot 重复运行结果一致率 |
| 性能 | 环境启动时间、命令额外开销、snapshot 时间 |
| 清理 | 残留进程、文件、网络资源和远端实例数 |
| 可用性 | 合法命令被误阻止比例、审批次数 |

安全和可用性需要一起测。一个拒绝所有命令的系统很安全，但不是 Code Agent；一个完全开放的系统完成率高，却不能用于不可信输入。

## 十三、常见误区

### 误区 1：`shell=False` 就安全

它避免 shell 解释某些元字符，但被调用的程序仍可执行任意系统调用。

### 误区 2：命令首词 allowlist 足够

解释器、测试框架、构建工具和 Git 都是能力放大器。风险取决于完整调用与环境。

### 误区 3：容器里可以放长期凭据

容器内的仓库代码和依赖同样可能读取环境与文件。秘密应最小化、短期化、阶段化。

### 误区 4：没有网络就没有数据外泄

结果日志、共享目录、Git patch、artifact 和后续人工复制都可能成为通道。仍需输出脱敏和最小文件可见性。

### 误区 5：超时后进程自然会消失

必须终止整个进程树，并确认环境中没有残留后台任务。

## 十四、从当前 Harness 演进的最小路径

### v0.2：先改执行协议

- `command` 改为 argv；
- 最小环境变量；
- 进程组取消；
- stdout/stderr 分离并落 artifact；
- 记录退出码、signal、耗时和文件变更。

### v0.3：加入本地 OS Sandbox

- 工作区可写，其他目录默认不可写；
- 敏感目录不可读；
- 默认断网；
- 限制 CPU、内存、进程和输出；
- Sandbox 不可用时 fail closed，而不是静默裸跑。

### v0.4：容器化任务

- 固定镜像 digest；
- setup 与 agent 阶段分离；
- 每任务独立环境；
- snapshot/restore；
- 任务结束强制清理。

## 十五、检查题

1. 为什么 `pytest` 在 allowlist 中仍然需要 Sandbox？
2. Permissions 和 Sandbox 分别解决什么问题？
3. 只限制文件写入、不限制网络会留下什么攻击路径？
4. 为什么 setup 阶段和 agent 阶段应使用不同的网络与凭据策略？
5. Git worktree 能隔离哪些状态，不能隔离哪些状态？

## 参考资料

- [Claude Code: Sandboxing](https://code.claude.com/docs/en/sandboxing)
- [Claude Code: Configure permissions](https://code.claude.com/docs/en/permissions)
- [Codex: Agent approvals and security](https://learn.chatgpt.com/docs/agent-approvals-security.md)
- [SWE-ReX: Sandboxed code execution for AI agents](https://github.com/SWE-agent/swe-rex)
- [SWE-bench evaluation harness](https://github.com/SWE-bench/SWE-bench)
- [OpenHands: An Open Platform for AI Software Developers as Generalist Agents](https://arxiv.org/abs/2407.16741)
