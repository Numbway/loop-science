# 开发进度记录

> 科研分身框架开发进度，按模块追踪完成状态。
> 每个阶段完成后更新此文件，方便断点继续开发。

---

## 总体进度

| Phase | 描述 | 状态 |
|-------|------|------|
| Phase 1 | 基础设施 | ✅ 已完成 |
| Phase 2 | 论文管理 | ✅ 已完成 |
| Phase 3 | AI 服务 | ✅ 已完成 |
| Phase 4 | 实验执行 | ✅ 已完成 |
| Phase 5 | 前端 | 🔄 进行中 |
| Phase 6 | 完善 | ⏳ 待开始 |

---

## Phase 1: 基础设施 ✅

**完成时间**：2026-07-27

### M1: 项目脚手架 ✅

**文件清单**：
- `docker-compose.yml` — PostgreSQL 16 + Redis 7 + Backend + Frontend
- `backend/` — FastAPI 项目结构
  - `backend/app/main.py` — FastAPI 入口，含 `/health` 端点
  - `backend/app/core/config.py` — pydantic-settings 配置管理
  - `backend/app/core/database.py` — 异步数据库连接（asyncpg）
  - `backend/requirements.txt` — Python 依赖
  - `backend/Dockerfile` — Python 3.11 镜像
- `frontend/` — Vite + React 18 + TypeScript
  - `frontend/src/main.tsx` — 入口，含 Ant Design + React Query
  - `frontend/src/App.tsx` — 基础路由 + 欢迎页
  - `frontend/Dockerfile` — Node 20 镜像
  - `frontend/package.json` — 含所有前端依赖
- `.env.example` / `.env` — 环境变量
- `.gitignore`
- `README.md`

**验证结果**：
- ✅ 后端 `app/main.py` 加载成功
- ✅ `GET /health` 返回 `{"status": "ok", "version": "0.1.0"}`
- ✅ 前端 Vite build 成功（3.88s）
- ⚠️ Docker Compose 待有网络环境时验证

### M2: 数据模型 ✅

**文件清单**：
- `backend/app/models/base.py` — UUIDMixin + TimestampMixin
- `backend/app/models/user.py` — User 模型
- `backend/app/models/project.py` — Project 模型
- `backend/app/models/experiment.py` — Experiment 模型
- `backend/app/models/reference_paper.py` — ReferencePaper 模型
- `backend/app/models/experiment_log.py` — ExperimentLog 模型
- `backend/app/models/__init__.py` — 统一导出
- `backend/alembic/` — 数据库迁移配置
  - `alembic.ini` — 数据库连接配置
  - `alembic/env.py` — 导入所有模型以支持 autogenerate
- `backend/app/services/crud/base.py` — 泛型 BaseCRUD

**验证结果**：
- ✅ 所有 5 个模型加载成功
- ✅ Alembic 初始化完成
- ⚠️ 数据库迁移待 PostgreSQL 可用时执行

### M3: 用户认证 ✅

**文件清单**：
- `backend/app/core/security.py` — JWT + bcrypt 密码哈希
- `backend/app/schemas/user.py` — Pydantic 请求/响应模型
- `backend/app/api/auth.py` — 注册/登录/me 接口
- `backend/app/api/deps.py` — get_current_user 依赖
- `frontend/src/types/index.ts` — TypeScript 类型定义
- `frontend/src/services/api.ts` — Axios 封装（含 token 拦截器）
- `frontend/src/store/auth.ts` — Zustand 认证状态管理
- `frontend/src/pages/Login.tsx` — 登录/注册页面

**验证结果**：
- ✅ 密码哈希 + 验证正常
- ✅ JWT 生成 + 解码正常
- ✅ Pydantic schema 校验正常
- ✅ API 路由注册成功：`/api/auth/register`, `/api/auth/login`, `/api/auth/me`
- ✅ TypeScript 类型检查通过
- ✅ Vite 生产构建成功

---

## 环境说明

