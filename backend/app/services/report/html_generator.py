"""Generate self-contained HTML evidence reports for experiments."""

from __future__ import annotations

import math
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from app.models.experiment import Experiment
from app.models.project import Project
from app.models.reference_paper import ReferencePaper
from app.services.git import BranchDiff, GitService
from app.services.git.exceptions import GitServiceError

_PERCENT_METRICS = ("acc", "precision", "recall", "f1", "auc")
_LOWER_BETTER_METRICS = ("loss", "error", "perplexity", "latency", "time")
_STATUS_LABELS = {
    "pending": "等待执行",
    "running": "运行中",
    "completed": "已完成",
    "failed": "失败",
}


class HTMLReportGenerator:
    """Render one experiment as a portable, self-contained HTML file."""

    def __init__(
        self,
        storage_root: Path | str,
        *,
        git_service: GitService | None = None,
        template_directory: Path | None = None,
    ) -> None:
        self._storage_root = Path(storage_root).resolve()
        self._git_service = git_service or GitService(self._storage_root)
        templates = template_directory or Path(__file__).parent / "templates"
        self._environment = Environment(
            loader=FileSystemLoader(templates),
            autoescape=select_autoescape(("html", "xml", "j2")),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._environment.filters.update(
            format_datetime=self._format_datetime,
            format_duration=self._format_duration,
            format_metric=self._format_metric,
        )

    async def generate(
        self,
        experiment: Experiment,
        project: Project,
        parent_experiment: Experiment | None,
        reference_papers: list[ReferencePaper],
    ) -> str:
        """Generate all seven report sections and return the private file path."""
        generated_at = datetime.now(timezone.utc)
        metric_rows = self._metric_rows(experiment, parent_experiment, project)
        primary_metric = self._primary_metric(metric_rows)
        code_diff = self._code_diff(experiment, project, parent_experiment)
        charts = self._metric_charts(experiment)
        safe_references = [
            {
                "title": paper.title,
                "authors": paper.authors or [],
                "year": paper.year,
                "url": self._safe_url(paper.url),
                "key_contributions": paper.key_contributions or [],
            }
            for paper in reference_papers
        ]
        context = {
            "generated_at": generated_at,
            "experiment": experiment,
            "project": project,
            "parent": parent_experiment,
            "status_label": _STATUS_LABELS.get(experiment.status, experiment.status),
            "metric_rows": metric_rows,
            "primary_metric": primary_metric,
            "verdict": self._verdict(experiment, primary_metric),
            "charts": charts,
            "code_diff": code_diff,
            "references": safe_references,
            "next_steps": self._next_steps(experiment, project, metric_rows),
            "paper_authors": (project.paper_metadata or {}).get("authors", []),
        }
        html = self._environment.get_template("experiment_report.html.j2").render(
            **context
        )
        report_path = self.report_path(experiment.id)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = report_path.with_name(f".report-{uuid.uuid4().hex}.tmp")
        temporary_path.write_text(html, encoding="utf-8")
        temporary_path.replace(report_path)
        return str(report_path)

    def report_path(self, experiment_id: uuid.UUID) -> Path:
        """Return the canonical private report path for one experiment."""
        report_path = (
            self._storage_root
            / "experiment_reports"
            / str(experiment_id)
            / "report.html"
        ).resolve()
        if not report_path.is_relative_to(self._storage_root):
            raise ValueError("Report path must remain inside storage.")
        return report_path

    def _code_diff(
        self,
        experiment: Experiment,
        project: Project,
        parent: Experiment | None,
    ) -> dict[str, Any]:
        base_branch = parent.git_branch if parent else "main"
        try:
            diff: BranchDiff = self._git_service.compare_branches(
                project.id,
                base_branch,
                experiment.git_branch,
                max_patch_characters=80_000,
            )
            return {
                "available": True,
                "base_branch": diff.base_branch,
                "target_branch": diff.target_branch,
                "files": diff.files,
                "patch": diff.patch,
                "insertions": diff.insertions,
                "deletions": diff.deletions,
                "truncated": diff.truncated,
                "reason": None,
            }
        except GitServiceError as error:
            return {
                "available": False,
                "base_branch": base_branch,
                "target_branch": experiment.git_branch,
                "files": [],
                "patch": "",
                "insertions": 0,
                "deletions": 0,
                "truncated": False,
                "reason": error.message,
            }

    def _metric_rows(
        self,
        experiment: Experiment,
        parent: Experiment | None,
        project: Project,
    ) -> list[dict[str, Any]]:
        current_metrics = self._finite_metrics(experiment.metrics or {})
        parent_metrics = self._finite_metrics(parent.metrics or {}) if parent else {}
        target_metrics = self._finite_metrics(project.target_metrics or {})
        names = sorted(set(current_metrics) | set(parent_metrics) | set(target_metrics))
        rows = []
        for name in names:
            current = current_metrics.get(name)
            parent_value = parent_metrics.get(name)
            delta = (
                current - parent_value
                if current is not None and parent_value is not None
                else None
            )
            rows.append(
                {
                    "name": name,
                    "current": current,
                    "parent": parent_value,
                    "delta": delta,
                    "delta_display": self._format_signed_delta(name, delta),
                    "target": target_metrics.get(name),
                    "improved": self._is_improved(name, delta),
                    "target_met": self._target_met(
                        name, current, target_metrics.get(name)
                    ),
                }
            )
        return rows

    def _metric_charts(self, experiment: Experiment) -> list[dict[str, Any]]:
        histories = self._tensorboard_histories(experiment.id)
        if not histories:
            histories = {
                name: [(0, value)]
                for name, value in self._finite_metrics(
                    experiment.metrics or {}
                ).items()
            }

        preferred = sorted(
            histories,
            key=lambda name: (
                0
                if any(
                    token in name.lower()
                    for token in ("validation/accuracy", "val_accuracy", "accuracy")
                )
                else 1
                if "loss" in name.lower()
                else 2,
                name,
            ),
        )[:4]
        charts = []
        for name in preferred:
            values = histories[name]
            if len(values) > 160:
                stride = math.ceil(len(values) / 160)
                values = values[::stride]
                if values[-1] != histories[name][-1]:
                    values.append(histories[name][-1])
            numeric_values = [value for _, value in values]
            minimum = min(numeric_values)
            maximum = max(numeric_values)
            span = maximum - minimum
            points = []
            for index, (_step, value) in enumerate(values):
                x = 0 if len(values) == 1 else index / (len(values) - 1) * 100
                y = 50 if span == 0 else 92 - ((value - minimum) / span * 84)
                points.append(f"{x:.2f},{y:.2f}")
            charts.append(
                {
                    "name": name,
                    "points": " ".join(points),
                    "point_count": len(values),
                    "latest": numeric_values[-1],
                    "minimum": minimum,
                    "maximum": maximum,
                    "first_step": values[0][0],
                    "last_step": values[-1][0],
                    "improves_down": self._is_lower_better(name),
                }
            )
        return charts

    def _tensorboard_histories(
        self, experiment_id: uuid.UUID
    ) -> dict[str, list[tuple[int, float]]]:
        try:
            from tensorboard.backend.event_processing.event_accumulator import (
                EventAccumulator,
            )
            from tensorboard.compat.tensorflow_stub.errors import DataLossError
        except ImportError:
            return {}

        run_directory = (
            self._storage_root / "experiment_runs" / str(experiment_id)
        ).resolve()
        if not run_directory.is_relative_to(self._storage_root):
            return {}
        event_files = (
            sorted(run_directory.rglob("events.out.tfevents.*"))
            if run_directory.is_dir()
            else []
        )
        histories: dict[str, dict[int, tuple[float, float]]] = defaultdict(dict)
        for event_file in event_files:
            try:
                accumulator = EventAccumulator(
                    str(event_file), size_guidance={"scalars": 0}
                )
                accumulator.Reload()
                for tag in accumulator.Tags().get("scalars", []):
                    for event in accumulator.Scalars(tag):
                        value = float(event.value)
                        if not math.isfinite(value):
                            continue
                        current = histories[tag].get(int(event.step))
                        if current is None or event.wall_time >= current[0]:
                            histories[tag][int(event.step)] = (
                                float(event.wall_time),
                                value,
                            )
            except (DataLossError, OSError, ValueError):
                continue
        return {
            tag: [
                (step, timestamp_and_value[1])
                for step, timestamp_and_value in sorted(events.items())
            ]
            for tag, events in histories.items()
            if events
        }

    def _primary_metric(self, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        return next(
            (
                row
                for row in rows
                if row["current"] is not None
                and any(
                    token in row["name"].lower()
                    for token in ("accuracy", "acc", "f1", "auc")
                )
            ),
            next((row for row in rows if row["current"] is not None), None),
        )

    def _verdict(
        self,
        experiment: Experiment,
        primary_metric: dict[str, Any] | None,
    ) -> str:
        if experiment.status == "failed":
            return "本轮实验未形成有效结论，需先处理运行失败证据。"
        if experiment.status == "running":
            return "本报告为运行中快照，最终结论仍待训练完成。"
        if experiment.status == "pending":
            return "实验尚未开始，本报告记录当前方案与待验证目标。"
        if primary_metric is None:
            return "实验已完成，但尚未记录可比较的结果指标。"
        if primary_metric["delta"] is None:
            return (
                f"实验已完成，建立 {primary_metric['name']} "
                f"{self._format_metric(primary_metric['current'], primary_metric['name'])} 基线。"
            )
        direction = "改善" if primary_metric["improved"] else "回退"
        return (
            f"实验已完成，{primary_metric['name']} 相对父节点"
            f"{direction} {self._format_delta(primary_metric)}。"
        )

    def _next_steps(
        self,
        experiment: Experiment,
        project: Project,
        rows: list[dict[str, Any]],
    ) -> list[str]:
        if experiment.status == "failed":
            return [
                "先根据错误日志和 AI 诊断定位失败原因，再复用相同配置重跑。",
                "修复时只改变一个故障变量，避免把恢复效果与算法改进混在一起。",
            ]
        unmet = [
            row
            for row in rows
            if row["current"] is not None
            and row["target"] is not None
            and not row["target_met"]
        ]
        suggestions = []
        if unmet:
            names = "、".join(row["name"] for row in unmet[:3])
            suggestions.append(f"下一轮优先缩小 {names} 与目标值之间的差距。")
        elif any(row["target_met"] for row in rows):
            suggestions.append("当前目标已达到，下一轮应验证不同随机种子下的稳定性。")
        else:
            suggestions.append("为核心指标补充明确目标值，再判断是否继续扩展方案。")
        if project.improvement_targets:
            suggestions.append(
                f"从既定方向“{project.improvement_targets[0]}”中选择一个变量进行消融。"
            )
        else:
            suggestions.append("从本轮诊断中选择单一变量建立子分支，保持其余配置不变。")
        suggestions.append("保留当前分支和报告作为证据基线，并记录下一轮停止条件。")
        return suggestions

    @staticmethod
    def _finite_metrics(metrics: dict[str, Any]) -> dict[str, float]:
        result = {}
        for name, raw_value in metrics.items():
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(value):
                result[str(name)] = value
        return result

    @staticmethod
    def _is_percent(name: str) -> bool:
        normalized = name.lower()
        return any(token in normalized for token in _PERCENT_METRICS)

    @staticmethod
    def _is_lower_better(name: str) -> bool:
        normalized = name.lower()
        return any(token in normalized for token in _LOWER_BETTER_METRICS)

    @classmethod
    def _is_improved(cls, name: str, delta: float | None) -> bool | None:
        if delta is None:
            return None
        return delta <= 0 if cls._is_lower_better(name) else delta >= 0

    @classmethod
    def _target_met(
        cls, name: str, current: float | None, target: float | None
    ) -> bool | None:
        if current is None or target is None:
            return None
        return current <= target if cls._is_lower_better(name) else current >= target

    @classmethod
    def _format_metric(cls, value: float | None, name: str = "") -> str:
        if value is None:
            return "—"
        if cls._is_percent(name):
            normalized = value * 100 if abs(value) <= 1 else value
            return f"{normalized:.2f}%"
        return f"{value:.4f}"

    @classmethod
    def _format_delta(cls, row: dict[str, Any]) -> str:
        delta = row["delta"]
        if delta is None:
            return "—"
        if cls._is_percent(row["name"]):
            return f"{abs(delta * 100):.2f} pp"
        return f"{abs(delta):.4f}"

    @classmethod
    def _format_signed_delta(cls, name: str, delta: float | None) -> str:
        if delta is None:
            return "—"
        if cls._is_percent(name):
            return f"{delta * 100:+.2f} pp"
        return f"{delta:+.4f}"

    @staticmethod
    def _format_datetime(value: datetime | None) -> str:
        if value is None:
            return "—"
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    @staticmethod
    def _format_duration(seconds: int | None) -> str:
        if seconds is None:
            return "—"
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        parts = [f"{hours} 小时" if hours else "", f"{minutes} 分" if minutes else ""]
        parts.append(f"{seconds} 秒")
        return " ".join(part for part in parts if part)

    @staticmethod
    def _safe_url(value: str | None) -> str | None:
        if not value:
            return None
        parsed = urlparse(value)
        return value if parsed.scheme in {"http", "https"} and parsed.netloc else None
