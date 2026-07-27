---
name: ai-development-guide
description: 科研分身框架的AI开发指导计划 —— 详细到可直接指导AI逐步开发
metadata:
  type: development-plan
  date: 2026-07-27
  version: 1.0
  target: AI开发助手
---

# 科研分身框架 - AI开发指导计划

> **本文档目标**：指导AI开发助手（如Claude Code）按顺序、按模块、按标准完成科研分身框架的开发。
> **使用方式**：AI按照本文档的顺序依次实现每个模块，每完成一个模块都要通过验收标准。

---

## 0. 开发前必读

### 0.1 项目结构规范

```
research-companion/
├── backend/                    # 后端服务
│   ├── app/
│   │   ├── api/               # FastAPI 路由
│   │   ├── core/              # 核心业务逻辑
│   │   ├── models/            # SQLAlchemy 数据模型
│   │   ├── services/          # 服务层
│   │   │   ├── ai/           # AI 相关服务
│   │   │   ├── paper/        # 论文管理
│   │   │   ├── experiment/   # 实验管理
│   │   │   ├── git/          # Git 版本管理
│   │   │   └── code/         # 代码生成/修改
│   │   ├── tasks/             # Celery 异步任务
│   │   ├── schemas/           # Pydantic 数据校验
│   │   └── main.py
│   ├── tests/
│   ├── requirements.txt
│   ├── Dockerfile
│   └── alembic/               # 数据库迁移
│
├── frontend/                  # 前端应用
│   ├── src/
│   │   ├── components/       # React 组件
│   │   ├── pages/            # 页面组件
│   │   ├── services/         # API 调用
│   │   ├── hooks/            # 自定义 hooks
│   │   ├── store/            # 状态管理
│   │   └── types/            # TypeScript 类型
│   ├── package.json
│   └── Dockerfile
│
├── executor/                  # 实验执行器（Docker容器）
│   ├── base_image/           # 基础镜像
│   └── runner.py             # 实验运行脚本
│
├── docker-compose.yml
├── docs/
└── README.md
```

### 0.2 编码规范

**Python (后端)**：
- Python 3.11+
- 使用 `type hints`
- 使用 `black` 格式化
- 使用 `ruff` 做 lint
- 每个函数必须有 docstring
- 使用 `pydantic` 做数据校验

**TypeScript (前端)**：
- TypeScript 5.0+
- 使用 `prettier` 格式化
- 使用 `eslint` 做 lint
- React 18+ 函数组件
- 使用 hooks 而非 class

**Git 规范**：
- 每个模块一个 feature branch
- Commit message 格式：`feat(module): description` / `fix(module): description`
- 每个模块完成后合并到 develop 分支

### 0.3 AI开发原则

**AI在开发过程中必须遵守**：
1. **不跳步骤** — 按顺序完成每个模块
2. **测试先行** — 每个功能实现前先写测试用例
3. **接口优先** — 先定义接口再写实现
4. **模块解耦** — 保持模块间低耦合
5. **文档同步** — 代码变动同步更新文档
6. **每步都可运行** — 每完成一个子任务，代码都应该能跑

---

## 1. 技术栈选择

### 1.1 后端

| 组件 | 选择 | 理由 |
|------|------|------|
| Web框架 | **FastAPI** | 异步支持好、自动生成OpenAPI文档、性能高 |
| 数据库 | **PostgreSQL** | 稳定、支持JSON字段、生态好 |
| ORM | **SQLAlchemy 2.0** | 成熟、类型友好 |
| 异步任务 | **Celery + Redis** | 处理耗时的实验运行任务 |
| WebSocket | **FastAPI WebSocket** | 实时推送实验进度 |
| AI调用 | **Anthropic SDK (Claude API)** | 代码生成、诊断、改进 |
| 容器化 | **Docker + docker-py** | 隔离实验环境 |
| Git操作 | **GitPython** | 分支管理 |
| PDF解析 | **PyMuPDF + pdfplumber** | 提取论文内容 |
| 论文检索 | **arxiv API + Semantic Scholar API** | 参考论文推荐 |

### 1.2 前端

| 组件 | 选择 | 理由 |
|------|------|------|
| 框架 | **React 18 + TypeScript** | 生态成熟、类型安全 |
| 构建工具 | **Vite** | 快速热更新 |
| UI库 | **Ant Design** | 组件丰富、易上手 |
| 树形组件 | **React Flow** | 专业的节点图组件 |
| 状态管理 | **Zustand** | 轻量、易用 |
| API调用 | **Axios + React Query** | 缓存、重试友好 |
| Markdown | **react-markdown** | 渲染AI输出 |
| 代码高亮 | **react-syntax-highlighter** | 展示代码变更 |
| 图表 | **Recharts** | 训练曲线可视化 |

### 1.3 基础设施

| 组件 | 选择 |
|------|------|
| 容器编排 | Docker Compose (开发) / Kubernetes (生产) |
| 反向代理 | Nginx |
| 监控 | Prometheus + Grafana |
| 日志 | ELK Stack |
| 对象存储 | MinIO (S3兼容，存储PDF、Checkpoint) |

---

## 2. 数据模型定义

### 2.1 数据库表设计

**AI必须先创建这些表，作为整个系统的基础**：

