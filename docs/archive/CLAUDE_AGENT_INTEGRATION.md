---
name: claude-agent-integration
description: Claude Agent SDK 集成方案 —— 明确代码操作用Claude Agent，其余自研的具体实现
metadata:
  type: integration-plan
  date: 2026-07-27
  version: 1.0
---

# Claude Agent SDK 集成方案

## 一、明确的分工

### 🤖 使用 Claude Agent SDK（涉及代码的所有操作）

| 功能 | 说明 |
|------|------|
| **1. 代码框架生成** | 根据论文和配置生成完整的初始代码 |
| **2. 代码修改** | 根据改进建议精确修改现有代码 |
| **3. 代码验证** | 静态检查、语法验证、运行时错误诊断 |
| **4. 代码错误自动修复** | 遇到运行错误时自动修复 |
| **5. 依赖管理** | 分析代码需要的依赖，生成 requirements.txt |
| **6. 代码解释** | 向学生解释代码逻辑 |

### 🛠️ 自己开发（业务逻辑和基础设施）

| 功能 | 说明 |
|------|------|
| **1. 引导式对话** | 收集学生意图（虽然也调 Claude API，但流程自控） |
| **2. 论文管理** | PDF 解析、下载、库管理 |
| **3. 实验诊断** | 分析实验结果，生成改进建议（调 Claude API 但不用 Agent） |
| **4. 实验树管理** | 分支、节点、状态管理 |
| **5. Git 版本控制** | 分支创建、检出、提交 |
| **6. Docker 执行环境** | 容器编排、日志采集 |
| **7. TensorBoard 集成** | 训练监控 |
| **8. 报告生成** | HTML 报告的 Jinja2 渲染 |
| **9. 前端** | 所有 UI 交互 |
| **10. 数据库** | 数据模型、持久化 |

---

## 二、为什么这样分工？

### **代码操作交给 Claude Agent 的理由**：

1. **代码修改的精确性极难保证** — 需要读文件、精确定位、替换、验证的完整循环
2. **工具调用编排复杂** — read/write/bash/validate 的动态组合
3. **错误恢复困难** — 需要多轮尝试才能修复
4. **Anthropic 已经解决了这些问题** — 官方 SDK 内置支持

### **诊断分析自己写的理由**：

1. **业务逻辑重** — 需要结合参考论文、历史实验、目标指标等上下文
2. **不需要工具调用** — 只是分析和生成建议，是"纯思考"任务
3. **Prompt 精细控制** — 需要严格控制输出格式（JSON、结构化建议）
4. **成本敏感** — Agent 每次调用工具都有成本，直接 API 更省

---

## 三、Claude Agent SDK 集成架构

### 3.1 整体架构

```
┌───────────────────────────────────────────────────────┐
│  你的业务代码 (FastAPI 后端)                          │
│                                                       │
│  ┌─────────────────────────────────────────────┐     │
│  │  services/ai/code_agent.py                  │     │
│  │  (封装 Claude Agent SDK)                    │     │
│  │                                             │     │
│  │  class CodeAgent:                           │     │
│  │    - generate_framework(paper, config)      │     │
│  │    - modify_code(code, suggestion)          │     │
│  │    - validate_code(code)                    │     │
│  │    - fix_runtime_error(code, error)         │     │
│  └─────────────────────────────────────────────┘     │
│                    ↓                                  │
│  ┌─────────────────────────────────────────────┐     │
│  │  Anthropic Python SDK                       │     │
│  │  - client.messages.create() with tools     │     │
│  │  - 自动工具调用循环                          │     │
│  │  - Prompt caching                          │     │
│  └─────────────────────────────────────────────┘     │
│                    ↓                                  │
│  ┌─────────────────────────────────────────────┐     │
│  │  你自己实现的工具 (Tool Functions)          │     │
│  │  - read_file(path)                          │     │
│  │  - write_file(path, content)                │     │
│  │  - list_files(directory)                    │     │
│  │  - run_python_syntax_check(code)            │     │
│  │  - run_bash(cmd) (在Docker沙箱中)           │     │
│  │  - search_reference_paper(keyword)          │     │
│  └─────────────────────────────────────────────┘     │
└───────────────────────────────────────────────────────┘
```

