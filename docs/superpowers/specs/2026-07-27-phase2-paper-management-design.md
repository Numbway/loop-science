# Phase 2 论文管理 - 设计文档

**日期**：2026-07-27
**状态**：已确认
**依赖**：Phase 1（M1-M3 已完成）

---

## 1. 架构概览

```
backend/app/
├── services/paper/
│   ├── parser.py          # M4: PDF 解析
│   ├── downloader.py      # M5: 论文检索/下载
│   └── library.py         # M6: 论文库管理
├── api/papers.py          # REST API 路由
└── schemas/paper.py       # Pydantic 模型

frontend/src/pages/
└── ReferencePapers.tsx    # 论文库页面
```

---

## 2. M4: PDF 解析服务 (`parser.py`)

### 职责
从 PDF 论文中提取结构化信息。

### 数据类型
```python
class PaperContent(BaseModel):
    title: str
    authors: list[str]
    abstract: str
    keywords: list[str]
    sections: dict[str, str]  # {"introduction": "...", "methods": "..."}
    full_text: str
    references: list[dict]    # [{"title": "...", "authors": [...], "year": ...}]
    key_contributions: list[str]
```

### 处理流程
1. **PyMuPDF 提取**：全文文本、章节标题识别、引用列表
2. **AI 增强**（可选）：调用 Claude 提取关键词和核心贡献
3. **降级**：Claude 不可用时，关键词用 TF-IDF 规则，贡献置空

### 依赖
- PyMuPDF（本地必选）
- Anthropic SDK（AI 增强，可选）

### 验收
- 能解析 arxiv PDF
- 提取标题、作者、摘要
- 关键词不为空（本地或 AI 均可）

---

## 3. M5: 论文检索/下载 (`downloader.py`)

### 职责
搜索并下载参考论文，支持失败恢复。

### 接口设计
```python
class PaperSearchClient(Protocol):
    async def search(self, query: str, max_results: int = 5) -> list[PaperMetadata]: ...
    async def download(self, paper_id: str, save_path: str) -> DownloadResult: ...

class ArxivClient(PaperSearchClient): ...
class SemanticScholarClient(PaperSearchClient): ...
class FakeSearchClient(PaperSearchClient): ...  # 测试用
```

### 数据类型
```python
class PaperMetadata(BaseModel):
    title: str
    authors: list[str]
    year: int | None
    arxiv_id: str | None
    url: str | None
    abstract: str | None

class DownloadResult(BaseModel):
    success: bool
    local_path: str | None
    error: str | None
```

### 处理流程
1. 通过 arXiv API 搜索论文
2. Semantic Scholar 获取补充信息
3. 下载 PDF 并保存到 `storage/projects/{id}/reference_papers/`
4. 失败时设置 `download_status="failed"` 并记录错误

### 依赖
- arxiv Python 库
- httpx（HTTP 客户端）
- FakeSearchClient（测试注入）

### 验收
- 能从 arXiv 搜索和下载论文
- 下载失败时正确记录错误
- FakeSearchClient 可注入进行离线测试

---

## 4. M6: 论文库管理 (`library.py` + 前端)

### 后端职责
管理项目的参考论文集合，包括文件存储和数据库操作。

### API 路由 (`api/papers.py`)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/projects/{id}/papers` | 论文列表（支持关键词筛选） |
| POST | `/api/projects/{id}/papers/search` | 外部搜索论文（传 query） |
| POST | `/api/projects/{id}/papers` | 添加论文到库 |
| POST | `/api/papers/{id}/upload` | 手动上传失败论文的 PDF |
| DELETE | `/api/papers/{id}` | 删除论文 |
| GET | `/api/papers/{id}/keywords` | 按关键词分组 |

### 文件存储
```
storage/projects/{project_id}/reference_papers/
├── by_keyword/
│   ├── BatchNorm/
│   │   └── paper.pdf
│   └── ResNet/
│       └── paper.pdf
├── successful/
└── failed/
    └── pending_upload.json
```

### 前端页面 (`ReferencePapers.tsx`)
- 搜索栏：输入关键词搜索 arXiv
- 论文列表：标题、作者、下载状态、关键词标签
- 添加按钮：从搜索结果添加到库
- 上传按钮：手动上传失败的论文 PDF
- 关键词筛选

### 验收
- 能添加论文并按关键词分类
- 能查询相关论文
- 失败的论文能被标记和补充上传

---

## 5. 错误处理

| 场景 | 处理 |
|------|------|
| PDF 解析失败 | 抛出 `PaperParseError`，返回 400 |
| arXiv API 超时 | 重试 3 次，失败返回部分结果 |
| 下载失败 | 保留元数据（`download_status="failed"`），记录错误 |
| Claude API 不可用 | 降级为纯本地解析 |
| 文件不存在 | 返回 404 |

---

## 6. 测试策略

- M4 单元测试：真实 PDF 文件解析
- M5 单元测试：用 FakeSearchClient 替换外部 API
- M6 集成测试：API 端点 + 数据库
- 前端：React Testing Library 组件测试

---

## 7. 验证清单

- [ ] M4：解析 arxiv PDF，提取标题/作者/摘要/关键词
- [ ] M5：搜索 arXiv 返回结果，下载成功和失败处理
- [ ] M6：API 增删查，按关键词筛选，前端页面交互
- [ ] `.env` 不在提交中
- [ ] 更新 `PROGRESS.md` 和 `PROJECT_DESIGN.md` 完成状态