| 工具 | 路径 | 备注 |
|------|------|------|
| Python (系统) | `C:\Users\WeiJun\AppData\Local\Programs\Python\Python310\python.exe` | Python 3.10.1 |
| Python (Anaconda) | `E:\anaconda3\python` | Python 3.13，用于本地开发 |
| Node.js | `C:\Program Files\nodejs\node.exe` | v24.14.0 |
| npm registry | `https://registry.npmmirror.com` | 开发时使用镜像 |
| pip index | `https://pypi.tuna.tsinghua.edu.cn/simple` | 全局配置 |

**注意**：本地开发使用 Anaconda Python (`/e/anaconda3/python`)，Docker 中使用 Python 3.11。

---

## Phase 2: 论文管理 ✅

**完成时间**：2026-07-28

### M4: PDF 解析服务 ✅

**文件**：`backend/app/services/paper/parser.py`、`backend/app/schemas/paper.py`

**能力**：
- PyMuPDF 提取全文、标题、作者、摘要、章节、引用
- 可选 Claude AI 增强（关键词 + 核心贡献）
- AI 不可用时降级为本地 TF-IDF 规则

**验证**：PDFParser 初始化成功，数据结构完整

### M5: 论文检索/下载 ✅

**文件**：`backend/app/services/paper/downloader.py`

**能力**：
- `ArxivClient`：arXiv API 搜索 + PDF 下载（3 次重试）
- `SemanticScholarClient`：Semantic Scholar API 搜索（仅元数据）
- `FakeSearchClient`：可注入测试替身，离线可用
- 协议 `PaperSearchClient` 抽象所有人

**验证**：FakeSearchClient 搜索/下载/失败处理全部通过

### M6: 论文库 ✅

**后端文件**：`backend/app/services/paper/library.py`、`backend/app/api/papers.py`

**API 路由**（7 个）：
- `GET /api/projects/{id}/papers` — 论文列表（支持关键词/来源筛选）
- `POST /api/projects/{id}/papers/search` — 外部搜索
- `POST /api/projects/{id}/papers` — 添加论文
- `GET /api/papers/{id}` — 论文详情
- `DELETE /api/papers/{id}` — 删除论文
- `POST /api/papers/{id}/upload` — 手动上传 PDF
- `GET /api/projects/{id}/papers/keywords` — 关键词分组

**前端文件**：`frontend/src/pages/ReferencePapers.tsx`

**功能**：
- 论文库列表（标题、作者、关键词标签、下载状态）
- 搜索 arXiv 并添加到库
- 手动上传失败的论文 PDF
- 删除论文

**验证**：TypeScript 类型检查通过，Vite 构建成功

---

## Phase 4: 实验执行 🔄

**完成时间**：2026-07-29

### M10: GitService ✅

**文件清单**：
- `backend/app/api/git.py` — Git 相关 REST API
- `backend/app/services/git/service.py` — GitService 核心实现
- `backend/app/schemas/git.py` — 仓库、分支、提交请求/响应模型
- `backend/tests/api/test_git.py` — API 集成测试
- `backend/tests/services/git/` — GitService 单元测试

**能力**：
- 初始化项目仓库并隔离在项目目录内
- 创建基于实验节点的分支
- 提交真实文件变更并返回 commit SHA
- 查询仓库状态并区分 clean / dirty 工作区
- 通过 REST API 暴露仓库初始化、分支、提交、状态查询

**验证结果**：
- ✅ `python -m pytest -v` 通过（15 项）
- ✅ M10 相关文件的 `ruff check` 通过
- ✅ API 测试验证仓库初始化、分支创建、提交和状态查询；当前 FastAPI 版本以嵌套 router 形式注册 5 条 repository 路由
- ⚠️ `ruff check .` 仍报告 51 项既有问题，位于 Alembic、认证、论文、模型和 AI 服务等 M10 范围外文件

---

### M11: Docker Executor ✅

**完成时间**：2026-08-01

