"""Safe Docker-backed execution for a checked-out experiment directory."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ExperimentExecutorError(Exception):
    """Raised when an experiment cannot be safely managed."""


@dataclass(frozen=True)
class ExperimentResult:
    experiment_id: uuid.UUID
    container_id: str
    status: str
    output_path: Path


class ExperimentExecutor:
    """Manage one isolated Docker container for each experiment.

    The source directory is always mounted read-only.  Containers have no network
    access and write artifacts only into a per-experiment output directory.
    """

    def __init__(
        self,
        storage_root: Path | str,
        image: str = "loop-science-executor:latest",
        client: Any | None = None,
        sandbox_mode: bool = False,
    ) -> None:
        self._storage_root = Path(storage_root).resolve()
        self._image = image
        self._client = client
        self._sandbox_mode = sandbox_mode

    def _docker_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import docker
        except ImportError as exc:  # pragma: no cover - deployment dependency
            raise ExperimentExecutorError("Docker SDK is not installed.") from exc
        self._client = docker.from_env()
        return self._client

    def _paths(self, experiment_id: uuid.UUID, code_path: Path | str) -> tuple[Path, Path]:
        code_directory = Path(code_path).resolve()
        if not code_directory.is_dir() or not code_directory.is_relative_to(self._storage_root):
            raise ExperimentExecutorError("Experiment code must be a directory within storage.")
        output_directory = self._storage_root / "experiment_runs" / str(experiment_id)
        output_directory.mkdir(parents=True, exist_ok=True)
        return code_directory, output_directory

    async def run_experiment(
        self,
        experiment_id: uuid.UUID,
        code_path: Path | str,
        config: dict[str, Any],
    ) -> ExperimentResult:
        code_directory, output_directory = self._paths(experiment_id, code_path)
        config_path = output_directory / "config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        container = await asyncio.to_thread(
            self._docker_client().containers.run,
            self._image,
            command="python /workspace/runner.py --config /workspace/output/config.json",
            name=f"rc-experiment-{experiment_id}",
            detach=True,
            network_disabled=True,
            read_only=True,
            volumes={
                str(code_directory): {"bind": "/workspace/code", "mode": "ro"},
                str(output_directory): {"bind": "/workspace/output", "mode": "rw"},
            },
            environment={"SANDBOX_MODE": "1" if self._sandbox_mode else "0"},
        )
        return ExperimentResult(experiment_id, container.id, container.status, output_directory)

    async def get_status(self, experiment_id: uuid.UUID) -> str:
        container = await asyncio.to_thread(
            self._docker_client().containers.get, f"rc-experiment-{experiment_id}"
        )
        await asyncio.to_thread(container.reload)
        return str(container.status)

    async def stream_logs(self, experiment_id: uuid.UUID) -> AsyncIterator[str]:
        container = await asyncio.to_thread(
            self._docker_client().containers.get, f"rc-experiment-{experiment_id}"
        )
        log_lines = container.logs(stream=True, follow=True)
        while True:
            line = await asyncio.to_thread(next, log_lines, None)
            if line is None:
                break
            yield line.decode("utf-8", errors="replace").rstrip()

    async def stop(self, experiment_id: uuid.UUID) -> None:
        container = await asyncio.to_thread(
            self._docker_client().containers.get, f"rc-experiment-{experiment_id}"
        )
        await asyncio.to_thread(container.stop)

    async def cleanup(self, experiment_id: uuid.UUID) -> None:
        container = await asyncio.to_thread(
            self._docker_client().containers.get, f"rc-experiment-{experiment_id}"
        )
        await asyncio.to_thread(container.remove, force=False)
