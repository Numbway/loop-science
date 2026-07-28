# 开发进度记录

> 科研分身框架开发进度，按模块追踪完成状态。
> 每个阶段完成后更新此文件，方便断点继续开发。

---

## 总体进度

| Phase | 描述 | 状态 |
|-------|------|------|
| Phase 1 | 基础设施 | ✅ 已完成 |
| Phase 2 | 论文管理 | ✅ 已完成 |
| Phase 3 | AI 服务 | ⏳ 待开始 |
| Phase 4 | 实验执行 | ⏳ 待开始 |
| Phase 5 | 前端 | ⏳ 待开始 |
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

## 下一步：Phase 3 AI 服务

待开发模块：
- M7: CodeAgent（Claude Agent SDK 集成）
- M8: Diagnostician（实验诊断）
- M9: BrainstormDialog（引导对话）

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