### 3.2 核心：CodeAgent 类

**文件路径**：`backend/app/services/ai/code_agent.py`

```python
from anthropic import Anthropic
from typing import Optional
from pathlib import Path

class CodeAgent:
    """
    封装 Claude Agent SDK，处理所有代码相关操作。
    
    使用 Anthropic 的 Tool Use 功能，让 Claude 自主决定何时读文件、
    写文件、验证代码等，直到任务完成。
    """
    
    def __init__(
        self,
        api_key: str,
        workspace_path: str,  # 项目工作目录
        model: str = "claude-opus-4-7",
    ):
        self.client = Anthropic(api_key=api_key)
        self.model = model
        self.workspace = Path(workspace_path)
        self.tools = self._register_tools()
    
    def _register_tools(self) -> list[dict]:
        """注册 Claude 可以调用的工具"""
        return [
            {
                "name": "read_file",
                "description": "读取工作目录下的文件内容",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "相对于工作目录的文件路径"
                        }
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "write_file",
                "description": "写入或覆盖文件内容",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"}
                    },
                    "required": ["path", "content"]
                }
            },
            {
                "name": "edit_file",
                "description": "在文件中查找 old_string 并替换为 new_string（精确修改）",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "old_string": {"type": "string"},
                        "new_string": {"type": "string"},
                    },
                    "required": ["path", "old_string", "new_string"]
                }
            },
            {
                "name": "list_files",
                "description": "列出目录下的文件",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "directory": {"type": "string", "default": "."}
                    }
                }
            },
            {
                "name": "check_syntax",
                "description": "对Python代码进行语法和lint检查",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "run_in_sandbox",
                "description": "在Docker沙箱中执行代码，快速验证是否能运行（不完整训练）",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "script": {"type": "string", "description": "要执行的Python脚本路径"},
                        "timeout": {"type": "integer", "default": 60}
                    },
                    "required": ["script"]
                }
            },
        ]
    
    async def _execute_tool(self, tool_name: str, tool_input: dict) -> str:
        """执行工具调用"""
        if tool_name == "read_file":
            path = self.workspace / tool_input["path"]
            return path.read_text() if path.exists() else f"File not found: {path}"
        
        elif tool_name == "write_file":
            path = self.workspace / tool_input["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(tool_input["content"])
            return f"File written: {path}"
        
        elif tool_name == "edit_file":
            path = self.workspace / tool_input["path"]
            content = path.read_text()
            old = tool_input["old_string"]
            new = tool_input["new_string"]
            
            if old not in content:
                return f"Error: old_string not found in {path}"
            
            if content.count(old) > 1:
                return f"Error: old_string appears multiple times, please provide more context"
            
            path.write_text(content.replace(old, new))
            return f"File edited: {path}"
        
        elif tool_name == "list_files":
            directory = self.workspace / tool_input.get("directory", ".")
            return "\n".join(str(p.relative_to(self.workspace)) for p in directory.rglob("*"))
        
        elif tool_name == "check_syntax":
            # 使用 ruff 检查
            import subprocess
            path = self.workspace / tool_input["path"]
            result = subprocess.run(
                ["ruff", "check", str(path)],
                capture_output=True, text=True
            )
            return result.stdout + result.stderr
        
        elif tool_name == "run_in_sandbox":
            # 在Docker沙箱中运行
            from app.services.experiment.sandbox import Sandbox
            sandbox = Sandbox(self.workspace)
            return await sandbox.run_script(
                tool_input["script"],
                timeout=tool_input.get("timeout", 60)
            )
    
    async def _run_agent_loop(
        self,
        system_prompt: str,
        user_message: str,
        max_iterations: int = 20,
    ) -> AgentResult:
        """
        运行 Agent 循环，直到 Claude 说完成或达到最大迭代次数。
        
        这是核心方法，处理 tool use 的完整循环。
        """
        messages = [{"role": "user", "content": user_message}]
        
        for iteration in range(max_iterations):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=8192,
                system=system_prompt,
                tools=self.tools,
                messages=messages,
            )
            
            # 检查是否需要调用工具
            if response.stop_reason == "end_turn":
                # Claude 完成任务，返回最终结果
                return AgentResult(
                    success=True,
                    final_message=response.content[0].text,
                    iterations=iteration + 1,
                )
            
            elif response.stop_reason == "tool_use":
                # Claude 请求调用工具
                messages.append({"role": "assistant", "content": response.content})
                
                tool_results = []
                for content_block in response.content:
                    if content_block.type == "tool_use":
                        result = await self._execute_tool(
                            content_block.name,
                            content_block.input
                        )
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": content_block.id,
                            "content": result,
                        })
                
                messages.append({"role": "user", "content": tool_results})
        
        return AgentResult(
            success=False,
            final_message="Max iterations reached",
            iterations=max_iterations,
        )
    
    # ========== 对外接口 ==========
    
    async def generate_framework(
        self,
        paper_content: PaperContent,
        config: ProjectConfig,
    ) -> AgentResult:
        """生成完整的代码框架"""
        system_prompt = self._build_framework_gen_prompt(paper_content, config)
        user_message = """
请根据论文和配置，在工作目录中生成完整的代码框架，包括：
1. data.py - 数据加载和预处理
2. model.py - 模型定义（基于论文）
3. train.py - 训练循环
4. eval.py - 评估脚本
5. config.yaml - 超参数配置
6. requirements.txt - 依赖列表
7. README.md - 使用说明

要求：
- 每个文件写完后使用 check_syntax 验证
- 最后使用 run_in_sandbox 验证代码能启动（跑1个batch）
- 如果发现问题就修复，直到全部通过
        """
        return await self._run_agent_loop(system_prompt, user_message)
    
    async def apply_suggestion(
        self,
        current_branch_path: str,
        suggestion: Suggestion,
    ) -> AgentResult:
        """应用改进建议，修改代码"""
        # 切换工作目录到当前分支
        self.workspace = Path(current_branch_path)
        
        system_prompt = self._build_modification_prompt(suggestion)
        user_message = f"""
根据以下改进建议，修改工作目录中的代码：

## 改进建议
方法：{suggestion.method}
原因：{suggestion.reason}
预期改进：{suggestion.expected_improvement}
具体的代码改动指导：{suggestion.code_changes}

## 你需要做的
1. 先用 read_file 读取相关文件，理解现有代码
2. 使用 edit_file 精确修改（每次只改一处，用 old_string/new_string）
3. 修改后使用 check_syntax 验证
4. 使用 run_in_sandbox 验证代码能运行
5. 如果验证失败，分析原因并修复
6. 完成后总结你做了哪些改动

重要：不要重写整个文件，使用 edit_file 做精确修改。
        """
        return await self._run_agent_loop(system_prompt, user_message)
    
    async def fix_runtime_error(
        self,
        code_path: str,
        error_log: str,
    ) -> AgentResult:
        """自动修复运行时错误"""
        self.workspace = Path(code_path)
        
        system_prompt = "你是一个Python调试专家，擅长修复PyTorch训练代码的错误。"
        user_message = f"""
代码运行时遇到以下错误：

```
{error_log}
```

请：
1. 读取相关代码理解上下文
2. 分析错误原因
3. 修复错误（使用 edit_file）
4. 使用 run_in_sandbox 验证修复
5. 总结修复了什么问题
        """
        return await self._run_agent_loop(system_prompt, user_message)
    
    def _build_framework_gen_prompt(
        self, 
        paper: PaperContent, 
        config: ProjectConfig
    ) -> str:
        """构建代码生成的 system prompt（使用 prompt caching）"""
        return f"""
你是一位深度学习研究员，擅长复现论文并写高质量的PyTorch代码。

## 论文信息（长期缓存）
标题：{paper.title}
摘要：{paper.abstract}
方法部分：
{paper.sections.get('methods', '')}

实验部分：
{paper.sections.get('experiments', '')}

## 学生的配置
改进方向：{config.improvement_targets}
目标指标：{config.target_metrics}

## 你的行为准则
1. 生成的代码必须可运行
2. 使用类型注解
3. 关键部分要注释说明
4. 使用 TensorBoard 记录 loss 和 metrics
5. 保存 checkpoint 到 ./checkpoints/
6. 使用 argparse 让参数可配置
7. 每写完一个文件就用 check_syntax 检查
8. 最后用 run_in_sandbox 验证代码能启动

## 输出的代码风格要求
- 使用 PyTorch Lightning 或原生 PyTorch（选一个）
- 遵循 PEP 8
- 单个文件不超过 500 行
        """
    
    def _build_modification_prompt(self, suggestion: Suggestion) -> str:
        """构建代码修改的 system prompt"""
        return """
你是一位代码修改专家。你的任务是精确地修改现有代码，实现改进建议。

## 修改原则
1. **最小化改动** — 只改必要的地方
2. **使用 edit_file** — 通过 old_string/new_string 精确替换
3. **保持代码风格** — 与现有代码一致
4. **验证修改** — 每次修改后运行 check_syntax
5. **可回滚性** — 如果修改导致错误，回滚并重试

## 常见修改模式
- 添加新的层：先读 model.py 找到 __init__，用 edit_file 添加
- 修改超参数：直接修改 config.yaml
- 添加数据增强：修改 data.py 的 transforms

## 输出
最后总结：
- 修改了哪些文件
- 具体改了什么
- 验证结果
        """
```