**文件清单**：
- `executor/Dockerfile`、`executor/runner.py` — PyTorch 容器镜像与实验入口
- `backend/app/services/experiment/executor.py` — 隔离容器生命周期管理
- `backend/tests/services/experiment/test_executor.py` — 执行器单元测试

**能力**：
- 代码只读挂载、独立输出目录、禁用容器网络
- 启动、日志流、状态查询、停止和清理容器
- 通过 `EXECUTOR_IMAGE` 与 `EXECUTOR_SANDBOX_MODE` 配置镜像和沙箱模式

**验证结果**：
- ✅ 执行器单元测试 3 项通过，M11 范围 Ruff 通过
- ✅ 构建 `loop-science-executor:latest` 并在无网络、只读容器中运行 PyTorch，输出 `torch-result=3.0`

---

### M12: Celery 任务 ✅

**完成时间**：2026-08-01

**文件清单**：
- `backend/app/core/celery_app.py` — Celery/Redis 应用配置
- `backend/app/tasks/experiment_tasks.py` — 单实验执行与项目迭代任务
- `backend/tests/tasks/test_experiment_tasks.py` — 停止条件与 eager-mode 任务测试

**能力**：
- `experiments.run` 从数据库加载实验，切换 Git 分支并启动隔离容器
- `experiments.iterate` 根据项目状态、迭代上限和目标指标选择并排队实验
- 执行失败时写回实验 `failed` 状态和完成时间
- Alembic 统一使用应用的同步数据库连接配置

**验证结果**：
- ✅ Redis broker 连接成功，两条 Celery 任务注册成功
- ✅ 全部后端测试 22 项通过，M12 范围 Ruff 通过
- ✅ Alembic 可连接隔离 PostgreSQL 验证实例

---

### M13: 实验监控 ✅

**完成时间**：2026-08-01

**文件清单**：
- `backend/app/services/experiment/monitor.py` — 实时日志、TensorBoard 指标和最终状态采集
- `backend/app/tasks/experiment_tasks.py` — `experiments.monitor` 任务与执行任务衔接
- `executor/runner.py` — 从可写实验输出目录运行训练代码
- `backend/tests/services/experiment/test_monitor.py` — 日志解析、指标采集和状态持久化测试

**能力**：
- 容器运行期间逐行采集并持久化标准输出，按 info/warning/error 分类
- 从 TensorBoard event 文件读取每个 scalar 的最新值和 step
- 解析 epoch、最新/最佳指标，检测 NaN、Inf、Traceback、OOM 等异常
- 根据容器退出码写回 completed/failed、metrics、完成时间和运行时长
- `experiments.run` 启动容器后自动排队 `experiments.monitor`

**验证结果**：
- ✅ 全部后端测试 27 项通过，M13 范围 Ruff 与格式检查通过
- ✅ Redis broker 连接成功，`experiments.run`、`experiments.monitor`、`experiments.iterate` 自动注册
- ✅ 真实无网络 Docker 容器完成三轮 PyTorch 训练，日志被流式读取，输出产物可写
- ✅ 从真实 TensorBoard event 文件采集 `train/loss` 和 `validation/accuracy` 最新指标

---

### M14: 项目创建向导 ✅

**完成时间**：2026-08-01

**文件清单**：
- `backend/app/api/project_wizard.py` — PDF、问答、代码生成/审核和实验启动编排 API
- `backend/app/schemas/project_wizard.py` — 向导请求与响应模型
- `backend/tests/api/test_project_wizard.py` — 完整创建流程和路径隔离测试
- `frontend/src/pages/ProjectWizard.tsx` — 六步项目创建向导
- `frontend/src/pages/ProjectWizard.css` — 实验协议台视觉、响应式与无障碍样式
- `frontend/src/services/projectWizard.ts` — 类型化向导 API 客户端