```python
# app/models/project.py
class Project(Base):
    """项目：一个论文复现任务"""
    __tablename__ = "projects"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(200))
    
    # 论文信息
    paper_title: Mapped[str] = mapped_column(String(500))
    paper_path: Mapped[str] = mapped_column(String(500))  # 本地路径
    paper_metadata: Mapped[dict] = mapped_column(JSON)
    
    # 改进配置
    improvement_targets: Mapped[list] = mapped_column(JSON)  # ["model", "data", ...]
    target_metrics: Mapped[dict] = mapped_column(JSON)  # {"accuracy": 0.92}
    max_iterations: Mapped[int] = mapped_column(Integer, default=5)
    
    # Git仓库路径
    repo_path: Mapped[str] = mapped_column(String(500))
    
    # 状态
    status: Mapped[str] = mapped_column(String(50))  # "created", "running", "paused", "completed"
    
    # 时间戳
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    
    # 关系
    experiments: Mapped[list["Experiment"]] = relationship(back_populates="project")
    reference_papers: Mapped[list["ReferencePaper"]] = relationship(back_populates="project")


# app/models/experiment.py
class Experiment(Base):
    """实验节点：每个树节点"""
    __tablename__ = "experiments"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"))
    
    # 树结构
    node_id: Mapped[str] = mapped_column(String(20))  # "1", "2-1", "3-2"
    parent_node_id: Mapped[str | None] = mapped_column(String(20))
    
    # Git分支
    git_branch: Mapped[str] = mapped_column(String(100))  # "exp/2-1"
    
    # 实验配置
    improvement_description: Mapped[str] = mapped_column(Text)  # 改进方案描述
    code_changes: Mapped[dict] = mapped_column(JSON)  # 代码变更记录
    config: Mapped[dict] = mapped_column(JSON)  # 训练配置
    
    # 实验结果
    metrics: Mapped[dict | None] = mapped_column(JSON)  # {"accuracy": 0.88, ...}
    diagnosis: Mapped[str | None] = mapped_column(Text)  # AI诊断
    report_html_path: Mapped[str | None] = mapped_column(String(500))
    
    # 状态和时间
    status: Mapped[str] = mapped_column(String(50))  # "pending", "running", "completed", "failed"
    created_by: Mapped[str] = mapped_column(String(20))  # "ai" or "user"
    started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]
    duration_seconds: Mapped[int | None]
    
    # 关系
    project: Mapped["Project"] = relationship(back_populates="experiments")
    logs: Mapped[list["ExperimentLog"]] = relationship(back_populates="experiment")


# app/models/reference_paper.py
class ReferencePaper(Base):
    """参考论文"""
    __tablename__ = "reference_papers"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"))
    
    # 论文信息
    title: Mapped[str] = mapped_column(String(500))
    authors: Mapped[list] = mapped_column(JSON)
    year: Mapped[int | None]
    arxiv_id: Mapped[str | None]
    url: Mapped[str | None]
    
    # 本地存储
    local_path: Mapped[str | None] = mapped_column(String(500))
    
    # 元数据
    keywords: Mapped[list] = mapped_column(JSON)
    abstract: Mapped[str | None] = mapped_column(Text)
    key_contributions: Mapped[list] = mapped_column(JSON)
    
    # 来源和状态
    source: Mapped[str] = mapped_column(String(50))  # "ai_recommended", "user_uploaded"
    download_status: Mapped[str] = mapped_column(String(50))  # "success", "failed", "pending"
    download_error: Mapped[str | None] = mapped_column(Text)
    
    created_at: Mapped[datetime]
    
    project: Mapped["Project"] = relationship(back_populates="reference_papers")


# app/models/experiment_log.py
class ExperimentLog(Base):
    """实验日志（TensorBoard之外的额外日志）"""
    __tablename__ = "experiment_logs"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    experiment_id: Mapped[UUID] = mapped_column(ForeignKey("experiments.id"))
    
    level: Mapped[str] = mapped_column(String(20))  # "info", "warning", "error"
    message: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime]
    
    experiment: Mapped["Experiment"] = relationship(back_populates="logs")


# app/models/user.py
class User(Base):
    __tablename__ = "users"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    hashed_password: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime]
```

**验收标准**：
- [ ] Alembic 迁移脚本能正常执行
- [ ] 所有表创建成功
- [ ] 关系正确定义
- [ ] 单元测试覆盖 CRUD 操作

---

## 3. 模块开发顺序（严格按此顺序）

### Phase 1: 基础设施（第1-2周）

#### 3.1 M1: 项目脚手架

**任务**：
1. 创建 `docker-compose.yml`（PostgreSQL、Redis、后端、前端）
2. 后端：FastAPI 项目初始化，包含健康检查接口
3. 前端：Vite + React + TS 项目初始化
4. 配置 CI/CD (GitHub Actions)

**验收标准**：
```bash
docker-compose up
# 后端: http://localhost:8000/health 返回 {"status": "ok"}
# 前端: http://localhost:3000 显示欢迎页
```

#### 3.2 M2: 数据模型和迁移

**任务**：
1. 实现 2.1 中的所有 SQLAlchemy 模型
2. 编写 Alembic 迁移脚本
3. 编写基础 CRUD 服务（`app/services/crud/`）
4. 编写单元测试