### 3.3 数据类型定义

```python
# app/schemas/agent.py
from pydantic import BaseModel

class AgentResult(BaseModel):
    """Agent 执行结果"""
    success: bool
    final_message: str
    iterations: int
    modified_files: list[str] = []
    errors: list[str] = []


class Suggestion(BaseModel):
    """改进建议（诊断服务输出）"""
    priority: str  # "high", "medium", "low"
    method: str
    reason: str
    evidence: list[str]
    expected_improvement: str
    code_changes: dict[str, str]  # {文件名: 改动描述}
```

---

## 四、诊断服务（自己开发）

诊断服务**不用 Agent**，只是普通的 Claude API 调用。

**文件路径**：`backend/app/services/ai/diagnostician.py`

```python
class Diagnostician:
    """实验诊断 - 自研，不用 Agent"""
    
    def __init__(self, claude_client: Anthropic):
        self.client = claude_client
    
    async def diagnose(
        self,
        experiment: Experiment,
        parent_experiment: Optional[Experiment],
        reference_papers: list[ReferencePaper],
    ) -> Diagnosis:
        """
        基于实验结果和参考论文，生成诊断和改进建议。
        
        注意：这里不用 Agent，因为不涉及工具调用，只是分析。
        """
        
        # 构造 prompt（使用 prompt caching 缓存长期不变的部分）
        system_prompt = self._build_system_prompt(reference_papers)
        user_message = self._build_user_message(experiment, parent_experiment)
        
        response = self.client.messages.create(
            model="claude-opus-4-7",
            max_tokens=4096,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"}  # 缓存参考论文
                }
            ],
            messages=[{"role": "user", "content": user_message}],
        )
        
        # 解析 JSON 输出为结构化的 Diagnosis
        return self._parse_response(response.content[0].text)
    
    def _build_system_prompt(self, papers: list[ReferencePaper]) -> str:
        """构建 system prompt，包含参考论文"""
        papers_content = "\n\n".join([
            f"### 论文 {i+1}: {p.title}\n关键词：{p.keywords}\n摘要：{p.abstract}\n主要贡献：{p.key_contributions}"
            for i, p in enumerate(papers)
        ])
        
        return f"""
你是一位机器学习实验诊断专家。

## 5篇参考论文（缓存）
{papers_content}

## 输出格式（必须严格遵守JSON格式）
{{
  "problem_analysis": "分析当前实验存在的问题",
  "suggestions": [
    {{
      "priority": "high|medium|low",
      "method": "具体方法名称",
      "reason": "为什么需要这个改进",
      "evidence": ["参考论文X提到...", "参考论文Y证明..."],
      "expected_improvement": "预期改进幅度",
      "code_changes": {{
        "文件名": "具体改动描述（要能转化为代码修改）"
      }}
    }}
  ],
  "top_recommendation_index": 0
}}
        """
```