**能力**：
- 上传并解析 25 MB 内的论文 PDF，建立归属当前用户的草稿项目
- 通过最多六轮、一次一问的引导对话收集目标指标和实验边界
- 调用 CodeAgent 生成七文件 PyTorch 框架，逐文件查看、编辑并创建审核提交
- 限制 AI 工具和审核文件只能访问项目工作区，禁止路径穿越和 `.git` 修改
- 创建 `exp/1` 初始实验分支并将首个实验排入 Celery 队列
- 桌面与移动端响应式界面、键盘焦点、减少动画支持和路由级代码分割

**验证结果**：
- ✅ 全部后端测试 30 项通过，M14 相关 Ruff 与格式检查通过
- ✅ 前端 TypeScript 生产构建与 ESLint 通过
- ✅ 桌面 1440px 与移动 500px 无头浏览器截图完成视觉验收
- ✅ 隔离 PostgreSQL 真实 HTTP 流程通过：注册、上传、六轮问答、生成 7 文件、保存、启动并入队

---

### M15: 实验树可视化 ✅

**完成时间**：2026-08-01

**文件清单**：
- `backend/app/api/experiment_tree.py` — 项目归属校验后的只读实验树 API
- `backend/app/schemas/experiment_tree.py` — 项目谱系和节点响应模型
- `backend/tests/api/test_experiment_tree.py` — 自然排序、状态、指标和私有报告路径测试
- `frontend/src/pages/ExperimentTree.tsx` — React Flow 竖向实验树与节点详情面板
- `frontend/src/pages/ExperimentTree.css` — 实验谱系图册视觉与桌面/窄屏布局
- `frontend/src/components/experiment-tree/ExperimentNode.tsx` — 状态化实验节点卡片
- `frontend/src/services/experimentTree.ts` — 类型化实验树 API 客户端

**能力**：
- 按父子节点关系计算稳定的竖向分叉布局，并兼容孤立节点和异常环路数据
- 节点卡片展示状态、accuracy/loss、改进描述、耗时及报告/分支入口
- 点击节点查看分支、完整指标、实验配置、AI 诊断和创建来源
- 支持缩放、平移、缩略图、自动适配视口和运行中连线动画
- 每 5 秒轮询项目实验树，在 M19 WebSocket 接入前提供近实时状态更新
- 桌面双栏和窄屏单栏响应式布局，支持键盘焦点和减少动画偏好

**验证结果**：
- ✅ 全部后端测试 31 项通过，M15 相关 Ruff 与格式检查通过
- ✅ 前端 TypeScript 生产构建与 ESLint 通过
- ✅ 桌面 1440px 与窄屏 500px 无头浏览器截图完成视觉验收
- ✅ 修复窄屏单列模式下 React Flow 高度链断裂导致节点不可见的问题

---

### M16: 分支创建对话框 ✅

**完成时间**：2026-08-01

**文件清单**：
- `backend/app/api/experiment_tree.py` — 从任意父实验创建子节点和真实 Git 分支
- `backend/app/schemas/experiment_tree.py` — 三项分支计划及创建结果模型
- `backend/app/services/git/service.py` — 不切换工作区地读取任意父分支 HEAD
- `frontend/src/components/experiment-tree/BranchDialog.tsx` — 三问分支规划对话框
- `frontend/src/components/experiment-tree/BranchDialog.css` — 分支提案单视觉与响应式布局
- `frontend/src/services/experimentTree.ts` — 类型化分支创建 API

**能力**：
- 从实验树任意节点打开三问向导，依次收集改进对象、具体方案和验证预算
- 根据父节点深度分配全局唯一的下一实验节点编号
- 从父实验记录的 Git 分支 HEAD 创建并检出真实 `exp/{node_id}` 分支
- 继承父实验配置并保存结构化 `branch_plan`，新增节点初始状态为 `pending`
- 创建成功后立即刷新实验树、选中新节点，并展示明确的分支创建结果
- Git 冲突、脏工作区和缺失父分支以可操作错误反馈呈现，不覆盖现场