**接口定义**：
```python
# app/services/crud/base.py
class BaseCRUD(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    def get(self, db: AsyncSession, id: UUID) -> Optional[ModelType]: ...
    def get_multi(self, db: AsyncSession, skip: int = 0, limit: int = 100) -> list[ModelType]: ...
    def create(self, db: AsyncSession, obj_in: CreateSchemaType) -> ModelType: ...
    def update(self, db: AsyncSession, db_obj: ModelType, obj_in: UpdateSchemaType) -> ModelType: ...
    def delete(self, db: AsyncSession, id: UUID) -> ModelType: ...
```

**验收标准**：
- [ ] 所有模型能创建、读取、更新、删除
- [ ] 测试覆盖率 > 80%

#### 3.3 M3: 用户认证

**任务**：
1. 实现 JWT 认证
2. 注册/登录接口
3. 前端登录页面

**验收标准**：
- [ ] 能注册新用户
- [ ] 能登录获取 token
- [ ] 前端能存储和使用 token

---

### Phase 2: 论文管理（第3周）

#### 3.4 M4: PDF 解析服务

**任务**：创建 `app/services/paper/pdf_parser.py`

**接口定义**：
```python
from pydantic import BaseModel

class PaperContent(BaseModel):
    title: str
    authors: list[str]
    abstract: str
    keywords: list[str]
    sections: dict[str, str]  # {"introduction": "...", "methods": "..."}
    full_text: str
    references: list[dict]  # [{"title": "...", "authors": [...], "year": ...}]

class PDFParser:
    async def parse(self, pdf_path: str) -> PaperContent:
        """解析PDF论文，提取结构化信息"""
        ...
    
    async def extract_keywords(self, content: PaperContent, top_k: int = 10) -> list[str]:
        """提取关键词（结合Claude API和TF-IDF）"""
        ...
```

**实现要点**：
- 使用 PyMuPDF 提取文本
- 使用 pdfplumber 提取表格
- 使用 Claude API 提取关键词和核心贡献
- 解析引用列表

**验收标准**：
- [ ] 能解析 arxiv 上的PDF
- [ ] 能提取标题、作者、摘要
- [ ] 能识别关键词
- [ ] 能识别引用列表

#### 3.5 M5: 论文下载服务

**任务**：创建 `app/services/paper/downloader.py`

**接口定义**：
```python
class PaperDownloader:
    async def search_arxiv(self, query: str, max_results: int = 5) -> list[PaperMetadata]:
        """搜索arxiv"""
        ...
    
    async def search_semantic_scholar(self, query: str, max_results: int = 5) -> list[PaperMetadata]:
        """搜索Semantic Scholar"""
        ...
    
    async def download(self, paper: PaperMetadata, save_path: str) -> DownloadResult:
        """下载论文PDF，失败时返回错误信息"""
        return DownloadResult(
            success=bool,
            local_path=str | None,
            error=str | None
        )
    
    async def find_related_papers(
        self, 
        source_paper: PaperContent, 
        top_k: int = 3
    ) -> list[PaperMetadata]:
        """基于源论文找相关论文"""
        ...
```

**实现要点**：
- 使用 arxiv Python 库
- 使用 Semantic Scholar API
- 支持重试机制（最多3次）
- 失败时保留元数据，方便手动上传

**验收标准**：
- [ ] 能从 arxiv 下载论文
- [ ] 下载失败时正确记录错误
- [ ] 能基于关键词找相关论文

#### 3.6 M6: 论文库管理

**任务**：创建 `app/services/paper/library.py`

**接口定义**：
```python
class PaperLibrary:
    async def add_paper(
        self, 
        project_id: UUID, 
        paper: PaperMetadata,
        source: str  # "ai_recommended" or "user_uploaded"
    ) -> ReferencePaper:
        """添加论文到项目库"""
        ...
    
    async def organize_by_keyword(self, project_id: UUID) -> dict[str, list[UUID]]:
        """按关键词组织论文"""
        ...
    
    async def find_relevant(
        self, 
        project_id: UUID, 
        keywords: list[str],
        top_k: int = 5
    ) -> list[ReferencePaper]:
        """根据关键词找相关论文"""
        ...
    
    async def mark_failed(self, paper_id: UUID, error: str) -> None:
        """标记下载失败"""
        ...
    
    async def upload_manual(
        self, 
        paper_id: UUID, 
        file: UploadFile
    ) -> ReferencePaper:
        """用户手动上传失败的论文"""
        ...
```

**目录结构**：
```
storage/projects/{project_id}/reference_papers/
├── metadata.json
├── by_keyword/
│   ├── BatchNorm/
│   │   ├── paper_1.pdf
│   │   └── metadata.json
│   └── ...
├── successful/
└── failed/
    ├── failed_papers.json
    └── pending_upload/
```

**验收标准**：
- [ ] 能添加论文并按关键词分类
- [ ] 能查询相关论文
- [ ] 失败的论文能被标记和补充

---

### Phase 3: AI 核心能力（第4-5周）

#### 3.7 M7: Claude API 客户端封装

**任务**：创建 `app/services/ai/claude_client.py`

**接口定义**：
```python
class ClaudeClient:
    """Claude API 客户端，含缓存和重试"""
    
    def __init__(self, api_key: str, model: str = "claude-opus-4-7"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
    
    async def chat(
        self,
        messages: list[dict],
        system: str | None = None,
        max_tokens: int = 4096,
        use_cache: bool = True,  # 使用 prompt caching
    ) -> str:
        """基础对话"""
        ...
    
    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system: str | None = None,
    ) -> ChatResponse:
        """带工具调用的对话"""
        ...
    
    async def stream_chat(
        self,
        messages: list[dict],
        system: str | None = None,
    ) -> AsyncIterator[str]:
        """流式对话"""
        ...
```