---

## 五、更新后的开发计划

### 相比之前的开发计划，主要变化：

#### **M9 代码框架生成服务** → 改为 M9-Agent

**旧方案**：
```python
# 自己实现所有细节
class CodeGenerator:
    async def generate_framework(...): 
        # 自己调 API、验证、重试
        ...
```

**新方案**：
```python
# 使用 Claude Agent SDK
class CodeAgent:
    async def generate_framework(...):
        # 调用 _run_agent_loop
        # Claude 自主决定何时读写文件、验证
        return await self._run_agent_loop(system_prompt, user_message)
```

**开发工作量**：
- 减少 60%（不用自己实现 tool use 循环）
- 需要新增：定义工具函数、Docker 沙箱

#### **M11 代码改进服务** → 改为 M11-Agent

**旧方案**：手动生成 diff、验证
**新方案**：Agent 自主使用 `edit_file` 工具精确修改

### 具体变化的模块清单

| 模块 | 变化 |
|------|------|
| **M9 代码生成** | 用 Agent SDK 实现 |
| **M11 代码修改** | 用 Agent SDK 实现 |
| **新增 M9.5** | 实现工具函数（read/write/edit/check/sandbox） |
| **新增 M9.6** | Docker 沙箱服务（快速验证代码） |
| **M10 诊断** | 保持自研，只调 API 不用 Agent |
| **M23 错误处理** | 用 Agent SDK 实现 `fix_runtime_error` |