**验证结果**：
- ✅ 全部后端测试 34 项通过，M16 相关 Ruff 与格式检查通过
- ✅ 真实临时 Git 仓库验证：任意父分支 HEAD 读取、子分支创建和工作区切换正确
- ✅ 前端 Prettier、ESLint、TypeScript 生产构建通过
- ✅ 桌面 1440px 与窄屏 500px 无头浏览器截图完成视觉验收
- ✅ 修复选项卡自动网格排布导致说明文字挤压为竖排的问题

---

### M17: 实验详情页 ✅

**完成时间**：2026-08-01

**文件清单**：
- `backend/app/api/experiment_detail.py` — 用户归属校验后的实验详情聚合 API
- `backend/app/schemas/experiment_detail.py` — 指标、训练日志、参考依据、监控与代码差异响应模型
- `backend/app/services/git/service.py` — 父子实验分支只读比较与统计
- `backend/tests/api/test_experiment_detail.py` — 实验档案、路径隔离与 TensorBoard 配置测试
- `frontend/src/pages/ExperimentDetail.tsx` — 实验检验档案详情页
- `frontend/src/pages/ExperimentDetail.css` — 证据标尺、双栏布局与窄屏重排
- `frontend/src/services/experimentDetail.ts` — 类型化实验详情 API 客户端

**能力**：
- 从实验树节点直接进入 `/experiments/{id}`，并返回所属项目实验树
- 聚合头部总结、父子指标对照、目标指标、运行档案、训练日志和参考论文
- 检测 TensorBoard event 文件；配置 `TENSORBOARD_PUBLIC_URL` 后安全嵌入实验监控界面
- 使用真实 Git 分支生成统一格式 Diff、文件列表和增删统计，全程不切换工作区
- 展示 AI 诊断、参考依据、实验配置，并仅报告 M18 HTML 报告是否已存在
- 后端响应不暴露存储根目录、event 文件和私有报告的主机路径

**验证结果**：
- ✅ 全部后端测试 36 项通过，M17 相关 Ruff 与格式检查通过
- ✅ 真实临时 Git 仓库验证父子分支 Diff、文件统计及工作区不切换
- ✅ 前端 Prettier、ESLint、TypeScript 生产构建通过
- ✅ 桌面 1440px 与窄屏 500px 无头浏览器截图完成视觉验收
- ✅ TensorBoard iframe、指标正负语义、训练日志与逐行代码 Diff 均完成模拟数据验收

---

### M18: HTML 报告生成 ✅

**完成时间**：2026-08-01

**文件清单**：
- `backend/app/services/report/html_generator.py` — 独立报告数据整理、TensorBoard 曲线固化与原子写入
- `backend/app/services/report/templates/experiment_report.html.j2` — 单文件报告骨架、内联样式和打印布局
- `backend/app/services/report/templates/sections/` — 七个实验报告 section
- `backend/app/api/experiment_report.py` — 报告生成、归属校验后的查看与下载 API
- `backend/app/schemas/experiment_report.py` — 报告生成结果模型
- `backend/tests/services/report/test_html_generator.py` — 模板完整性、转义、曲线与独立性测试
- `backend/tests/api/test_experiment_report.py` — 生成、持久化、查看、下载和路径隔离测试
- `frontend/src/pages/ExperimentDetail.tsx` — 报告生成、打开、下载与重新生成控制区
- `frontend/src/services/experimentDetail.ts` — 授权 Blob 报告客户端

**能力**：
- 通过 Jinja2 生成快速总结、详细分析、性能对比、训练曲线、代码变更、参考文献和后续建议七类证据
- 从 TensorBoard event 文件读取完整 scalar 历史并固化为内联 SVG，不依赖运行中的 TensorBoard 服务
- 使用真实父子 Git 分支 Diff，并限制报告中的差异体积
- 将样式、曲线和内容写入单个 HTML，支持离线打开、下载和 A4 打印
- 原子替换同一实验报告，数据库仅记录私有规范路径
- 查看与下载接口复用实验归属校验，拒绝旧路径、越界路径和缺失文件
- 模板自动转义诊断、配置和代码内容，仅保留 HTTP/HTTPS 参考链接

