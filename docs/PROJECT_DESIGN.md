---
name: research-companion-design
description: 科研分身框架 —— 完整项目设计文档 v2.0（基于 Claude Agent SDK）
metadata:
  type: master-design
  date: 2026-07-27
  version: 2.0
  status: 最终版
---

# 科研分身框架 - 完整设计文档 v2.0

> **文档定位**：本文档是项目的**唯一权威设计文档**，涵盖需求、架构、开发计划、部署方案。  
> **重要变化**：v2.0 采用 **Claude Agent SDK** 作为核心，大幅简化 AI 相关开发。

---

## 目录

1. [项目定位](#1-项目定位)
2. [用户旅程](#2-用户旅程)
3. [系统架构](#3-系统架构)
4. [核心模块设计](#4-核心模块设计)
5. [数据结构](#5-数据结构)
6. [前端 UI 设计](#6-前端-ui-设计)
7. [Claude Agent SDK 集成](#7-claude-agent-sdk-集成)
8. [开发计划](#8-开发计划)
9. [部署方案](#9-部署方案)
10. [附录](#10-附录)

---

## 1. 项目定位

### 1.1 项目名称

**科研分身（Research Companion）**

### 1.2 目标用户

**硕士研究生**，特别是需要复现顶刊/顶会论文并进行改进的学生。

### 1.3 核心价值

**不仅是工具，而是研究生的科研分身：**

- 🤖 **自动复现**：从论文自动生成可运行代码
- 🧠 **智能诊断**：基于参考论文分析实验结果
- ⚙️ **异步自主**：学生离开后 AI 继续迭代
- 🌳 **实验可观测**：完整决策树，可回溯任何分支
- 📊 **详细报告**：每次实验生成 HTML 分析报告

### 1.4 设计原则

1. **极简易用** — 目标用户是"不太聪明的人"，每个功能必须简单易懂
2. **异步自主** — 学生不操作时 AI 继续工作
3. **有理有据** — 所有改进建议基于参考论文证据
4. **容错友好** — 优先自动修复，出错时用人话解释
5. **完整可观测** — 每一步决策都可追溯

---

## 2. 用户旅程

### 2.1 完整流程

```
┌─────────────────────────────────────────────────────────┐
│  阶段 1: 项目初始化（引导式对话，最多 6 个问题）        │
│  → 上传论文 PDF                                          │
│  → 一问一答（改进方向、目标指标、循环上限、参考论文）    │
│  → AI 生成初始代码框架                                    │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  阶段 2: 代码审核                                        │
│  → 学生查看/微调 AI 生成的代码                            │
│  → 点击"开始实验"                                         │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  阶段 3: 异步实验循环（AI 自主运行）                     │
│                                                          │
│  实验 → 诊断 → 改进 → 新实验 → ... → 达标或达上限       │
│                                                          │
│  期间学生可以：                                          │
│  - 查看实验树（实时更新）                                │
│  - 在任意节点新建分支（点击 + 号）                       │
│  - 暂停/恢复迭代                                         │
│  - 查看详细 HTML 报告                                    │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  阶段 4: 结果输出                                        │
│  → 完整实验树                                            │
│  → 每个节点的 HTML 报告                                  │
│  → 最优代码（可导出）                                    │
│  → 综合对比报告                                          │
└─────────────────────────────────────────────────────────┘
```

### 2.2 关键交互设计

#### 引导式对话（阶段1）

```
系统: "嘿，我是你的科研分身👋 让我帮你快速复现论文并改进它。"

Q1: [上传 PDF]
Q2: 这篇论文的核心创新是什么？ → 学生用一句话总结
Q3: 你想改进哪些方面？（多选：数据/模型/训练策略/其他）
Q4: 目标指标是什么？（如 accuracy=92%）
Q5: 最多尝试多少轮实验？（默认 5 轮）
Q6: 有相关论文要参考吗？（可选上传，也可跳过让 AI 推荐）

→ AI 生成初始代码框架
```

**关键约束**：
- 最多 6 个核心问题
- 每个问题只问一次（不追问超过 1 次）
- 优先多选/单选（不是开放式）

#### 实验树交互（阶段3）

```
每个节点显示：
- 标号（如 3-2）
- 关键指标（acc, loss）
- 改进方案（简短文本）
- 训练耗时
- 📊 详细报告链接
- ➕ 新建分支按钮

用户可以：
- 点击 ➕ 从任意节点开新分支
- 点击 📊 打开 HTML 详细报告
- 暂停整个项目的迭代
```

---

## 3. 系统架构

### 3.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                         用户浏览器                              │
│  ┌───────────────────────────────────────────────────────┐     │
│  │  React 前端                                           │     │
│  │  - 项目管理                                            │     │
│  │  - 实验树可视化（React Flow）                          │     │
│  │  - 实时监控（WebSocket）                                │     │
│  │  - HTML 报告查看                                        │     │
│  └───────────────────────────────────────────────────────┘     │
└──────────────────────┬──────────────────────────────────────────┘
                       │ HTTP / WebSocket
                       ↓
┌─────────────────────────────────────────────────────────────────┐
│                     后端服务（FastAPI）                          │
│                                                                  │
│  ┌────────────────────────┐  ┌────────────────────────────┐    │
│  │  业务逻辑层（自研）    │  │  AI 服务层（Claude 官方）   │    │
│  │                        │  │                            │    │
│  │  - 项目管理            │  │  🤖 Claude Agent SDK       │    │
│  │  - 引导对话             │  │  （代码生成/修改/修复）    │    │
│  │  - 论文管理             │  │                            │    │
│  │  - 实验树管理           │  │  🧠 Anthropic SDK          │    │
│  │  - Git 版本控制         │  │  （诊断/对话/分析）        │    │
│  │  - 报告生成             │  │                            │    │
│  │  - WebSocket 通知       │  │                            │    │
│  └────────────────────────┘  └────────────────────────────┘    │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐    │
│  │  异步任务队列（Celery + Redis）                        │    │
│  │  - 实验运行                                             │    │
│  │  - 论文下载                                             │    │
│  │  - 报告生成                                             │    │
│  └────────────────────────────────────────────────────────┘    │
└──────────────────────────────┬──────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────┐
│                     执行层                                       │
│  ┌────────────────────┐  ┌──────────────────┐  ┌────────────┐  │
│  │  Docker 实验容器   │  │  Git 仓库        │  │ 文件存储    │  │
│  │  - GPU 训练        │  │  - 分支管理      │  │ - PDF       │  │
│  │  - TensorBoard     │  │  - 版本追溯      │  │ - Reports   │  │
│  └────────────────────┘  └──────────────────┘  └────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────┐
│  数据层                                                          │
│  PostgreSQL（元数据）+ Redis（缓存/队列）                        │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 关键架构决策

| 决策 | 选择 | 理由 |
|------|------|------|
| **AI 核心** | **Claude Agent SDK** | 内置工具、权限、Hook，节省 80% 开发 |
| **诊断分析** | Anthropic SDK 直调 | 纯思考任务，不需要 Agent |
| **后端** | FastAPI + Celery | 异步支持好、Python 生态 |
| **前端** | React + TypeScript | 生态成熟、类型安全 |
| **树可视化** | React Flow | 专业节点图组件 |
| **数据库** | PostgreSQL | JSON 支持好、稳定 |
| **版本控制** | Git（GitPython） | 学生熟悉、成熟 |
| **实验隔离** | Docker | 环境隔离 |
| **代码分支** | 完全复制父节点 | 简单、可靠 |

---

## 4. 核心模块设计

### 4.1 模块划分

```
research-companion/
├── backend/
│   ├── app/
│   │   ├── api/                    # REST API 路由
│   │   ├── services/
│   │   │   ├── ai/                # AI 服务层
│   │   │   │   ├── code_agent.py  # Claude Agent SDK 封装
│   │   │   │   ├── diagnostician.py  # 诊断服务（自研）
│   │   │   │   └── dialog.py      # 引导对话（自研）
│   │   │   ├── paper/             # 论文管理
│   │   │   │   ├── parser.py
│   │   │   │   ├── downloader.py
│   │   │   │   └── library.py
│   │   │   ├── experiment/        # 实验管理
│   │   │   │   ├── tree.py
│   │   │   │   ├── executor.py
│   │   │   │   └── monitor.py
│   │   │   ├── git/               # Git 管理
│   │   │   └── report/            # 报告生成
│   │   ├── models/                # 数据模型
│   │   ├── tasks/                 # Celery 任务
│   │   └── main.py
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   ├── components/
│   │   └── services/
│   └── package.json
│
├── executor/                       # Docker 实验镜像
│   └── Dockerfile
│
└── docker-compose.yml
```

### 4.2 核心模块清单

#### 4.2.1 AI 服务层

##### **M1: CodeAgent（代码 Agent）** ⭐ 核心
- **技术**：Claude Agent SDK
- **功能**：
  - 生成初始代码框架
  - 应用改进建议（修改代码）
  - 自动修复运行错误
  - 依赖管理
- **代码量**：约 100 行（大量能力由 SDK 提供）

##### **M2: Diagnostician（诊断服务）**
- **技术**：Anthropic SDK 直接调用
- **功能**：
  - 分析实验结果
  - 对比参考论文
  - 生成结构化改进建议
- **关键**：使用 Prompt Caching 缓存参考论文

##### **M3: BrainstormDialog（引导对话）**
- **技术**：Anthropic SDK 直接调用
- **功能**：
  - 一问一答收集需求
  - 最多 6 个问题
  - 整理为项目配置

#### 4.2.2 业务逻辑层

##### **M4: PaperService（论文管理）**
- 上传/解析 PDF
- 自动推荐参考论文（arXiv、Semantic Scholar）
- 下载管理（成功/失败/待上传）
- 按关键词组织

##### **M5: ExperimentTree（实验树）**
- 节点管理（创建、状态更新）
- 分支管理（创建、检出）
- 树结构查询

##### **M6: GitService（版本管理）**
- 基于 GitPython
- 分支命名：`exp/1`, `exp/2-1`, `exp/3-2`
- 完全复制父节点代码

##### **M7: ExperimentExecutor（实验执行）**
- Docker 容器管理
- TensorBoard 日志采集
- 实时状态推送

##### **M8: ReportGenerator（报告生成）**
- Jinja2 模板
- HTML 独立报告
- 包含：总结、诊断、对比、曲线、代码变更

##### **M9: IterationLoop（迭代循环控制）**
- 异步循环任务（Celery）
- 停止条件判断
- 自主决策（学生不操作时）

#### 4.2.3 基础设施

- **M10**: 认证系统（JWT）
- **M11**: WebSocket（实时推送）
- **M12**: 文件存储管理

---

## 5. 数据结构

### 5.1 数据库表

```python
# 用户
class User:
    id: UUID
    email: str
    hashed_password: str
    created_at: datetime

# 项目
class Project:
    id: UUID
    user_id: UUID
    name: str
    paper_title: str
    paper_path: str  # PDF 本地路径
    paper_metadata: JSON  # {authors, abstract, keywords}
    
    # 学生配置
    improvement_targets: list  # ["data", "model", "training"]
    target_metrics: dict  # {"accuracy": 0.92}
    max_iterations: int
    
    # Git 仓库
    repo_path: str
    
    status: str  # "created", "running", "paused", "completed"
    created_at: datetime

# 实验节点
class Experiment:
    id: UUID
    project_id: UUID
    node_id: str  # "1", "2-1", "3-2"
    parent_node_id: str | None
    git_branch: str  # "exp/2-1"
    
    improvement_description: str
    code_changes: JSON
    config: JSON
    
    metrics: JSON | None  # {accuracy, loss, ...}
    diagnosis: str | None
    report_html_path: str | None
    
    status: str  # "pending", "running", "completed", "failed"
    created_by: str  # "ai" or "user"
    started_at: datetime | None
    completed_at: datetime | None
    duration_seconds: int | None

# 参考论文
class ReferencePaper:
    id: UUID
    project_id: UUID
    title: str
    authors: list
    arxiv_id: str | None
    local_path: str | None
    keywords: list
    abstract: str | None
    source: str  # "ai_recommended", "user_uploaded"
    download_status: str  # "success", "failed", "pending"
    download_error: str | None
```

### 5.2 文件存储结构

```
storage/projects/{project_id}/
├── metadata.json
├── paper.pdf                     # 原始论文
├── reference_papers/
│   ├── metadata.json
│   ├── by_keyword/
│   │   ├── BatchNorm/
│   │   └── ResNet/
│   ├── successful/               # 已下载
│   └── failed/                   # 待手动上传
│       └── pending_upload.json
│
├── git_repo/                     # Git 仓库（各分支代码）
│   ├── .git/
│   ├── data.py                   # 当前 checkout 的代码
│   ├── model.py
│   ├── train.py
│   └── config.yaml
│
└── experiments/
    ├── 1/
    │   ├── config.json
    │   ├── train.log
    │   ├── metrics.json
    │   ├── diagnosis.md
    │   ├── tensorboard/
    │   ├── checkpoints/
    │   └── report.html
    ├── 2-1/
    └── 3-2/
```

### 5.3 Git 分支结构

```
main (AI 生成的初始代码)
  └── exp/1 (第一次实验)
        ├── exp/2-1 (改进：+Dropout)
        │     ├── exp/3-1 (改进：+BatchNorm)
        │     └── exp/3-2 (学生新分支：残差连接)
        │           └── exp/4-2 (继续迭代)
        └── exp/2-2 (改进：数据增强)
```

**规则**：
- 分支命名：`exp/{node_id}`
- 新建分支时完全复制父分支代码
- 每次实验的代码变更 commit 到对应分支

---

## 6. 前端 UI 设计

### 6.1 关键页面

#### 6.1.1 项目创建向导

**页面**：`/projects/new`

**流程**：
```
Step 1: 上传 PDF
  ↓
Step 2: 引导式对话（一问一答）
  [左侧显示历史对话] [右侧显示当前问题]
  ↓
Step 3: 配置汇总（学生确认）
  ↓
Step 4: AI 生成代码（进度条 + 流式显示）
  ↓
Step 5: 代码审核（可编辑）
  ↓
Step 6: 开始实验
```

#### 6.1.2 实验树页面 ⭐ 核心

**页面**：`/projects/{id}/tree`

**布局**：
```
┌──────────────────────────────────────────────────────┐
│  顶部：项目信息 + 状态（运行中/暂停）+ 操作按钮      │
├──────────────────────────────────────────────────────┤
│                                                       │
│              [实验树可视化（React Flow）]            │
│                                                       │
│           ┌───────────────────┐                       │
│           │  节点 1           │                       │
│           │  acc: 85%         │                       │
│           │  [📊] [➕]        │                       │
│           └─────────┬─────────┘                       │
│                     ↓                                 │
│           ┌───────────────────┐                       │
│           │  节点 2-1         │                       │
│           │  acc: 86%         │                       │
│           │  +Dropout         │                       │
│           │  [📊] [➕]        │                       │
│           └─────┬───────┬─────┘                       │
│                 ↓       ↓                             │
│         ┌──────────┐ ┌──────────┐                     │
│         │ 节点3-1  │ │ 节点3-2  │                     │
│         │ acc:87%  │ │ 运行中.. │                     │
│         └──────────┘ └──────────┘                     │
│                                                       │
├──────────────────────────────────────────────────────┤
│  右侧栏：选中节点的详情                              │
│  - 改进方案                                           │
│  - 参考论文                                           │
│  - 训练曲线（TensorBoard 嵌入）                       │
└──────────────────────────────────────────────────────┘
```

**节点卡片信息**：
- 标号（1, 2-1, 3-2）
- 关键指标（acc, loss）
- 改进方案（简短文本）
- 训练耗时
- 状态图标（运行/完成/失败）
- 按钮：`[📊 详细报告]` `[➕ 新分支]`

**交互**：
- **点击节点** → 右侧显示详情
- **点击 📊** → 打开 HTML 报告（新窗口）
- **点击 ➕** → 弹出分支创建对话框

#### 6.1.3 分支创建对话框

**触发**：点击节点的 ➕

**内容**：
```
┌──────────────────────────────────────────┐
│  从节点 2-1 创建新分支                   │
├──────────────────────────────────────────┤
│  你想在这个节点尝试什么改进？            │
│                                          │
│  □ 更换数据增强方法                      │
│  □ 修改模型架构                          │
│  □ 调整训练策略                          │
│  □ 其他（描述...）                       │
│                                          │
│  改进的详细描述：                        │
│  ┌────────────────────────────────────┐  │
│  │                                    │  │
│  │  试试残差连接 + 更强的数据增强     │  │
│  │                                    │  │
│  └────────────────────────────────────┘  │
│                                          │
│         [取消]        [创建分支]         │
└──────────────────────────────────────────┘
```

#### 6.1.4 实验详情页

**页面**：`/experiments/{id}`

**内容**：
- 头部：简洁总结（一句话结果）
- 训练监控：TensorBoard 嵌入 iframe
- AI 诊断：改进方案 + 参考论文依据
- 代码变更：Diff 展示
- 打开完整 HTML 报告的链接

### 6.2 关键组件

```typescript
// components/ExperimentTree/index.tsx
export const ExperimentTree = ({ projectId }) => {
  const { nodes, edges } = useExperimentTree(projectId);
  
  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={{ experiment: ExperimentNode }}
      layout="vertical"  // 竖向布局
      onNodeClick={handleNodeClick}
    />
  );
};

// components/ExperimentNode/index.tsx
export const ExperimentNode = ({ data }) => (
  <Card status={data.status}>
    <NodeId>{data.nodeId}</NodeId>
    <Metrics>
      <span>acc: {data.metrics.accuracy}%</span>
      <span>loss: {data.metrics.loss}</span>
    </Metrics>
    <Improvement>{data.improvement}</Improvement>
    <Duration>{data.duration}</Duration>
    <Actions>
      <Button onClick={() => openReport(data.reportUrl)}>📊 报告</Button>
      <Button onClick={() => createBranch(data.nodeId)}>➕ 分支</Button>
    </Actions>
  </Card>
);
```

### 6.3 HTML 报告模板

**每个实验生成独立的 HTML 报告**：

```html
<!DOCTYPE html>
<html>
<head>
  <title>实验节点 {node_id} - 详细分析报告</title>
</head>
<body>
  <!-- 1. 快速总结 -->
  <section class="summary">
    <h1>实验节点 3-2</h1>
    <div class="result">✓ 成功！准确率 85.2% → 88.5% (+3.3%)</div>
    <div class="improvement">改进方案：+BatchNorm + L2正则化</div>
  </section>
  
  <!-- 2. 详细分析 -->
  <section class="analysis">
    <h2>AI 诊断</h2>
    <h3>发现的问题：</h3>
    <p>验证 loss 波动大，模型不稳定</p>
    
    <h3>改进理由：</h3>
    <ul>
      <li>参考论文[1]：BatchNorm 提升 6.8%</li>
      <li>参考论文[2]：ResNet 标准使用</li>
    </ul>
  </section>
  
  <!-- 3. 性能对比表 -->
  <section class="comparison">
    <table>
      <tr><th>版本</th><th>acc</th><th>loss</th></tr>
      <tr><td>原论文</td><td>85.2%</td><td>0.42</td></tr>
      <tr class="current"><td>节点3-2</td><td>88.5%</td><td>0.32</td></tr>
    </table>
  </section>
  
  <!-- 4. TensorBoard 嵌入 -->
  <section class="curves">
    <h2>训练曲线</h2>
    <iframe src="tensorboard/" width="100%" height="500"></iframe>
  </section>
  
  <!-- 5. 代码变更 -->
  <section class="code-diff">
    <h2>代码变更</h2>
    <pre><code>+ self.bn1 = nn.BatchNorm2d(64)</code></pre>
  </section>
  
  <!-- 6. 参考文献 -->
  <section class="references">
    <h2>参考论文</h2>
    <ul>
      <li>[1] BatchNorm (Ioffe & Szegedy 2015)</li>
      <li>[2] ResNet (He et al. 2015)</li>
    </ul>
  </section>
  
  <!-- 7. 后续建议 -->
  <section class="next-steps">
    <h2>下一步建议</h2>
    <p>接近目标(92%)，可以尝试 RandAugment 数据增强</p>
  </section>
</body>
</html>
```

---

## 7. Claude Agent SDK 集成

### 7.1 CodeAgent 完整实现

**这是整个系统 AI 部分的核心**，仅约 100 行代码。

```python
# backend/app/services/ai/code_agent.py

from claude_agent_sdk import ClaudeAgent
from typing import Optional
from pathlib import Path

class CodeAgent:
    """
    代码相关操作的 Agent 封装。
    
    使用 Claude Agent SDK，内置以下工具：
    - Read/Write/Edit：文件操作
    - Bash：执行命令（受限于权限）
    - Glob/Grep：文件搜索
    """
    
    def __init__(self, workspace: str):
        self.workspace = workspace
        self.agent = ClaudeAgent(
            working_directory=workspace,
            model="claude-opus-4-7",  # 默认使用 Opus
            
            # 权限：允许必要操作，禁止危险操作
            permissions={
                "allow": [
                    "Read(*)",                      # 读所有文件
                    "Write(*.py)",                  # 只允许写 Python
                    "Write(*.yaml)",                # 允许写配置
                    "Write(*.txt)",                 # 允许写文本
                    "Edit(*)",                      # 编辑所有文件
                    "Bash(python:*)",               # 允许 python 命令
                    "Bash(pip install:*)",          # 允许安装依赖
                    "Bash(pytest:*)",               # 允许运行测试
                    "Bash(ruff:*)",                 # 允许 lint
                ],
                "deny": [
                    "Bash(rm:*)",                   # 禁止删除
                    "Bash(curl:*)",                 # 禁止网络请求
                    "Bash(wget:*)",
                    "Write(/etc/*)",                # 禁止写系统文件
                ]
            },
            
            # Hooks：修改后自动 lint
            hooks={
                "PostToolUse": {
                    "Edit": ["ruff check {file_path}"],
                    "Write": ["ruff check {file_path}"]
                }
            }
        )
    
    # ========== 核心能力 1: 生成初始代码框架 ==========
    async def generate_framework(
        self,
        paper_content: str,
        config: dict,
    ) -> AgentResult:
        """
        根据论文和配置生成完整代码框架。
        
        Claude 会自主：
        1. 分析论文架构
        2. 生成 data.py, model.py, train.py, config.yaml
        3. 使用 ruff 检查代码
        4. 生成 requirements.txt
        """
        prompt = f"""
请根据以下论文和配置，生成完整的 PyTorch 代码框架。

## 论文内容
{paper_content}

## 学生的改进意图
- 改进方向：{config['improvement_targets']}
- 目标指标：{config['target_metrics']}

## 你需要生成的文件
1. data.py - 数据加载和预处理
2. model.py - 模型定义（基于论文）
3. train.py - 训练循环（含 TensorBoard 日志）
4. eval.py - 评估脚本
5. config.yaml - 超参数配置
6. requirements.txt - 依赖列表
7. README.md - 使用说明

## 代码要求
- 使用类型注解
- 每个关键部分要注释
- 使用 argparse 让参数可配置
- checkpoint 保存到 ./checkpoints/
- TensorBoard 日志保存到 ./runs/
- 支持通过环境变量 SANDBOX_MODE=true 只跑 1 个 batch（用于快速验证）

## 完成后
- 用 pytest 或简单脚本验证代码能启动
- 输出总结：生成了哪些文件、关键设计决策
        """
        return await self.agent.run(prompt=prompt, max_turns=30)
    
    # ========== 核心能力 2: 应用改进建议 ==========
    async def apply_suggestion(
        self,
        suggestion: dict,
    ) -> AgentResult:
        """
        根据诊断服务生成的改进建议，修改代码。
        """
        prompt = f"""
请根据以下改进建议，精确修改工作目录中的代码。

## 改进建议
方法：{suggestion['method']}
理由：{suggestion['reason']}
预期效果：{suggestion['expected_improvement']}
具体改动：{suggestion['code_changes']}

## 修改原则
1. 使用 Edit 工具做精确修改（不要重写整个文件）
2. 每次修改后用 ruff 检查
3. 最后运行 SANDBOX_MODE=true python train.py 验证代码能跑
4. 如果验证失败，分析原因并修复

## 完成后输出
- 修改了哪些文件
- 具体改了什么
- 验证结果
        """
        return await self.agent.run(prompt=prompt, max_turns=20)
    
    # ========== 核心能力 3: 修复运行错误 ==========
    async def fix_runtime_error(
        self,
        error_log: str,
    ) -> AgentResult:
        """
        当实验运行失败时，自动分析并修复错误。
        """
        prompt = f"""
代码在运行时遇到错误：

```
{error_log}
```

请：
1. 读取相关代码理解上下文
2. 分析错误原因
3. 使用 Edit 精确修复
4. 用 SANDBOX_MODE=true 验证修复成功
5. 总结做了什么修复
        """
        return await self.agent.run(prompt=prompt, max_turns=15)
```

### 7.2 Diagnostician（诊断服务，自研）

**不使用 Agent SDK，只调 Anthropic SDK**，因为是纯分析任务。

```python
# backend/app/services/ai/diagnostician.py

from anthropic import Anthropic

class Diagnostician:
    """诊断服务：分析实验结果，生成改进建议"""
    
    def __init__(self, api_key: str):
        self.client = Anthropic(api_key=api_key)
    
    async def diagnose(
        self,
        experiment_metrics: dict,
        experiment_log: str,
        parent_metrics: Optional[dict],
        target_metrics: dict,
        reference_papers: list[dict],  # 5 篇参考论文
    ) -> dict:
        """
        生成结构化的诊断和改进建议。
        
        使用 Prompt Caching 缓存参考论文。
        """
        
        # 构造参考论文的缓存内容
        papers_content = "\n\n".join([
            f"### 论文 {i+1}: {p['title']}\n"
            f"摘要：{p['abstract']}\n"
            f"关键贡献：{p['key_contributions']}"
            for i, p in enumerate(reference_papers)
        ])
        
        response = self.client.messages.create(
            model="claude-opus-4-7",
            max_tokens=4096,
            system=[
                {
                    "type": "text",
                    "text": "你是机器学习实验诊断专家。基于参考论文分析实验并给出改进建议。",
                },
                {
                    "type": "text",
                    "text": f"## 参考论文\n{papers_content}",
                    "cache_control": {"type": "ephemeral"}  # 💾 缓存
                }
            ],
            messages=[{
                "role": "user",
                "content": f"""
## 当前实验
指标：{experiment_metrics}
日志摘要：{experiment_log[:2000]}

## 上一个节点（如有）
{parent_metrics or "无（这是第一次实验）"}

## 目标指标
{target_metrics}

## 请生成
以 JSON 格式输出：
{{
  "problem_analysis": "当前实验的问题分析",
  "suggestions": [
    {{
      "priority": "high|medium|low",
      "method": "具体方法名",
      "reason": "为什么需要这个改进",
      "evidence": ["参考论文X提到...", "..."],
      "expected_improvement": "预期改进幅度",
      "code_changes": "具体的代码改动指导"
    }}
  ],
  "top_recommendation_index": 0
}}
                """
            }]
        )
        
        # 解析 JSON
        import json
        return json.loads(response.content[0].text)
```

### 7.3 BrainstormDialog（引导对话，自研）

```python
# backend/app/services/ai/dialog.py

class BrainstormDialog:
    """引导式对话服务"""
    
    MAX_QUESTIONS = 6
    
    def __init__(self, api_key: str):
        self.client = Anthropic(api_key=api_key)
        self.sessions = {}  # session_id -> conversation history
    
    async def next_question(
        self,
        session_id: str,
        paper_summary: str,
        history: list[dict],
    ) -> dict:
        """
        生成下一个问题，或判断信息已足够。
        """
        remaining = self.MAX_QUESTIONS - len([h for h in history if h['role'] == 'assistant'])
        
        if remaining <= 0:
            return await self._finalize(history)
        
        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=f"""
你是科研助手，帮助研究生初始化论文复现项目。

规则：
1. 一次只问一个问题
2. 优先多选/单选，减少开放式
3. 剩余可问 {remaining} 个问题
4. 如果信息已足够，返回 {{"finalize": true, "config": {{...}}}}
5. 否则返回 {{"question": "...", "options": [...], "type": "single|multi|text"}}

论文摘要：{paper_summary}

已收集的信息：
{[h for h in history if h['role'] == 'user']}
            """,
            messages=history,
        )
        
        import json
        return json.loads(response.content[0].text)
```

### 7.4 iterationLoop（迭代循环控制）

```python
# backend/app/tasks/iteration_tasks.py

from celery import shared_task

@shared_task
def run_iteration_loop(project_id: str):
    """
    异步迭代循环。
    
    这是 AI 自主运行的核心任务：
    1. 运行当前实验
    2. 完成后诊断
    3. 应用改进
    4. 创建新分支
    5. 递归启动下一轮（如果未达停止条件）
    """
    project = get_project(project_id)
    
    while True:
        # 1. 检查项目状态（用户可能暂停）
        if project.status == "paused":
            break
        
        # 2. 运行当前实验
        current_exp = get_current_experiment(project_id)
        result = run_experiment(current_exp)
        
        # 3. 判断停止条件
        if should_stop(project, current_exp, result):
            break
        
        # 4. 诊断
        diagnostician = Diagnostician(settings.ANTHROPIC_API_KEY)
        diagnosis = await diagnostician.diagnose(...)
        
        # 5. 应用改进
        new_branch = create_new_branch(project_id, current_exp.node_id)
        code_agent = CodeAgent(workspace=git_checkout(new_branch))
        await code_agent.apply_suggestion(diagnosis['suggestions'][0])
        
        # 6. 创建下一个实验
        new_exp = create_experiment(project_id, new_branch, diagnosis)
        
        # 7. 通知前端
        await websocket_notify(project_id, {
            "type": "new_experiment_created",
            "experiment": new_exp
        })

def should_stop(project, exp, result) -> bool:
    """判断是否停止迭代"""
    # 达到目标指标
    if all(
        result.metrics.get(k, 0) >= v
        for k, v in project.target_metrics.items()
    ):
        return True
    
    # 达到循环上限
    count = count_experiments_in_project(project.id)
    if count >= project.max_iterations:
        return True
    
    return False
```

---

## 8. 开发计划

### 8.1 总体时间线

**总工期：约 8-9 周**（相比之前的 10 周，节省 1-2 周）

```
Week 1-2: 基础设施 + 数据模型
Week 3:   论文管理 + AI 服务
Week 4:   Docker 执行 + Git 版本管理
Week 5:   异步循环 + 实验管理
Week 6-7: 前端 UI
Week 8:   HTML 报告 + WebSocket
Week 9:   集成测试 + 优化
```

### 8.2 详细模块开发顺序

#### **Phase 1: 基础设施（Week 1-2）**

##### M1: 项目脚手架
- Docker Compose 环境（PostgreSQL、Redis、后端、前端）
- FastAPI 项目初始化
- Vite + React + TS 前端初始化
- **验收**：`docker-compose up` 能启动所有服务

##### M2: 数据模型
- SQLAlchemy 模型（User、Project、Experiment、ReferencePaper）
- Alembic 迁移
- 基础 CRUD
- **验收**：所有表可以 CRUD

##### M3: 用户认证
- JWT 认证
- 注册/登录接口
- 前端登录页
- **验收**：能注册、登录

#### **Phase 2: 论文管理（Week 3）**

##### M4: PDF 解析
- 用 PyMuPDF 提取文本
- 用 Anthropic SDK 提取关键词、贡献
- **验收**：能解析 arxiv 论文

##### M5: 论文下载
- arxiv API 集成
- Semantic Scholar API 集成
- 失败处理（标记状态）
- **验收**：能下载、失败可标记

##### M6: 论文库
- 按关键词组织
- 查询接口
- 手动上传接口
- **验收**：能管理和查询

#### **Phase 3: AI 服务（Week 3-4）**

##### M7: CodeAgent（核心）⭐
- 集成 Claude Agent SDK
- 三个核心方法：`generate_framework`、`apply_suggestion`、`fix_runtime_error`
- 权限配置和 Hooks
- **验收**：能生成完整可运行的代码框架
- **代码量**：约 100 行

##### M8: Diagnostician
- Anthropic SDK 直调
- Prompt Caching
- 结构化 JSON 输出
- **验收**：能生成有理有据的改进建议

##### M9: BrainstormDialog
- 6 轮问答限制
- 自动整理为配置
- **验收**：对话不超过 6 轮，能收集完整配置

#### **Phase 4: 实验执行（Week 4-5）**

##### M10: GitService
- GitPython 封装
- 分支管理（创建、检出、提交）
- **验收**：分支树结构正确

##### M11: Docker Executor
- 预构建镜像（PyTorch + TensorBoard）
- 容器管理（启动、停止、日志）
- SANDBOX_MODE 支持（快速验证）
- **验收**：能运行 PyTorch 训练

##### M12: Celery 任务
- `run_experiment_task`
- `iterate_experiment_loop_task`
- 停止条件判断
- **验收**：异步循环工作正常

##### M13: 实验监控
- TensorBoard 日志采集
- 实时状态更新
- 异常检测
- **验收**：能实时监控实验
- **状态**：✅ 已完成（2026-08-01）

#### **Phase 5: 前端（Week 6-7）**

##### M14: 项目创建向导
- 上传 PDF
- 对话式收集配置
- 代码审核界面
- **验收**：完整流程可用
- **状态**：✅ 已完成（2026-08-01）

##### M15: 实验树可视化 ⭐
- React Flow 集成
- 竖向树布局
- 节点卡片
- 交互（点击、新建分支）
- **验收**：树形正确展示，实时更新
- **状态**：✅ 已完成（2026-08-01）

##### M16: 分支创建对话框
- 简化的问答（2-3 个问题）
- 提交后创建 Git 分支
- **验收**：能从任意节点新建分支
- **状态**：✅ 已完成（2026-08-01）

##### M17: 实验详情页
- 头部总结
- TensorBoard 嵌入
- AI 诊断展示
- 代码变更 Diff
- **验收**：信息完整展示
- **状态**：✅ 已完成（2026-08-01）

#### **Phase 6: 完善（Week 8-9）**

##### M18: HTML 报告生成
- Jinja2 模板
- 7 大 section
- 独立可打开
- **验收**：报告完整、美观
- **状态**：✅ 已完成（2026-08-01）

##### M19: WebSocket 实时通信
- 项目级 WebSocket
- 状态变化推送
- 前端实时更新
- **验收**：无需刷新即可更新
- **状态**：✅ 已完成（2026-08-01）

##### M20: 错误处理
- Claude Agent 内置错误恢复
- 用户友好的提示
- 日志记录
- **验收**：常见错误能自动处理

##### M21: E2E 测试
- 完整流程测试
- 分支创建测试
- 异常处理测试
- **验收**：无 P0 bug

### 8.3 模块工作量估算

| 模块类别 | 模块 | 工作量 |
|----------|------|--------|
| **基础设施** | M1-M3 | 8 天 |
| **论文管理** | M4-M6 | 5 天 |
| **AI 服务** | M7-M9 | 4 天 ⭐（大幅减少） |
| **实验执行** | M10-M13 | 8 天 |
| **前端** | M14-M17 | 12 天 |
| **完善** | M18-M21 | 8 天 |
| **总计** | | **45 天（约 9 周）** |

### 8.4 AI 开发时使用的指令

**给 AI 开发助手的指令模板**：

```
你现在要开发科研分身框架的 M{X} 模块。

## 模块信息
[从上面的模块清单复制]

## 开发要求
1. 严格按顺序：不要跳过前置模块
2. 测试先行：写测试再实现
3. 使用规范：Python black + ruff, TypeScript prettier + eslint
4. 文档同步：更新对应文档
5. Commit 规范：feat(m{x}): xxx

## 验收标准
[从上面的验收标准复制]

## 完成后
- Push 到 branch feature/m{x}
- 更新本文档的完成状态
- 报告完成情况
```

---

## 9. 部署方案

### 9.1 开发环境

```bash
# 1. 克隆仓库
git clone <repo>
cd research-companion

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env：填入 ANTHROPIC_API_KEY 等

# 3. 启动服务
docker-compose up -d

# 4. 数据库迁移
docker-compose exec backend alembic upgrade head

# 5. 访问
# Frontend: http://localhost:3000
# Backend: http://localhost:8000/docs
```

### 9.2 环境变量

```bash
# .env.example
DATABASE_URL=postgresql://user:pass@postgres:5432/research_companion
REDIS_URL=redis://redis:6379/0
ANTHROPIC_API_KEY=sk-ant-xxx
SEMANTIC_SCHOLAR_API_KEY=xxx  # 可选
STORAGE_PATH=/data/projects
DOCKER_HOST=unix:///var/run/docker.sock
JWT_SECRET=xxx
```

### 9.3 生产部署（可选）

- **容器编排**：Kubernetes
- **GPU 节点池**：独立于服务节点
- **反向代理**：Nginx + HTTPS
- **监控**：Prometheus + Grafana
- **日志**：ELK Stack

---

## 10. 附录

### 10.1 关键决策记录（ADR）

#### ADR-001: 使用 Claude Agent SDK 而非直接封装 Anthropic SDK
- **决策**：所有代码相关操作使用 Claude Agent SDK
- **理由**：
  - SDK 内置工具（Read/Write/Edit/Bash）
  - 内置权限管理和 Hook 系统
  - 减少 80% 代码量
  - 官方维护
- **影响**：开发工期减少 2 周

#### ADR-002: 诊断服务不使用 Agent SDK
- **决策**：诊断服务直接调用 Anthropic SDK
- **理由**：
  - 纯思考任务，不需要工具调用
  - 需要严格控制输出格式（JSON）
  - 直接调用成本更低

#### ADR-003: Git 分支采用完全复制策略
- **决策**：新建分支时完全复制父节点代码，而非 diff/引用
- **理由**：
  - 简单可靠
  - 学生易理解
  - Git 自带压缩，磁盘不是瓶颈

#### ADR-004: 实验循环采用异步 Celery 任务
- **决策**：使用 Celery + Redis
- **理由**：
  - 学生离开后 AI 继续工作
  - 支持长时间运行（可能几天）
  - 成熟的分布式方案

#### ADR-005: 前端树使用 React Flow
- **决策**：使用 React Flow 而非自研树组件
- **理由**：
  - 专业的节点图组件
  - 支持自定义节点
  - 内置 dagre 布局算法

### 10.2 成本预估

**每个项目的 Claude API 成本**：

| 操作 | 次数 | 单次成本 | 小计 |
|------|------|---------|------|
| 引导对话 | 1 | $0.02 | $0.02 |
| 生成初始代码 | 1 | $0.15 | $0.15 |
| 应用改进（含缓存） | 4-5 | $0.05 | $0.20-0.25 |
| 实验诊断 | 5 | $0.10 | $0.50 |
| 错误修复（如有） | 1-3 | $0.02 | $0.02-0.06 |
| **每项目总计** | | | **约 $0.90-1.00** |

### 10.3 风险和缓解

| 风险 | 影响 | 缓解方案 |
|------|------|---------|
| Claude API 成本高 | 财务 | Prompt caching + 模型分级 |
| GPU 资源不足 | 用户体验 | 队列机制、限制并发 |
| 代码生成质量不稳定 | 核心功能 | Agent SDK 内置验证 |
| 论文下载失败 | 参考质量 | 手动上传兜底 |
| Agent 死循环 | 系统稳定 | 设置 max_turns 上限 |

### 10.4 参考资源

- [Anthropic Claude Agent SDK 文档](https://docs.anthropic.com)
- [Anthropic Cookbook](https://github.com/anthropics/anthropic-cookbook)
- [React Flow 文档](https://reactflow.dev)
- [Celery 文档](https://docs.celeryproject.org)
- [Aider 源码](https://github.com/paul-gauthier/aider)（代码修改参考）

### 10.5 后续扩展方向（v2）

1. **多 GPU 分布式训练**
2. **论文写作辅助**（自动生成实验章节）
3. **团队协作**（多人共享项目）
4. **移动端**（查看进度）
5. **AI 主动提醒**（重要事件推送）
6. **多模态支持**（NLP、RL 等领域）

---

## 完成状态跟踪

**AI 开发助手请在完成每个模块后更新此表**：

| 模块 | 状态 | 完成时间 | Branch |
|------|------|---------|--------|
| M1 项目脚手架 | ✅ 已完成 | 2026-07-27 | - |
| M2 数据模型 | ✅ 已完成 | 2026-07-27 | - |
| M3 用户认证 | ✅ 已完成 | 2026-07-27 | - |
| M4 PDF 解析 | ✅ 已完成 | 2026-07-28 | - |
| M5 论文下载 | ✅ 已完成 | 2026-07-28 | - |
| M6 论文库 | ✅ 已完成 | 2026-07-28 | - |
| M7 CodeAgent ⭐ | ✅ 已完成 | 2026-07-29 | - |
| M8 Diagnostician | ✅ 已完成 | 2026-07-29 | - |
| M9 BrainstormDialog | ✅ 已完成 | 2026-07-29 | - |
| M10 GitService | ✅ 已完成 | 2026-07-29 | - |
| M11 Docker Executor | ✅ 已完成 | 2026-08-01 | - |
| M12 Celery 任务 | ✅ 已完成 | 2026-08-01 | - |
| M13 实验监控 | ✅ 已完成 | 2026-08-01 | - |
| M14 项目创建向导 | ✅ 已完成 | 2026-08-01 | - |
| M15 实验树 ⭐ | ✅ 已完成 | 2026-08-01 | - |
| M16 分支创建对话框 | ✅ 已完成 | 2026-08-01 | - |
| M17 实验详情页 | ✅ 已完成 | 2026-08-01 | - |
| M18 HTML 报告 | ✅ 已完成 | 2026-08-01 | - |
| M19 WebSocket | ✅ 已完成 | 2026-08-01 | - |
| M20 错误处理 | ⏳ 待开始 | - | - |
| M21 E2E 测试 | ⏳ 待开始 | - | - |

---

**文档版本**：2.0  
**最后更新**：2026-08-01
**关键变化**：采用 Claude Agent SDK，开发工作量减少 40%  
**下一步**：开始 M1 项目脚手架
