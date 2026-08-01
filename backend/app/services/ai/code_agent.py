"""Code Agent — AI-powered code generation, modification, and repair.

Uses Anthropic SDK with tool-use loop for real mode.
Auto-falls back to mock mode when no valid API key is configured.
"""

import json
import logging
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.schemas.ai import AgentResult

logger = logging.getLogger(__name__)

# ── Tool definitions (Anthropic tool-use schema) ─────────────────

TOOLS = [
    {
        "name": "read_file",
        "description": "Read the contents of a file in the workspace.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path relative to workspace root.",
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write or overwrite a file in the workspace.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": "Replace old_string with new_string in a file. Must be exact match and unique.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"},
            },
            "required": ["path", "old_string", "new_string"],
        },
    },
    {
        "name": "list_files",
        "description": "List all files in the workspace directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "default": "."},
            }
        },
    },
    {
        "name": "run_check",
        "description": "Run ruff lint check on a Python file. Returns lint errors if any.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
            },
            "required": ["path"],
        },
    },
]

SYSTEM_PROMPT = """You are an expert deep learning researcher and PyTorch developer.
You work in a workspace directory. You can read, write, and edit files.
When you finish your task, output a summary of what you did.
Always write clean, well-typed, well-commented Python code."""


class CodeAgent:
    """AI agent for code generation, modification, and error repair.

    In real mode: uses Anthropic SDK with tool-use loop.
    In mock mode: returns simulated responses for offline development.
    """

    def __init__(self, workspace: str | Path, api_key: str = ""):
        self.workspace = Path(workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self._api_key = api_key or settings.ANTHROPIC_API_KEY
        self._is_mock = not self._api_key or self._api_key == "sk-ant-xxx"

        if not self._is_mock:
            from anthropic import Anthropic

            self._client = Anthropic(api_key=self._api_key)

    # ── Public API ───────────────────────────────────────────────

    async def generate_framework(
        self,
        paper_content: str,
        config: dict,
        max_turns: int = 30,
    ) -> AgentResult:
        """Generate a complete PyTorch code framework from a paper and config."""
        # Handle both string and dict paper_content
        if isinstance(paper_content, dict):
            paper_text = json.dumps(paper_content, indent=2)
        else:
            paper_text = str(paper_content)

        prompt = f"""Generate a complete PyTorch code framework based on the paper and config below.

## Paper Content
{paper_text[:8000]}

## Student's Improvement Targets
{json.dumps(config.get('improvement_targets', []), indent=2)}

## Target Metrics
{json.dumps(config.get('target_metrics', {}), indent=2)}

## Files to Generate
1. data.py — data loading and preprocessing
2. model.py — model definition based on the paper
3. train.py — training loop with TensorBoard logging
4. eval.py — evaluation script
5. config.yaml — hyperparameter configuration
6. requirements.txt — dependency list
7. README.md — usage instructions

## Requirements
- Use type annotations
- Comment key sections
- Use argparse for configurable parameters
- Save checkpoints to ./checkpoints/
- TensorBoard logs to ./runs/
- Support SANDBOX_MODE=true env var to run only 1 batch for validation
- Read batch_size, learning_rate, and device overrides from EXPERIMENT_CONFIG
- After writing each file, run run_check to verify syntax
- Output a summary of all files created and key design decisions."""

        if self._is_mock:
            return self._mock_generate_framework(config)

        return await self._run_agent_loop(prompt, max_turns)

    async def apply_suggestion(
        self,
        suggestion: dict,
        max_turns: int = 20,
    ) -> AgentResult:
        """Apply an improvement suggestion to the code in the workspace."""
        prompt = f"""Apply the following improvement suggestion to the code in the workspace.

## Improvement Suggestion
Method: {suggestion.get('method', '')}
Reason: {suggestion.get('reason', '')}
Expected Improvement: {suggestion.get('expected_improvement', '')}
Code Changes: {json.dumps(suggestion.get('code_changes', {}), indent=2)}

## Instructions
1. Read the relevant files first to understand the current code
2. Use edit_file for precise changes (do NOT rewrite entire files)
3. Run run_check after each change
4. If validation fails, fix the issue
5. Output a summary: which files were modified, what changed, and the result."""

        if self._is_mock:
            return self._mock_apply_suggestion(suggestion)

        return await self._run_agent_loop(prompt, max_turns)

    async def fix_runtime_error(
        self,
        error_log: str,
        max_turns: int = 15,
    ) -> AgentResult:
        """Fix a runtime error in the code."""
        prompt = f"""The code in the workspace encountered a runtime error:

```
{error_log[:5000]}
```

Please:
1. Read the relevant files to understand the context
2. Analyze the root cause of the error
3. Use edit_file to fix the issue
4. Run run_check to verify the fix
5. Output a summary of what was fixed and why."""

        if self._is_mock:
            return self._mock_fix_error(error_log)

        return await self._run_agent_loop(prompt, max_turns)

    # ── Agent Loop ───────────────────────────────────────────────

    async def _run_agent_loop(
        self,
        user_message: str,
        max_turns: int,
    ) -> AgentResult:
        """Run the tool-use agent loop with Anthropic SDK."""
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_message}
        ]
        modified_files: list[str] = []
        errors: list[str] = []

        for iteration in range(max_turns):
            try:
                response = self._client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=8192,
                    system=SYSTEM_PROMPT,
                    tools=TOOLS,
                    messages=messages,
                )
            except Exception as e:  # noqa: BLE001 - external SDK error boundary
                errors.append(str(e))
                return AgentResult(
                    success=False,
                    final_message=f"API call failed: {e}",
                    iterations=iteration,
                    errors=errors,
                )

            if response.stop_reason == "end_turn":
                text = self._extract_text(response)
                return AgentResult(
                    success=True,
                    final_message=text,
                    iterations=iteration + 1,
                    modified_files=modified_files,
                    errors=errors,
                )

            if response.stop_reason == "tool_use":
                # Add assistant message
                messages.append({
                    "role": "assistant",
                    "content": response.content,
                })

                # Execute all tool calls
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = await self._execute_tool(
                            block.name, block.input
                        )
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })
                        if block.name in ("write_file", "edit_file"):
                            path = block.input.get("path", "")
                            if path and path not in modified_files:
                                modified_files.append(path)

                messages.append({"role": "user", "content": tool_results})

        return AgentResult(
            success=False,
            final_message=f"Max turns ({max_turns}) reached without completion",
            iterations=max_turns,
            modified_files=modified_files,
            errors=errors,
        )

    # ── Tool Execution ───────────────────────────────────────────

    async def _execute_tool(self, name: str, input_data: dict) -> str:
        """Execute a tool call and return the result string."""
        try:
            if name == "read_file":
                return self._tool_read(input_data.get("path", ""))
            elif name == "write_file":
                return self._tool_write(
                    input_data.get("path", ""), input_data.get("content", "")
                )
            elif name == "edit_file":
                return self._tool_edit(
                    input_data.get("path", ""),
                    input_data.get("old_string", ""),
                    input_data.get("new_string", ""),
                )
            elif name == "list_files":
                return self._tool_list(input_data.get("directory", "."))
            elif name == "run_check":
                return self._tool_check(input_data.get("path", ""))
        except ValueError as exc:
            return f"Error: {exc}"
        return f"Unknown tool: {name}"

    def _safe_path(self, path: str) -> Path:
        candidate = Path(path)
        resolved = (self.workspace / candidate).resolve()
        if (
            candidate.is_absolute()
            or ".git" in candidate.parts
            or not resolved.is_relative_to(self.workspace)
        ):
            raise ValueError("path must remain within the workspace")
        return resolved

    def _tool_read(self, path: str) -> str:
        p = self._safe_path(path)
        if not p.exists():
            return f"Error: file not found: {path}"
        try:
            return p.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as e:
            return f"Error reading {path}: {e}"

    def _tool_write(self, path: str, content: str) -> str:
        p = self._safe_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"File written: {path} ({len(content)} chars)"

    def _tool_edit(self, path: str, old: str, new: str) -> str:
        p = self._safe_path(path)
        if not p.exists():
            return f"Error: file not found: {path}"
        content = p.read_text(encoding="utf-8")
        if old not in content:
            return f"Error: old_string not found in {path}"
        if content.count(old) > 1:
            return f"Error: old_string appears {content.count(old)} times; provide more context"
        p.write_text(content.replace(old, new), encoding="utf-8")
        return f"File edited: {path}"

    def _tool_list(self, directory: str) -> str:
        p = self._safe_path(directory)
        if not p.exists():
            return "Directory not found"
        files = [str(f.relative_to(self.workspace)) for f in p.rglob("*") if f.is_file()]
        return "\n".join(files[:100])

    def _tool_check(self, path: str) -> str:
        import subprocess

        p = self._safe_path(path)
        if not p.exists():
            return f"File not found: {path}"
        try:
            result = subprocess.run(
                ["ruff", "check", str(p)],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            return result.stdout + result.stderr if result.returncode != 0 else "No lint errors."
        except FileNotFoundError:
            return "ruff not installed; skipping lint check."
        except subprocess.SubprocessError as e:
            return f"Lint check error: {e}"

    def _extract_text(self, response) -> str:
        """Extract text content from an Anthropic response."""
        for block in response.content:
            if block.type == "text":
                return block.text
        return ""

    # ── Mock Mode ────────────────────────────────────────────────

    def _mock_generate_framework(self, config: dict) -> AgentResult:
        """Simulate code generation in mock mode."""
        targets = config.get("improvement_targets", [])
        metrics = config.get("target_metrics", {})

        # Write a minimal framework as a real simulation
        self._write_mock_framework(targets, metrics)

        return AgentResult(
            success=True,
            final_message=(
                f"Generated code framework with 7 files:\n"
                f"- data.py: Data loading pipeline\n"
                f"- model.py: Neural network model\n"
                f"- train.py: Training loop with TensorBoard\n"
                f"- eval.py: Evaluation script\n"
                f"- config.yaml: Hyperparameters\n"
                f"- requirements.txt: Dependencies\n"
                f"- README.md: Usage instructions\n\n"
                f"Improvement targets: {targets}\n"
                f"Target metrics: {metrics}\n"
                f"All files pass ruff lint check."
            ),
            iterations=1,
            modified_files=[
                "data.py", "model.py", "train.py", "eval.py",
                "config.yaml", "requirements.txt", "README.md",
            ],
        )

    def _write_mock_framework(self, targets: list[str], metrics: dict) -> None:
        """Write a minimal mock code framework to the workspace."""
        self._tool_write("data.py", MOCK_DATA_PY)
        self._tool_write("model.py", MOCK_MODEL_PY)
        self._tool_write("train.py", MOCK_TRAIN_PY)
        self._tool_write("eval.py", MOCK_EVAL_PY)
        self._tool_write("config.yaml", MOCK_CONFIG_YAML)
        self._tool_write("requirements.txt", MOCK_REQUIREMENTS_TXT)
        self._tool_write("README.md", MOCK_README_MD)

    def _mock_apply_suggestion(self, suggestion: dict) -> AgentResult:
        return AgentResult(
            success=True,
            final_message=(
                f"Applied improvement: {suggestion.get('method', 'unknown')}\n"
                f"Reason: {suggestion.get('reason', '')}\n"
                f"Modified files: {list(suggestion.get('code_changes', {}).keys())}\n"
                f"Validation: ruff check passed."
            ),
            iterations=1,
            modified_files=list(suggestion.get("code_changes", {}).keys()),
        )

    def _mock_fix_error(self, error_log: str) -> AgentResult:
        return AgentResult(
            success=True,
            final_message=(
                f"Analyzed error and applied fix.\n"
                f"Error: {error_log[:200]}...\n"
                f"Fix: Adjusted code to handle the issue."
            ),
            iterations=1,
            modified_files=["train.py"],
        )


# ── Mock code templates ──────────────────────────────────────────

MOCK_DATA_PY = '''"""Data loading and preprocessing."""
import os
import torch
from torch.utils.data import DataLoader, Dataset


class ResearchDataset(Dataset):
    """Dataset for the research experiment."""

    def __init__(self, data_path: str, train: bool = True):
        self.data_path = data_path
        self.train = train
        # TODO: Load actual data
        self.data = torch.randn(1000, 3, 32, 32)
        self.labels = torch.randint(0, 10, (1000,))

    def __len__(self) -> int:
        return len(self.data)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        return self.data[idx], self.labels[idx]


def get_dataloaders(
    data_path: str,
    batch_size: int = 64,
    num_workers: int = 4,
) -> tuple[DataLoader, DataLoader]:
    """Create train and validation dataloaders."""
    train_dataset = ResearchDataset(data_path, train=True)
    val_dataset = ResearchDataset(data_path, train=False)

    train_loader = DataLoader(
        train_dataset, batch_size=batch_size,
        shuffle=True, num_workers=num_workers,
    )
    val_loader = DataLoader(
        val_dataset, batch_size=batch_size,
        shuffle=False, num_workers=num_workers,
    )
    return train_loader, val_loader
'''

MOCK_MODEL_PY = '''"""Neural network model definition."""
import torch
import torch.nn as nn


class ResearchModel(nn.Module):
    """Model architecture based on the paper."""

    def __init__(self, num_classes: int = 10):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(3, 64, 3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            nn.Conv2d(64, 128, 3, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            nn.Conv2d(128, 256, 3, padding=1),
            nn.BatchNorm2d(256),
            nn.ReLU(inplace=True),
            nn.AdaptiveAvgPool2d((1, 1)),
        )
        self.classifier = nn.Linear(256, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.features(x)
        x = x.view(x.size(0), -1)
        return self.classifier(x)
'''

MOCK_TRAIN_PY = '''"""Training loop with TensorBoard logging."""
import argparse
import json
import os
import torch
import torch.nn as nn
from torch.utils.tensorboard import SummaryWriter
from data import get_dataloaders
from model import ResearchModel


def train_epoch(
    model: nn.Module,
    loader: torch.utils.data.DataLoader,
    optimizer: torch.optim.Optimizer,
    criterion: nn.Module,
    device: torch.device,
) -> float:
    """Train for one epoch, return average loss."""
    model.train()
    total_loss = 0.0
    sandbox_mode = os.getenv("SANDBOX_MODE", "0").lower() in {"1", "true"}
    max_batches = 1 if sandbox_mode else len(loader)

    for batch_idx, (data, target) in enumerate(loader):
        if batch_idx >= max_batches:
            break
        data, target = data.to(device), target.to(device)
        optimizer.zero_grad()
        output = model(data)
        loss = criterion(output, target)
        loss.backward()
        optimizer.step()
        total_loss += loss.item()

    return total_loss / max_batches


def validate(
    model: nn.Module,
    loader: torch.utils.data.DataLoader,
    criterion: nn.Module,
    device: torch.device,
) -> tuple[float, float]:
    """Validate and return (loss, accuracy)."""
    model.eval()
    total_loss = 0.0
    correct = 0
    total = 0
    sandbox_mode = os.getenv("SANDBOX_MODE", "0").lower() in {"1", "true"}
    max_batches = 1 if sandbox_mode else len(loader)

    with torch.no_grad():
        for batch_idx, (data, target) in enumerate(loader):
            if batch_idx >= max_batches:
                break
            data, target = data.to(device), target.to(device)
            output = model(data)
            total_loss += criterion(output, target).item()
            pred = output.argmax(dim=1)
            correct += pred.eq(target).sum().item()
            total += target.size(0)

    return total_loss / max_batches, correct / total


def main():
    runtime_config = json.loads(os.getenv("EXPERIMENT_CONFIG", "{}"))
    training_config = runtime_config.get("training", {})
    if not isinstance(training_config, dict):
        training_config = {}

    def runtime_value(name, default):
        return runtime_config.get(name, training_config.get(name, default))

    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=runtime_value("epochs", 10))
    parser.add_argument(
        "--batch-size", type=int, default=runtime_value("batch_size", 64)
    )
    parser.add_argument(
        "--lr", type=float, default=runtime_value("learning_rate", 0.001)
    )
    parser.add_argument("--data-path", type=str, default="./data")
    args = parser.parse_args()

    requested_device = runtime_value("device", "auto")
    device_name = (
        "cuda"
        if requested_device == "auto" and torch.cuda.is_available()
        else "cpu"
        if requested_device == "auto"
        else requested_device
    )
    device = torch.device(device_name)
    writer = SummaryWriter("./runs")

    train_loader, val_loader = get_dataloaders(args.data_path, args.batch_size)
    model = ResearchModel().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    criterion = nn.CrossEntropyLoss()

    for epoch in range(args.epochs):
        train_loss = train_epoch(model, train_loader, optimizer, criterion, device)
        val_loss, val_acc = validate(model, val_loader, criterion, device)

        writer.add_scalar("Loss/train", train_loss, epoch)
        writer.add_scalar("Loss/val", val_loss, epoch)
        writer.add_scalar("Accuracy/val", val_acc, epoch)

        print(f"Epoch {epoch+1}: train_loss={train_loss:.4f}, "
              f"val_loss={val_loss:.4f}, val_acc={val_acc:.4f}")

    torch.save(model.state_dict(), "./checkpoints/model.pth")
    writer.close()


if __name__ == "__main__":
    main()
'''

MOCK_EVAL_PY = '''"""Evaluation script."""
import argparse
import torch
from data import get_dataloaders
from model import ResearchModel


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=str, default="./checkpoints/model.pth")
    parser.add_argument("--data-path", type=str, default="./data")
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = ResearchModel().to(device)
    model.load_state_dict(torch.load(args.checkpoint, map_location=device))
    model.eval()

    _, val_loader = get_dataloaders(args.data_path, args.batch_size)
    correct = 0
    total = 0

    with torch.no_grad():
        for data, target in val_loader:
            data, target = data.to(device), target.to(device)
            output = model(data)
            pred = output.argmax(dim=1)
            correct += pred.eq(target).sum().item()
            total += target.size(0)

    accuracy = correct / total
    print(f"Accuracy: {accuracy:.4f} ({correct}/{total})")


if __name__ == "__main__":
    main()
'''

MOCK_CONFIG_YAML = """# Experiment Configuration
model:
  name: ResearchModel
  num_classes: 10

training:
  epochs: 10
  batch_size: 64
  learning_rate: 0.001
  optimizer: adam

data:
  path: ./data
  num_workers: 4

checkpoint:
  dir: ./checkpoints
  save_best: true
"""

MOCK_REQUIREMENTS_TXT = """torch>=2.0.0
torchvision>=0.15.0
tensorboard>=2.13.0
numpy>=1.24.0
pyyaml>=6.0
"""

MOCK_README_MD = """# Research Experiment

Auto-generated code framework for paper reproduction.

## Quick Start
```bash
pip install -r requirements.txt
python train.py --epochs 10
```

## Files
- `data.py`: Data loading
- `model.py`: Model architecture
- `train.py`: Training loop
- `eval.py`: Evaluation
- `config.yaml`: Configuration
"""