---

## 六、Docker 沙箱设计

**为什么需要**：Agent 需要快速验证代码（跑1个batch即可），完整训练太慢。

**文件路径**：`backend/app/services/experiment/sandbox.py`

```python
class Sandbox:
    """轻量级 Docker 沙箱，用于快速验证代码"""
    
    async def run_script(
        self,
        script: str,
        timeout: int = 60,
    ) -> str:
        """
        在容器中运行脚本，用于 Agent 验证代码是否能启动。
        
        - 使用预热的容器（减少启动时间）
        - 强制 1 个 batch 后退出
        - 返回 stdout + stderr
        """
        # 使用 docker-py
        # 挂载工作目录
        # 设置环境变量 SANDBOX_MODE=true（让训练脚本只跑1个batch）
        ...
```

**关键**：在训练脚本中加个检查：
```python
# train.py
if os.getenv("SANDBOX_MODE"):
    max_batches = 1  # 验证模式只跑1个batch
```

---

## 七、成本预估

### Claude Agent 的成本

**每次代码生成/修改的估算**：
- 平均 5-10 次工具调用循环
- 每次约 3000-5000 tokens
- 总计约 15,000-50,000 tokens
- **成本**：约 $0.05-0.15 / 次（Opus）
- 使用 Haiku 会便宜 5-10 倍

### **优化策略**：

1. **模型分级**：
   - **代码生成**：用 Opus（质量优先）
   - **代码修改**：用 Sonnet（平衡）
   - **代码验证/错误修复**：用 Haiku（速度和成本）

```python
class CodeAgent:
    def __init__(self):
        self.models = {
            "generate": "claude-opus-4-7",
            "modify": "claude-sonnet-4-6",
            "fix": "claude-haiku-4-5",
        }
```

2. **Prompt Caching**：论文内容缓存起来
3. **工具调用去重**：避免重复读同一个文件
4. **缓存生成结果**：相似论文可能共用框架

---

## 八、开发步骤（针对代码 Agent 部分）

### Step 1: 环境准备（1天）
```bash
pip install anthropic
```

### Step 2: 实现基础工具（2天）
- `read_file`
- `write_file`
- `edit_file`（重点，参考 Aider 的实现）
- `list_files`
- `check_syntax`

