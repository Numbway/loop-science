# 科研分身 (Research Companion)

> 不仅是工具，而是研究生的科研分身

一个帮助硕士研究生复现顶刊/顶会论文并进行改进的 AI 辅助研究平台。

## 核心功能

- 🤖 **自动复现**：从论文自动生成可运行代码
- 🧠 **智能诊断**：基于参考论文分析实验结果
- ⚙️ **异步自主**：学生离开后 AI 继续迭代
- 🌳 **实验可观测**：完整决策树，可回溯任何分支
- 📊 **详细报告**：每次实验生成 HTML 分析报告
- 🔐 **远端训练**：SSH 密码或私钥认证，验证主机指纹后执行
- 🧾 **启动闸门**：论文分析、真实数据、实验机器和审核代码全部就绪才允许启动

## 快速开始

### 前置要求

- Docker & Docker Compose
- 一台可通过 SSH 访问且安装了 `python3`/`venv` 的 Linux 训练服务器
- 训练服务器可访问项目依赖源；GPU 实验还需准备匹配的驱动与 CUDA/PyTorch

### 安装与运行

```bash
# 1. 克隆仓库
git clone <repo-url>
cd research-companion

# 2. 配置环境变量
cp .env.example .env
# 至少修改 JWT_SECRET 和 CREDENTIAL_ENCRYPTION_KEY

# 3. 启动服务
docker compose up -d --build

# 4. 数据库迁移
docker compose exec backend python -m alembic upgrade head

# 5. 访问
# 前端: http://localhost:3000
# 后端 API 文档: http://localhost:8000/docs
```

先从顶部导航进入“系统配置”：

1. 录入一个或多个模型配置：选择 Anthropic Messages 或
   OpenAI-compatible 协议，并填写 Base URL、模型 ID 和 API Key。
2. 使用 SSH 账号密码或私钥录入并验证训练服务器。

登录后的首页是统一“实验管理”台账，集中展示当前用户的全部项目、最新实验状态、
指标、服务器和实验节点数量。运行中的项目可以重新进入实验谱系，未启动项目可以
从保存的论文向导或已有资产快捷流程继续准备。

创建项目时，在页面中按顺序完成：

项目入口提供两套 SOP：

- **从论文开始**：上传论文 PDF，选择大模型配置，完成论文分析与研究问答，
  再选择 SSH 服务器和远端数据。框架生成允许执行完整的多轮模型调用，
  不再由前端在 180 秒时中断。
- **已有代码与数据**：跳过论文分析、研究问答和框架生成；选择已验证的
  SSH 服务器后，从服务器选择数据文件或文件夹，再选择现有训练代码目录、
  入口脚本和启动参数。代码会过滤密钥、`.env`、Git 元数据与虚拟环境后导入
  为本地 Git 基线。

启动时，Worker 只会把代码上传到远端
   `~/.loop-science/runs/<experiment-id>`，训练会直接读取所选服务器路径中的数据，
   准备隔离虚拟环境并回传日志。

API Key、SSH 密码、私钥及口令以用户级配置档案加密保存。模型公司的
Base URL、协议与模型 ID 保存在档案的公开连接信息中。项目通过配置档案
ID 建立关联，不会复制凭据，凭据也不会出现在接口响应、Git 仓库或实验日志中。
已有项目可在实验谱系页面进入“连接配置”重新选择模型或训练服务器。
更换 `CREDENTIAL_ENCRYPTION_KEY` 后，已有凭据需要重新输入。

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
