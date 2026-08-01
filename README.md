# 科研分身 (Research Companion)

> 不仅是工具，而是研究生的科研分身

一个帮助硕士研究生复现顶刊/顶会论文并进行改进的 AI 辅助研究平台。

## 核心功能

- 🤖 **自动复现**：从论文自动生成可运行代码
- 🧠 **智能诊断**：基于参考论文分析实验结果
- ⚙️ **异步自主**：学生离开后 AI 继续迭代
- 🌳 **实验可观测**：完整决策树，可回溯任何分支
- 📊 **详细报告**：每次实验生成 HTML 分析报告

## 快速开始

### 前置要求

- Docker & Docker Compose
- Python 3.11+
- Node.js 18+

### 安装与运行

```bash
# 1. 克隆仓库
git clone <repo-url>
cd research-companion

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 ANTHROPIC_API_KEY

# 3. 启动服务
docker-compose up -d

# 4. 数据库迁移
docker-compose exec backend alembic upgrade head

# 5. 访问
# 前端: http://localhost:3000
# 后端 API 文档: http://localhost:8000/docs
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 18 + TypeScript + Vite + Ant Design |
| 后端 | FastAPI + SQLAlchemy + Celery |
| 数据库 | PostgreSQL 16 |
| 缓存 | Redis 7 |
| AI | Claude Agent SDK + Anthropic SDK |
| 容器 | Docker + Docker Compose |

## 开发计划

- [ ] Phase 1: 基础设施（M1-M3）
- [ ] Phase 2: 论文管理（M4-M6）
- [ ] Phase 3: AI 服务（M7-M9）
- [ ] Phase 4: 实验执行（M10-M13）
- [x] Phase 5: 前端（M14-M17）
- [ ] Phase 6: 完善（M18-M21）

## 项目结构

```
research-companion/
├── backend/          # FastAPI 后端
├── frontend/         # React 前端
├── executor/         # Docker 实验镜像
├── docs/             # 设计文档
├── docker-compose.yml
└── README.md
```

## 文档

- [项目设计文档](docs/PROJECT_DESIGN.md)
- [AI 开发指导](docs/archive/AI_DEVELOPMENT_GUIDE.md)
- [Claude Agent 集成方案](docs/archive/CLAUDE_AGENT_INTEGRATION.md)