### Step 3: 实现 Docker 沙箱（2天）
- 预热容器
- 挂载卷
- 快速运行验证脚本

### Step 4: 实现 CodeAgent 类（3天）
- `_run_agent_loop`（核心）
- `generate_framework`
- `apply_suggestion`
- `fix_runtime_error`

### Step 5: 集成测试（2天）
- 完整代码生成流程
- 代码修改流程
- 错误修复流程

**总计：约 10 个工作日**（相比自研 20+ 天，节省一半）

---

## 九、示例：完整的调用流程

### 场景：学生完成初始配置，AI 生成初始代码

```python
# app/tasks/experiment_tasks.py

@celery_app.task
def generate_initial_code_task(project_id: str) -> dict:
    """异步任务：生成初始代码"""
    project = get_project(project_id)
    paper = parse_paper(project.paper_path)
    
    # 创建 Git 仓库
    git_service.init_repo(project_id)
    workspace = git_service.get_workspace_path(project_id)
    
    # 调用 Code Agent 生成代码
    agent = CodeAgent(
        api_key=settings.ANTHROPIC_API_KEY,
        workspace_path=workspace,
    )
    
    result = await agent.generate_framework(
        paper_content=paper,
        config=project.get_config(),
    )
    
    if result.success:
        # 提交到 main 分支
        git_service.commit_changes(
            project_id, 
            branch="main",
            message="Initial code generation",
        )
        
        # 通知前端
        await websocket_manager.notify(
            project_id,
            {"type": "code_generated", "files": result.modified_files}
        )
    else:
        # 处理失败
        ...
```

### 场景：诊断后应用改进

```python
@celery_app.task
def diagnose_and_improve_task(experiment_id: str) -> dict:
    """诊断实验并应用改进"""
    experiment = get_experiment(experiment_id)
    project = experiment.project
    
    # 1. 诊断（自研，不用 Agent）
    diagnostician = Diagnostician(claude_client)
    diagnosis = await diagnostician.diagnose(
        experiment=experiment,
        parent_experiment=get_parent(experiment),
        reference_papers=get_reference_papers(project.id),
    )
    
    # 2. 选择最推荐的改进
    top_suggestion = diagnosis.suggestions[diagnosis.top_recommendation_index]
    
    # 3. 创建新分支
    new_node_id = generate_next_node_id(experiment.node_id)
    new_branch = f"exp/{new_node_id}"
    git_service.create_branch(
        project.id, 
        new_branch, 
        from_branch=experiment.git_branch
    )
    
    # 4. 使用 Code Agent 应用改进（这里用 Agent）
    workspace = git_service.checkout(project.id, new_branch)
    agent = CodeAgent(
        api_key=settings.ANTHROPIC_API_KEY,
        workspace_path=workspace,
    )
    
    modification_result = await agent.apply_suggestion(
        current_branch_path=workspace,
        suggestion=top_suggestion,
    )
    
    if modification_result.success:
        # 提交并启动新实验
        git_service.commit_changes(project.id, new_branch, "Apply improvement")
        create_and_run_experiment(project.id, new_node_id, new_branch, top_suggestion)
    else:
        # 修改失败，通知用户
        ...
```

---

## 十、总结

### 关键决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 代码操作实现方式 | **Claude Agent SDK** | 精确性、错误恢复、开发效率 |
| 诊断分析实现方式 | **直接调 Claude API** | 纯思考任务，不需要工具 |
| 论文管理 | **自研** | 业务逻辑清晰，无需 AI |
| Git 管理 | **自研（GitPython）** | 成熟方案 |
| 前端 | **自研（React）** | 定制化需求 |

### 开发工作量对比

| 模块 | 全自研 | 混合方案 |
|------|--------|---------|
| 代码生成 | 15天 | **5天** |
| 代码修改 | 10天 | **3天** |
| 错误修复 | 8天 | **2天** |
| 其他 | 60天 | 60天 |
| **总计** | **93天** | **70天** |

**节省约 25% 的开发时间，且质量更高。**

---

**文档版本**：1.0  
**最后更新**：2026-07-27
