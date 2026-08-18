# 源码解读版本升级协议

固定 commit 解决“今天可复现”，但不能让文章永久正确。升级应当像依赖迁移，而不是搜索替换 SHA。

## 1. 何时升级

满足任一条件再升级：

- 上游发布重要稳定版本；
- 入口或关键类型已经移动，读者无法跟随；
- 某项结论被新架构推翻；
- 实验无法在支持环境运行；
- 安全机制发生实质变化。

不要为了追最新 commit 每周改文档。高频漂移会破坏读者复现，也让 diff 失去解释力。

## 2. 升级审计清单

```text
[ ] 记录 old/new SHA 与发布日期
[ ] 阅读 release notes 与 migration guide
[ ] 比较源码地图路径
[ ] 重新追踪一次完整请求
[ ] 对比核心事件/Entry/Protocol schema
[ ] 重跑 Labs 与上游目标测试
[ ] 检查许可证和项目归属
[ ] 更新横向矩阵
[ ] 新增 MIGRATION.md，说明结论变化
```

## 3. 使用行为 Diff，而不只是文件 Diff

对每个项目保存一组 Golden Artifact：

- Event Timeline；
- Session/Trajectory fixture；
- Tool Call/Result；
- Compaction 前后 model view；
- Cancel/timeout/error 结果；
- Effective plugin/tool configuration。

升级后比较 Artifact，可以发现“文件重构但行为没变”和“接口没改但语义变了”的差别。

## 4. 文章中的结论标级

- **Fact**：固定源码直接可见，例如字段、调用或事件；
- **Inference**：根据多处源码推断设计理由；
- **Experiment**：由指定实验验证；
- **Out of scope**：未覆盖，不做结论。

对争议结论明确标记推断，避免把作者解释伪装成上游官方意图。

## 5. 链接策略

- 关键证据使用 commit permalink；
- 项目首页可链接 `main`用于发现最新版本；
- 不依赖行号作为唯一定位，函数移动后行号会失效；
- 每章顶部给出 fixed SHA；
- 大段代码用伪代码转述，只引用必要接口并遵守许可证。

## 6. 保留旧版本

重大架构变化时，不要直接覆盖有研究价值的旧分析。可以使用：

```text
project/
├── README.md              # 当前阅读入口
├── versions/
│   ├── 2026-08-sha/
│   └── 2027-02-release/
└── MIGRATION.md
```

旧源码解读本身就是架构演进史。尤其是 SWE-agent classic → mini、单一 Session → 事件溯源、内置工具 → 动态发现，这些变化能解释行业为什么修改 Harness。

## 7. 完成标准

升级只有在源码链接可达、文档内部链接通过、Golden Labs 有结果、关键差异写入 Migration、横向矩阵同步后才算完成。仅把版本号改成最新会制造比“旧但准确”更危险的文档。