**关键要求**：
- **必须使用 prompt caching**（参考论文内容大，需缓存）
- 支持流式响应（用于前端实时显示）
- 错误处理和重试

**验收标准**：
- [ ] 能调用 Claude API
- [ ] Prompt cache 命中率 > 50%
- [ ] 支持流式响应

#### 3.8 M8: 引导式对话服务

**任务**：创建 `app/services/ai/dialog.py`

**接口定义**：
```python
class BrainstormDialog:
    """引导式对话，帮助学生初始化项目"""
    
    def __init__(self, claude: ClaudeClient):
        self.claude = claude
        self.max_questions = 6  # 上限
    
    async def start(self, paper_content: PaperContent) -> DialogQuestion:
        """开始对话，根据论文内容生成第一个问题"""
        ...
    
    async def answer(
        self, 
        session_id: str, 
        answer: str
    ) -> DialogQuestion | ProjectConfig:
        """用户回答问题，返回下一个问题或最终配置"""
        ...
    
    async def _generate_next_question(
        self, 
        history: list[dict], 
        remaining_questions: int
    ) -> DialogQuestion:
        """生成下一个问题（避免发散）"""
        ...
    
    async def _finalize(
        self, 
        history: list[dict]
    ) -> ProjectConfig:
        """整理对话，生成项目配置"""
        ...
```

**Prompt 模板**：
```python
BRAINSTORM_SYSTEM = """
你是一个科研助手，帮助硕士研究生启动论文复现项目。

规则：
1. 一次只问一个问题
2. 优先提供选项让学生选（多选/单选）
3. 问题总数不超过{max_questions}个
4. 已经问了{asked}个问题，还剩{remaining}个
5. 如果学生答案已经足够清晰，可以提前结束

目标：帮助学生明确：
- 改进方向（数据/模型/训练策略）
- 目标指标
- 循环上限
- 参考论文（可选）

论文核心信息：
{paper_summary}

已收集的信息：
{collected_info}

请生成下一个问题，或者判断信息已足够时输出FINALIZE标记。
"""
```

**验收标准**：
- [ ] 对话不超过6轮
- [ ] 能根据论文生成合适的问题
- [ ] 能整理出完整的项目配置

#### 3.9 M9: 代码框架生成服务

**任务**：创建 `app/services/ai/code_generator.py`

**接口定义**：
```python
class CodeGenerator:
    """基于论文和配置生成代码框架"""
    
    async def generate_framework(
        self,
        paper_content: PaperContent,
        config: ProjectConfig,
    ) -> GeneratedCode:
        """生成初始代码框架"""
        return GeneratedCode(
            files={
                "data.py": "...",
                "model.py": "...",
                "train.py": "...",
                "eval.py": "...",
                "config.yaml": "...",
                "requirements.txt": "...",
                "README.md": "...",
            },
            entry_point="train.py",
            estimated_gpu_memory=8,  # GB
        )
    
    async def validate_code(self, code: dict[str, str]) -> ValidationResult:
        """静态验证代码（语法、导入等）"""
        ...
```

**分步生成策略**（重要）：
1. 先生成 `data.py` （数据处理）
2. 再生成 `model.py` （基于论文的模型架构）
3. 再生成 `train.py` （训练循环）
4. 生成 `config.yaml` （超参数）
5. 生成 `requirements.txt`
6. 生成 `README.md`

**Prompt 模板**（示例）：
```python
MODEL_GEN_SYSTEM = """
你是深度学习专家。根据论文的方法部分，生成PyTorch实现的模型代码。

要求：
1. 代码必须可运行
2. 使用类型注解
3. 每个类和函数要有 docstring
4. 关键部分要有注释说明
5. 遵循PyTorch最佳实践
6. 使用 tensorboard 记录关键指标

论文方法部分：
{methods_section}

学生的改进意图：
{improvement_targets}
"""
```

**验收标准**：
- [ ] 生成的代码通过静态检查（ruff）
- [ ] 生成的代码在 Docker 中能运行至少一个 batch
- [ ] 包含 TensorBoard 日志代码

#### 3.10 M10: 实验诊断服务

**任务**：创建 `app/services/ai/diagnostician.py`

**接口定义**：
```python
class Diagnostician:
    """实验结果诊断和改进建议"""
    
    async def diagnose(
        self,
        experiment: Experiment,
        reference_papers: list[ReferencePaper],
    ) -> Diagnosis:
        """基于5篇参考论文诊断实验结果，生成改进建议"""
        return Diagnosis(
            problem_analysis=str,  # 问题分析
            suggestions=[
                Suggestion(
                    priority="high",
                    method="加入BatchNorm",
                    reason="检测到训练不稳定",
                    evidence=["参考论文[1]报告...", "参考论文[2]报告..."],
                    expected_improvement="1-2%",
                    code_changes={"model.py": "在conv层后加BatchNorm2d"},
                ),
                ...
            ],
            top_recommendation=Suggestion,  # 最推荐的方案
        )
```