**验证结果**：
- ✅ 全部后端测试 39 项通过，M18 相关 Ruff 与格式检查通过
- ✅ 前端 Prettier、ESLint、TypeScript 生产构建通过
- ✅ 独立报告桌面 1440px、窄屏 500px 和完整七 section 长页面完成无头浏览器视觉验收
- ✅ M17 详情页报告控制区完成视觉验收
- ✅ 报告中无外部样式、脚本或 iframe 运行时依赖

---

### M19: WebSocket 实时通信 ✅

**完成时间**：2026-08-01

**文件清单**：
- `backend/app/api/websocket.py` — 项目级 WebSocket、JWT 子协议认证、Origin 与归属校验
- `backend/app/services/realtime/broker.py` — Redis Pub/Sub 跨进程事件代理、心跳和订阅生命周期
- `backend/app/schemas/realtime.py` — 类型化项目实时事件
- `backend/app/tasks/experiment_tasks.py` — 启动、训练进度、完成和失败事件发布
- `backend/app/api/experiment_tree.py` — 新实验分支创建事件发布
- `backend/tests/api/test_websocket.py` — 连接认证、项目隔离和事件流测试
- `backend/tests/services/realtime/test_broker.py` — 事件校验、隔离、心跳与故障降级测试
- `frontend/src/services/realtime.ts` — WebSocket 客户端、指数退避重连和网络状态处理
- `frontend/src/hooks/useProjectRealtime.ts` — 可复用项目实时订阅 Hook
- `frontend/src/pages/ExperimentTree.tsx` — 实验树事件合并与离线轮询降级
- `frontend/src/pages/ExperimentDetail.tsx` — 实验详情状态、指标与诊断即时合并

**能力**：
- FastAPI 与 Celery 通过 Redis Pub/Sub 共享项目事件，不依赖单进程内存状态
- 浏览器使用 `Sec-WebSocket-Protocol` 传递 JWT，避免令牌出现在 URL 和访问日志
- WebSocket 建连前校验 Origin、用户身份和项目归属，使用稳定关闭码区分认证与资源错误
- 推送实验启动、逐 epoch 指标、完成、失败、诊断和新分支事件
- 先完成 Redis 订阅再发送 `connected`，消除建连成功后首个事件丢失竞态
- 前端即时合并增量事件；终态触发完整查询刷新，断线时以 15 秒低频轮询兜底
- 断线采用 1、2、4、8、15 秒指数退避，并响应浏览器 online/offline 状态

**验证结果**：
- ✅ 全部后端测试 44 项通过，M19 范围 Ruff 检查通过
- ✅ 前端 M19 Prettier、全量 ESLint 与 TypeScript 生产构建通过
- ✅ Docker Redis 真实 Pub/Sub 验证通过，订阅者收到相同事件 ID 和训练指标
- ✅ FastAPI WebSocket + 真实 Redis 完整链路通过：协商 `bearer` 子协议并收到完成事件
- ⚠️ 全仓库 Ruff 仍有 43 个早期阶段遗留告警；未混入 M19 提交范围

---

## 下一步：M20 错误处理

待开发模块：
- M20: 常见实验错误自动恢复、用户友好提示和恢复过程日志

---

## 断点续开指南

如果从这里继续开发：

```bash
# 1. 进入项目目录
cd G:\Code\loop_science

# 2. 激活后端环境
# 使用 Anaconda Python 或 Docker
/e/anaconda3/python -m pip install -r backend/requirements.txt

# 3. 启动数据库（需要 Docker）
docker-compose up -d postgres redis
docker-compose exec backend alembic upgrade head

# 4. 启动后端
cd backend && /e/anaconda3/python -m uvicorn app.main:app --reload

# 5. 启动前端（另一个终端）
cd frontend && npm run dev

# 6. 验证
curl http://localhost:8000/health
curl http://localhost:3000
```
