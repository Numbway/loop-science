# Phase 4 M10 GitService - 设计文档

**日期**：2026-07-28  
**状态**：已确认，待实施  
**依赖**：Phase 1–3（项目、实验模型、认证与 AI 服务已完成）

---

## 1. 目标与范围

M10 为每个科研项目提供独立、可追溯的本地 Git 仓库，使后续的 CodeAgent、Docker Executor、Celery 任务与实验树能够在稳定的版本边界上工作。

本模块实现：

- 项目仓库初始化；
- 从指定父提交创建并检出实验分支；
- 检出已有分支；
- 提交真实代码变更；
- 查询仓库、分支和工作区状态；
- 通过受认证的 REST API 暴露最小闭环。

本模块不实现：

- Docker 训练、日志采集或 TensorBoard 监控（M11、M13）；
- Celery 异步调度、自动迭代或停止条件（M12）；
- Git worktree 池、跨进程锁、远程仓库同步或并行实验；
- 删除分支、强制切换、reset、clean、rebase 等破坏性操作。

---

## 2. 架构与职责

采用 **独立 `GitService` + 领域异常 + 薄 API 路由**。

```text
HTTP API
  ├─ 鉴权、项目归属校验、请求/响应校验
  └─ GitService
       ├─ 仓库路径与分支名校验
       ├─ GitPython 操作
       ├─ 工作区安全检查
       └─ 领域异常
```

新增结构：

```text
backend/app/
├── api/
│   └── git.py                 # 认证、项目归属和 HTTP 映射
├── schemas/
│   └── git.py                 # 请求与响应 Pydantic 模型
├── services/
│   └── git/
│       ├── __init__.py        # 公开服务与异常
│       ├── exceptions.py      # 受控领域错误
│       └── service.py         # GitPython 封装
└── tests/
    ├── services/git/
    └── api/
```

API 不接触 GitPython 对象；服务不依赖 FastAPI 请求或响应类型。后续 CodeAgent、实验执行器和 Celery 任务可直接调用服务方法。

---

## 3. 仓库、分支与提交规则

### 3.1 仓库位置

项目仓库的唯一位置为：

```text
{STORAGE_PATH}/{project_id}/git_repo
```

服务从 `settings.storage_path` 生成路径，并在实际解析后校验其仍位于存储根目录内，防止路径逃逸。

### 3.2 初始化

`initialize_project_repository(project_id)`：

1. 创建项目目录及 `git_repo`；
2. 初始化 Git 仓库并确保默认分支是 `main`；
3. 写入最小 `.gitkeep`；
4. 以 `Initial project repository` 创建首个提交；
5. 返回仓库位置、当前分支及 HEAD SHA。

重复调用是幂等的：已存在且有效的仓库仅返回当前信息，不会重建或覆盖内容。

这使得 CodeAgent 在生成初始代码前已有稳定、可分支的基线；生成代码后由调用方使用普通提交接口在 `main` 上提交。

### 3.3 实验分支

实验分支的唯一合法格式为：

```text
exp/{node_id}
```

其中 `node_id` 使用正整数段及连字符，例如 `1`、`2-1`、`3-2`；不允许斜杠、空白或 Git 保留引用语法。

`create_experiment_branch(project_id, node_id, parent_commit_sha)`：

1. 确认仓库存在且工作区干净；
2. 验证 `parent_commit_sha` 可在该仓库解析；
3. 拒绝已有同名分支；
4. 从指定父提交创建 `exp/{node_id}` 并检出；
5. 返回分支名和指向父提交的 HEAD SHA。

Git 分支本身已经引用父提交，因此不创建冗余“快照提交”。CodeAgent 或用户实际修改代码后，才通过提交接口创建一次带有实验说明的提交。

### 3.4 安全的工作区策略

所有写操作（创建分支、检出分支、提交）都检查工作区。存在未提交变更时，除提交操作外一律失败并保留现场；服务绝不调用 reset、clean、强制 checkout 或删除文件。

提交操作暂存受 Git 管理范围内的真实变更，并拒绝空提交。调用方提供提交说明，服务负责创建提交并返回 SHA、摘要和时间。

### 3.5 服务接口

```python
initialize_project_repository(project_id) -> RepositoryInfo
create_experiment_branch(project_id, node_id, parent_commit_sha) -> BranchInfo
checkout_branch(project_id, branch_name) -> BranchInfo
commit_changes(project_id, message) -> CommitInfo
get_repository_status(project_id) -> RepositoryStatus
```

服务返回自有 DTO/Pydantic 数据，而不是 GitPython `Repo`、`Commit` 或 `Head` 对象。

---

## 4. REST API