**核心 Prompt 结构**：
```python
DIAGNOSIS_PROMPT = """
你是一位机器学习实验诊断专家。

## 当前实验
- 改进方案: {improvement}
- 结果: {metrics}
- 目标: {target_metrics}
- 训练日志摘要: {log_summary}

## 5篇参考论文（已缓存，请仔细阅读）
{papers_content}  # 使用 prompt caching

## 你的任务
1. 分析当前实验存在什么问题（过拟合？欠拟合？训练不稳定？）
2. 对比参考论文的方法，找出可能的改进方向
3. 生成3个改进建议，按优先级排序
4. 每个建议必须：
   - 说明具体做什么（要能转化为代码修改）
   - 说明为什么这样做（结合参考论文证据）
   - 给出预期改进幅度
5. 输出格式为JSON

不要输出模糊建议，必须具体到代码级别。
"""
```

**验收标准**：
- [ ] 诊断建议基于参考论文
- [ ] 每个建议都有明确的代码改动
- [ ] 使用 prompt caching 减少论文读取成本

#### 3.11 M11: 代码改进服务

**任务**：创建 `app/services/ai/code_modifier.py`

**接口定义**：
```python
class CodeModifier:
    """基于改进建议修改代码"""
    
    async def apply_suggestion(
        self,
        current_code: dict[str, str],
        suggestion: Suggestion,
    ) -> ModificationResult:
        """应用一个改进建议到代码"""
        return ModificationResult(
            modified_files={"model.py": "新代码...", "config.yaml": "..."},
            change_log="加入了BatchNorm2d在每个conv层后，lr从0.01改为0.001",
            validation_passed=bool,
            errors=[],
        )
    
    async def _generate_diff(
        self,
        original: str,
        suggestion: Suggestion,
        filename: str,
    ) -> str:
        """生成精确的代码修改"""
        ...
    
    async def _validate(self, code: dict[str, str]) -> ValidationResult:
        """静态验证修改后的代码"""
        ...
```

**关键要求**：
- 使用**结构化输出**（JSON）确保修改精确
- 修改后必须通过 ruff 检查
- 保留原有代码风格

**验收标准**：
- [ ] 修改后的代码通过静态检查
- [ ] 修改后的代码能在容器中运行
- [ ] 生成的 change_log 清晰

---

### Phase 4: 实验执行系统（第6-7周）

#### 3.12 M12: Git 版本管理服务

**任务**：创建 `app/services/git/git_service.py`

**接口定义**：
```python
class GitService:
    """封装 Git 操作"""
    
    def init_repo(self, project_id: UUID, initial_code: dict[str, str]) -> str:
        """初始化项目仓库"""
        ...
    
    def create_branch(
        self, 
        project_id: UUID, 
        branch_name: str,  # "exp/2-1"
        from_branch: str,  # "exp/1"
    ) -> None:
        """从父分支创建新分支（完全复制）"""
        ...
    
    def commit_changes(
        self,
        project_id: UUID,
        branch_name: str,
        files: dict[str, str],
        message: str,
    ) -> str:  # commit hash
        """提交代码变更"""
        ...
    
    def checkout(self, project_id: UUID, branch_name: str) -> str:
        """检出分支到工作目录，返回工作目录路径"""
        ...
    
    def get_branch_tree(self, project_id: UUID) -> BranchTree:
        """获取项目的完整分支树"""
        ...
```

**分支命名规则**：
- `main`: AI 生成的初始代码
- `exp/1`: 第一轮实验
- `exp/2-1`: 第二轮第一个分支
- `exp/3-2`: 第三轮第二个分支（可能是学生新建的）

**验收标准**：
- [ ] 能创建、检出、提交分支
- [ ] 分支树结构正确
- [ ] 完全复制父节点代码

#### 3.13 M13: Docker 实验执行器

**任务**：
1. 创建 `executor/base_image/Dockerfile`（含 PyTorch、TensorBoard、常用库）
2. 创建 `executor/runner.py`（在容器内运行实验）
3. 创建 `app/services/experiment/executor.py`（后端管理容器）

**Dockerfile 关键内容**：
```dockerfile
FROM pytorch/pytorch:2.0.1-cuda11.7-cudnn8-runtime

RUN pip install \
    tensorboard \
    scikit-learn \
    pandas \
    numpy \
    matplotlib \
    tqdm

WORKDIR /workspace

# 挂载点：/workspace/code, /workspace/data, /workspace/output
```

**接口定义**：
```python
class ExperimentExecutor:
    """管理实验容器的生命周期"""
    
    async def run_experiment(
        self,
        experiment_id: UUID,
        code_path: str,
        config: dict,
    ) -> ExperimentResult:
        """启动容器运行实验，返回结果"""
        ...
    
    async def stream_logs(
        self, 
        experiment_id: UUID
    ) -> AsyncIterator[str]:
        """流式获取实验日志"""
        ...
    
    async def get_status(self, experiment_id: UUID) -> ExperimentStatus:
        """获取实验状态"""
        ...
    
    async def stop(self, experiment_id: UUID) -> None:
        """停止实验"""
        ...
    
    async def cleanup(self, experiment_id: UUID) -> None:
        """清理容器和临时文件"""
        ...
```

**验收标准**：
- [ ] 能在容器中运行 PyTorch 训练代码
- [ ] 能实时获取日志
- [ ] 能停止和清理容器
- [ ] TensorBoard 日志能被采集

#### 3.14 M14: 异步任务队列

**任务**：使用 Celery 实现异步实验管理

**接口定义**：
```python
# app/tasks/experiment_tasks.py

@celery_app.task(bind=True)
def run_experiment_task(self, experiment_id: str) -> dict:
    """运行单个实验的 Celery 任务"""
    ...

@celery_app.task(bind=True)
def iterate_experiment_loop_task(self, project_id: str) -> dict:
    """异步实验循环任务：
    1. 运行当前实验
    2. 完成后调用诊断
    3. 应用改进
    4. 创建新分支
    5. 递归启动下一轮（如果未达停止条件）
    """
    ...

@celery_app.task
def diagnose_and_improve_task(experiment_id: str) -> dict:
    """诊断+改进的独立任务"""
    ...
```

**循环控制逻辑**：
```python
def should_continue(project: Project, latest_exp: Experiment) -> bool:
    """判断是否继续下一轮迭代"""
    # 1. 用户暂停？
    if project.status == "paused":
        return False
    
    # 2. 达到目标指标？
    if all(
        latest_exp.metrics.get(k, 0) >= v 
        for k, v in project.target_metrics.items()
    ):
        return False
    
    # 3. 达到循环上限？
    experiment_count = count_experiments_in_branch(project.id, latest_exp.node_id)
    if experiment_count >= project.max_iterations:
        return False
    
    return True
```

**验收标准**：
- [ ] 异步任务能正常执行
- [ ] 循环停止条件正确
- [ ] 用户暂停能立即生效

#### 3.15 M15: 实验监控和日志采集

**任务**：创建 `app/services/experiment/monitor.py`

**接口定义**：
```python
class ExperimentMonitor:
    """实验监控服务"""
    
    async def collect_metrics(
        self, 
        experiment_id: UUID
    ) -> ExperimentMetrics:
        """从TensorBoard日志中提取指标"""
        ...
    
    async def parse_train_log(self, log_path: str) -> LogSummary:
        """解析训练日志，提取关键信息"""
        return LogSummary(
            total_epochs=int,
            completed_epochs=int,
            best_metric=dict,
            issues_detected=[],  # 检测到的问题
        )
    
    async def detect_anomalies(
        self, 
        metrics: list[float]
    ) -> list[Anomaly]:
        """检测异常（loss爆炸、准确率下降等）"""
        ...
```

**验收标准**：
- [ ] 能实时提取 TensorBoard 指标
- [ ] 能检测常见异常
- [ ] 能生成日志摘要

---

### Phase 5: 前端界面（第8-9周）

#### 3.16 M16: 项目创建向导

**页面**：`/projects/new`

**组件树**：
```
ProjectWizard/
├── PaperUploadStep      # 上传PDF
├── DialogStep           # 引导式对话
│   ├── QuestionCard    # 单个问题卡片
│   └── AnswerInput     # 输入组件
├── ReviewStep          # 审核配置
└── ConfirmStep         # 确认开始
```

**交互流程**：
```
1. 用户上传 PDF
2. 系统解析PDF后，进入对话阶段
3. 系统一次问一个问题，用户回答（多选/单选/文本）
4. 达到6轮或系统判断信息足够 → 展示汇总
5. 用户确认 → 进入代码审核阶段
```

**验收标准**：
- [ ] 上传PDF能成功
- [ ] 对话流畅（问答式）
- [ ] 能通过 API 完成配置

#### 3.17 M17: 代码审核界面

**页面**：`/projects/{id}/review-code`

**组件**：
```
CodeReview/
├── FileTree            # 文件树
├── CodeViewer          # 代码查看器（可编辑）
├── DependencyList      # 依赖列表
├── ChangesLog          # AI说明生成了什么
└── ActionBar           # 开始/修改按钮
```

**验收标准**：
- [ ] 能展示所有生成的文件
- [ ] 支持内联编辑
- [ ] 编辑后能提交

#### 3.18 M18: 实验树可视化

**页面**：`/projects/{id}/tree`

**核心组件**：`ExperimentTree`（基于 React Flow）

**组件设计**：
```typescript
interface ExperimentNodeProps {
  node: {
    id: string;              // "1", "2-1"
    metrics: Metrics;
    improvement: string;
    duration: string;
    status: "pending" | "running" | "completed" | "failed";
    reportUrl?: string;
    parentId?: string;
  };
  onCreateBranch: (nodeId: string) => void;
  onViewReport: (reportUrl: string) => void;
}

const ExperimentNode: React.FC<ExperimentNodeProps> = ({ node, ... }) => {
  return (
    <Card className={`node-card node-${node.status}`}>
      <div className="node-id">{node.id}</div>
      <div className="node-metrics">
        <span>acc: {node.metrics.accuracy}%</span>
        <span>loss: {node.metrics.loss}</span>
      </div>
      <div className="node-improvement">{node.improvement}</div>
      <div className="node-duration">{node.duration}</div>
      <div className="node-actions">
        <Button icon={<FileTextOutlined />} onClick={() => onViewReport(node.reportUrl)}>
          详细报告
        </Button>
        <Button icon={<PlusOutlined />} onClick={() => onCreateBranch(node.id)}>
          新分支
        </Button>
      </div>
    </Card>
  );
};
```

**布局**：竖向树，使用 dagre 布局算法

**实时更新**：使用 WebSocket 接收节点状态变化