所有端点要求登录。路由先以当前用户查询项目；未找到项目或项目不属于当前用户时，统一返回 `404`，避免泄漏项目存在性。

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/projects/{project_id}/repository` | 初始化仓库；重复调用返回现有仓库信息。 |
| `GET` | `/api/projects/{project_id}/repository/status` | 返回当前分支、HEAD、是否干净和已知分支。 |
| `POST` | `/api/projects/{project_id}/repository/branches` | 从父提交创建并检出 `exp/{node_id}`。 |
| `POST` | `/api/projects/{project_id}/repository/checkout` | 安全地切换到已有分支。 |
| `POST` | `/api/projects/{project_id}/repository/commits` | 暂存实际变更并创建提交。 |

建议请求体：

```python
class CreateExperimentBranchRequest(BaseModel):
    node_id: str
    parent_commit_sha: str

class CheckoutBranchRequest(BaseModel):
    branch_name: str

class CommitChangesRequest(BaseModel):
    message: str
```

响应包含与操作相符的结构化仓库、分支、提交或状态信息，不泄漏绝对宿主机路径。

---

## 5. 错误处理契约

`services/git/exceptions.py` 定义领域异常，包含稳定的错误码、面向用户的说明和处理提示。API 层将其转换为一致的 HTTP 响应。

| 场景 | 服务错误 | HTTP | 行为 |
|---|---|---:|---|
| 项目不存在或无归属权限 | API 项目查询失败 | 404 | 不泄漏资源存在性。 |
| 仓库不存在 | `RepositoryNotFoundError` | 409 | 提示先初始化仓库。 |
| 分支格式非法、分支已存在、父 SHA 无效、目标分支不存在 | 相应的 `GitOperationError` 子类 | 409 | 保留仓库现场，不做修复。 |
| 创建分支或切换前工作区不干净 | `DirtyWorkingTreeError` | 409 | 返回变更摘要与提交/人工处理提示。 |
| 提交无任何变更 | `NothingToCommitError` | 409 | 不创建空提交。 |
| 发现仓库路径逃逸 | `InvalidRepositoryPathError` | 422 | 拒绝操作并记录安全上下文。 |
| Git 底层不可预期错误 | `GitServiceError` | 500 | 记录服务端原因，不向客户端暴露底层命令或系统路径。 |

严格失败优先：失败时不覆盖、不丢弃、不自动清理任何文件或未提交改动。

---

## 6. 数据流

### 初始化项目仓库

```text
客户端 → POST repository
  → API：认证与项目归属验证
  → GitService：建立 main + .gitkeep + 首次提交
  ← RepositoryInfo
```

### 创建实验分支并提交改动

```text
调用方取得父实验提交 SHA
  → POST branches
  → API：认证与项目归属验证
  → GitService：检查工作区 → 从父 SHA 创建/检出 exp/{node_id}
  ← BranchInfo

CodeAgent 或用户修改工作目录
  → POST commits
  → GitService：暂存真实变更 → 创建提交
  ← CommitInfo
```

---

## 7. 测试策略与验收标准

使用 `pytest` 和 `tmp_path` 创建真实本地 Git 仓库，不依赖网络、Docker、数据库或 Anthropic API。

### 服务级测试

1. 初始化创建 `main`、`.gitkeep` 和可分支的首个提交；
2. 重复初始化保持仓库与提交不变；
3. 使用有效父 SHA 创建并检出正确 `exp/{node_id}`；
4. 写入文件后提交，验证 HEAD、提交信息、包含的文件与干净工作区；
5. 非法节点编号、重复分支、错误 SHA、空提交安全失败；
6. 工作区有未提交变更时拒绝创建分支和检出，并确认变更仍存在；
7. 非法存储路径不能逃逸到 `STORAGE_PATH` 之外。

### API 级测试

1. 未认证请求被认证依赖拒绝；
2. 当前用户可操作其自己的项目仓库；
3. 另一用户访问同一项目获得 `404`；
4. 各领域错误映射为约定的 `409`、`422` 或安全的 `500` 响应；
5. 响应不包含绝对宿主机路径或底层 Git 命令细节。

### 本模块完成条件

- GitService 可初始化项目仓库、创建/检出实验分支、提交真实变更并查询状态；
- 工作区不干净与所有冲突场景均严格失败且不丢失现场；
- REST API 完成认证、归属校验和错误映射；
- `pytest` 与 `ruff check .` 通过；
- 完成后更新 `docs/PROGRESS.md`，将 Phase 4/M10 标为完成，并移除过期的“下一步：Phase 3”说明。

---

## 8. 后续衔接

- **M11 Docker Executor** 将在检出的实验分支工作目录运行训练，并使用提交 SHA 记录运行版本。
- **M12 Celery** 将根据状态和停止条件串联分支、执行和提交操作。
- **M13 实验监控** 将把运行状态、日志及指标写入既有实验模型，而 GitService 保持专注于版本控制。
- 并行执行出现后，再针对工作树隔离、进程锁与清理策略做独立设计；本模块不提前实现这些复杂度。