**验收标准**：
- [ ] 树形展示正确
- [ ] 节点信息完整
- [ ] 支持点击 `+` 新建分支
- [ ] 实时更新运行状态

#### 3.19 M19: 分支创建对话框

**组件**：`CreateBranchModal`

**交互**：
```
1. 用户点击某节点的 `+` 按钮
2. 弹出对话框，AI 问 2-3 个问题（简化版对话）
3. 用户回答想尝试的改进方向
4. 提交后进入代码修改预览
5. 确认后开始新分支实验
```

**验收标准**：
- [ ] 能从任意节点新建分支
- [ ] 分支创建后立即开始实验
- [ ] 树上显示新分支

#### 3.20 M20: 实验详情页

**页面**：`/experiments/{id}`

**组件**：
```
ExperimentDetail/
├── HeaderSummary       # 简洁总结（结果、改进量）
├── LiveMonitor         # 实时监控（如果正在运行）
│   ├── ProgressBar
│   └── TensorBoardEmbed
├── DiagnosisPanel      # AI诊断
├── CodeChangesPanel    # 代码变更展示
├── ReferencePapersList # 参考的论文
└── ReportLink          # 打开HTML报告
```

**验收标准**：
- [ ] 显示实验完整信息
- [ ] 能查看训练曲线
- [ ] 能查看代码变更
- [ ] 能打开HTML报告

#### 3.21 M21: HTML 报告生成器

**任务**：创建 `app/services/report/html_generator.py`

**接口定义**：
```python
class HTMLReportGenerator:
    """生成实验的HTML报告"""
    
    async def generate(
        self,
        experiment: Experiment,
        project: Project,
        parent_experiment: Experiment | None,
        reference_papers: list[ReferencePaper],
    ) -> str:  # HTML文件路径
        """生成完整的HTML报告"""
        ...
```

**报告结构**：
1. 快速总结
2. 详细分析（诊断+改进理由）
3. 性能对比表
4. TensorBoard 嵌入
5. 代码变更 Diff
6. 参考文献
7. 后续建议

**使用 Jinja2 模板**：
```python
# templates/experiment_report.html.j2
<!DOCTYPE html>
<html>
<head>
    <title>实验节点 {{ node_id }} 报告</title>
    <link rel="stylesheet" href="report.css">
</head>
<body>
    {% include "sections/summary.html.j2" %}
    {% include "sections/diagnosis.html.j2" %}
    {% include "sections/comparison.html.j2" %}
    {% include "sections/curves.html.j2" %}
    {% include "sections/code_changes.html.j2" %}
    {% include "sections/references.html.j2" %}
    {% include "sections/next_steps.html.j2" %}
</body>
</html>
```

**验收标准**：
- [ ] 报告能正确生成
- [ ] 包含所有关键信息
- [ ] 独立可打开（不依赖服务器）

---

### Phase 6: 集成和优化（第10周）

#### 3.22 M22: WebSocket 实时通信

**任务**：创建 `app/api/websocket.py`

**接口**：
```python
@app.websocket("/ws/projects/{project_id}")
async def project_websocket(websocket: WebSocket, project_id: UUID):
    """项目级 WebSocket，推送实验状态变化"""
    ...

@app.websocket("/ws/experiments/{experiment_id}/logs")
async def experiment_logs_websocket(websocket: WebSocket, experiment_id: UUID):
    """实验日志流式推送"""
    ...
```

**消息类型**：
```typescript
type WSMessage = 
  | { type: "experiment_started", experimentId: string }
  | { type: "experiment_progress", experimentId: string, epoch: number, metrics: any }
  | { type: "experiment_completed", experimentId: string, metrics: any }
  | { type: "experiment_failed", experimentId: string, error: string }
  | { type: "diagnosis_ready", experimentId: string, diagnosis: any }
  | { type: "new_experiment_created", experiment: any };
```

**验收标准**：
- [ ] 实时推送实验状态
- [ ] 前端能接收并更新UI
- [ ] 断线重连正常

#### 3.23 M23: 错误处理和自动修复

**任务**：创建 `app/services/error_handler.py`

**自动修复策略**：
```python
class AutoErrorHandler:
    """遇到常见错误时自动修复"""
    
    async def handle(self, error: Exception, context: dict) -> HandleResult:
        """尝试自动修复错误"""
        if isinstance(error, ModuleNotFoundError):
            return await self._install_missing_module(error)
        elif isinstance(error, CudaOutOfMemoryError):
            return await self._reduce_batch_size(context)
        elif isinstance(error, DiskFullError):
            return await self._cleanup_old_checkpoints(context)
        else:
            return HandleResult(fixed=False, notify_user=True)
```

**验收标准**：
- [ ] 常见错误能自动修复
- [ ] 不能修复的错误清晰通知用户
- [ ] 修复过程记录在日志

#### 3.24 M24: 端到端测试

**测试场景**：
1. **完整流程测试**：
   - 上传论文 → 对话 → 生成代码 → 运行实验 → AI诊断 → 自动改进 → 循环3次
   
2. **分支创建测试**：
   - 在节点2-1创建分支3-2 → 独立运行 → 不影响主线

3. **异常处理测试**：
   - 代码错误 → 自动修复
   - 论文下载失败 → 手动上传
   - 用户暂停 → AI停止工作

**验收标准**：
- [ ] E2E 测试覆盖主要流程
- [ ] 无 P0 bug

---

## 4. 关键接口约定

### 4.1 REST API

```
# 项目管理
POST   /api/projects                        # 创建项目（含PDF上传）
GET    /api/projects                        # 列表
GET    /api/projects/{id}                   # 详情
PATCH  /api/projects/{id}                   # 更新（暂停/恢复）
DELETE /api/projects/{id}                   # 删除

# 对话
POST   /api/projects/{id}/dialog/start      # 开始对话
POST   /api/projects/{id}/dialog/answer     # 回答问题

# 参考论文
GET    /api/projects/{id}/reference-papers  # 列表
POST   /api/projects/{id}/reference-papers  # 手动上传
POST   /api/projects/{id}/reference-papers/recommend  # 触发推荐

# 代码
GET    /api/projects/{id}/code              # 获取当前分支代码
PATCH  /api/projects/{id}/code              # 修改代码
POST   /api/projects/{id}/code/validate     # 校验代码

# 实验
GET    /api/projects/{id}/experiments       # 实验列表（树结构）
POST   /api/projects/{id}/experiments       # 手动创建实验（从某节点新分支）
GET    /api/experiments/{id}                # 实验详情
GET    /api/experiments/{id}/logs           # 实验日志
GET    /api/experiments/{id}/report         # HTML报告

# WebSocket
WS     /ws/projects/{id}                    # 项目级实时消息
WS     /ws/experiments/{id}/logs            # 实验日志流
```

### 4.2 内部服务接口

见每个模块的接口定义（章节3）

---

## 5. 环境和部署

### 5.1 开发环境

```bash
# 首次启动
git clone <repo>
cd research-companion
cp .env.example .env  # 配置 API keys 等

# 启动
docker-compose up -d

# 数据库迁移
docker-compose exec backend alembic upgrade head

# 访问
# Frontend: http://localhost:3000
# Backend API: http://localhost:8000/docs
# TensorBoard: 通过实验详情页嵌入
```

### 5.2 环境变量

```bash
# .env.example
DATABASE_URL=postgresql://user:pass@postgres:5432/research_companion
REDIS_URL=redis://redis:6379/0
ANTHROPIC_API_KEY=sk-ant-xxx
SEMANTIC_SCHOLAR_API_KEY=xxx  # 可选
STORAGE_PATH=/data/projects
DOCKER_HOST=unix:///var/run/docker.sock
```

### 5.3 生产部署

- 使用 Kubernetes 部署
- 独立的 GPU 节点池用于实验执行
- Nginx 反向代理 + HTTPS
- Prometheus + Grafana 监控

---

## 6. 开发时间表

| 阶段 | 时间 | 主要任务 | 交付物 |
|------|------|---------|--------|
| Phase 1 | 第1-2周 | M1-M3 基础设施 | 可运行的骨架 |
| Phase 2 | 第3周 | M4-M6 论文管理 | PDF解析、下载、库 |
| Phase 3 | 第4-5周 | M7-M11 AI核心 | 5个AI能力就绪 |
| Phase 4 | 第6-7周 | M12-M15 实验执行 | 单个实验能跑通 |
| Phase 5 | 第8-9周 | M16-M21 前端 | 完整UI |
| Phase 6 | 第10周 | M22-M24 集成 | E2E可用 |

**总计：10周（约2.5个月）**

---

## 7. AI 开发过程 checklist

**AI 每完成一个模块必须**：

- [ ] 代码通过 lint 检查
- [ ] 单元测试通过
- [ ] 相关文档更新
- [ ] 集成到主流程测试
- [ ] Commit 到对应 branch
- [ ] 更新本文档中的完成状态

**AI 每周汇报**：
- 完成的模块列表
- 遇到的问题和解决方案
- 下周计划

---

## 8. 关键决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| 后端语言 | Python | 深度学习生态好 |
| 数据库 | PostgreSQL | JSON支持好、稳定 |
| 版本管理 | Git | 学生熟悉、成熟 |
| 分支策略 | 完全复制 | 简单、避免依赖 |
| AI模型 | Claude Opus 4.7 | 长上下文、代码能力强 |
| 前端树 | React Flow | 专业、可定制 |
| 报告格式 | HTML | 独立、可分享 |

---

## 9. 风险和缓解

| 风险 | 影响 | 缓解方案 |
|------|------|---------|
| Claude API 成本高 | 财务 | 使用 prompt caching + 缓存参考论文 |
| GPU 资源不足 | 用户体验 | 队列机制、超时限制、资源池 |
| 代码生成质量不稳定 | 核心功能 | 静态校验+沙箱测试+回滚 |
| 论文下载失败 | 参考质量 | 手动上传兜底 |
| 学生代码被修改破坏 | 数据丢失 | Git 完整版本控制 |

---

## 10. 后续优化方向（v2）

- [ ] 多GPU分布式训练支持
- [ ] 论文写作辅助（自动生成实验章节）
- [ ] 团队协作（多人共享项目）
- [ ] 更多领域支持（NLP、RL、CV细分）
- [ ] 移动端查看进度
- [ ] AI主动提醒（"你的实验完成了！"）

---

**文档版本**：1.0  
**最后更新**：2026-07-27  
**面向对象**：AI 开发助手（Claude Code / Cursor / GitHub Copilot 等）  
**使用方式**：从 Phase 1 开始，严格按顺序完成每个模块
