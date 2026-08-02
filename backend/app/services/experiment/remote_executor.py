"""SSH-backed experiment execution on a verified training server."""

from __future__ import annotations

import asyncio
import json
import posixpath
import shlex
import stat
import uuid
from collections.abc import AsyncIterator
from pathlib import Path, PurePosixPath
from typing import Any

from app.services.experiment.executor import (
    ExperimentExecutorError,
    ExperimentResult,
)
from app.services.ssh import open_ssh_client


class RemoteExperimentExecutor:
    """Upload reviewed code and run it against selected server-side data."""

    def __init__(
        self,
        storage_root: Path | str,
        connection: dict[str, Any],
        secret: dict[str, Any],
        data_path: Path | str,
    ) -> None:
        self._storage_root = Path(storage_root).resolve()
        self._connection = connection
        self._secret = secret
        self._data_path = str(data_path)

    def _local_output(self, experiment_id: uuid.UUID) -> Path:
        output = self._storage_root / "experiment_runs" / str(experiment_id)
        output.mkdir(parents=True, exist_ok=True)
        return output

    @staticmethod
    def _mkdirs(sftp: Any, path: str) -> None:
        current = "/"
        for part in PurePosixPath(path).parts:
            if part == "/":
                continue
            current = posixpath.join(current, part)
            try:
                sftp.stat(current)
            except OSError:
                sftp.mkdir(current)

    @classmethod
    def _upload_tree(cls, sftp: Any, local: Path, remote: str) -> None:
        cls._mkdirs(sftp, remote)
        for item in local.rglob("*"):
            relative = item.relative_to(local).as_posix()
            target = posixpath.join(remote, relative)
            if item.is_dir():
                cls._mkdirs(sftp, target)
            elif item.is_file():
                cls._mkdirs(sftp, posixpath.dirname(target))
                sftp.put(str(item), target)

    def _connect(self) -> Any:
        return open_ssh_client(self._connection, self._secret)

    @staticmethod
    def _remote_root(sftp: Any, experiment_id: uuid.UUID) -> str:
        home = sftp.normalize(".")
        return posixpath.join(home, ".loop-science", "runs", str(experiment_id))

    async def run_experiment(
        self,
        experiment_id: uuid.UUID,
        code_path: Path | str,
        config: dict[str, Any],
    ) -> ExperimentResult:
        return await asyncio.to_thread(
            self._run_sync,
            experiment_id,
            Path(code_path).resolve(),
            config,
        )

    def _run_sync(
        self,
        experiment_id: uuid.UUID,
        code_directory: Path,
        config: dict[str, Any],
    ) -> ExperimentResult:
        if not code_directory.is_dir() or not code_directory.is_relative_to(
            self._storage_root
        ):
            raise ExperimentExecutorError(
                "Experiment code must be a directory within storage."
            )
        data_candidate = PurePosixPath(self._data_path)
        if (
            not data_candidate.is_absolute()
            or "\x00" in self._data_path
            or "\n" in self._data_path
            or "\r" in self._data_path
        ):
            raise ExperimentExecutorError(
                "Experiment data must be an absolute path selected on the "
                "remote server."
            )
        client = self._connect()
        try:
            sftp = client.open_sftp()
            try:
                selected_attributes = sftp.stat(self._data_path)
            except OSError as exc:
                raise ExperimentExecutorError(
                    "The selected remote data path is no longer available."
                ) from exc
            if not (
                stat.S_ISDIR(selected_attributes.st_mode)
                or stat.S_ISREG(selected_attributes.st_mode)
            ):
                raise ExperimentExecutorError(
                    "The selected remote data path is not a file or directory."
                )
            root = self._remote_root(sftp, experiment_id)
            code_remote = posixpath.join(root, "code")
            output_remote = posixpath.join(root, "output")
            self._mkdirs(sftp, output_remote)
            self._upload_tree(sftp, code_directory, code_remote)
            data_input = self._data_path
            runtime_config = dict(config)
            runtime_config["data_path"] = data_input
            entrypoint = str(runtime_config.get("entrypoint") or "train.py")
            if (
                PurePosixPath(entrypoint).is_absolute()
                or ".." in PurePosixPath(entrypoint).parts
            ):
                raise ExperimentExecutorError(
                    "Remote entrypoint must remain in the code directory."
                )
            entrypoint_remote = posixpath.join(code_remote, entrypoint)
            raw_arguments = runtime_config.get("arguments") or []
            if not isinstance(raw_arguments, list) or any(
                not isinstance(argument, str) for argument in raw_arguments
            ):
                raise ExperimentExecutorError(
                    "Remote launch arguments must be a list of strings."
                )
            arguments = [
                argument.replace("{data_path}", data_input)
                for argument in raw_arguments
            ]
            argument_command = "".join(
                f" {shlex.quote(argument)}" for argument in arguments
            )
            venv_remote = posixpath.join(root, ".venv")
            python_remote = posixpath.join(venv_remote, "bin", "python")
            pip_remote = posixpath.join(venv_remote, "bin", "pip")
            requirements_remote = posixpath.join(code_remote, "requirements.txt")
            launch_script = "\n".join(
                (
                    "#!/bin/sh",
                    f"cd {shlex.quote(output_remote)}",
                    (
                        f"test -x {shlex.quote(python_remote)} || "
                        f"python3 -m venv --system-site-packages "
                        f"{shlex.quote(venv_remote)}"
                    ),
                    (
                        f"if test -f {shlex.quote(requirements_remote)}; then "
                        f"{shlex.quote(pip_remote)} install "
                        f"--disable-pip-version-check -r "
                        f"{shlex.quote(requirements_remote)}; fi"
                    ),
                    f"export PYTHONPATH={shlex.quote(code_remote)}",
                    f"export DATA_PATH={shlex.quote(data_input)}",
                    "export EXPERIMENT_CONFIG="
                    + shlex.quote(json.dumps(runtime_config, ensure_ascii=False)),
                    (
                        f"{shlex.quote(python_remote)} "
                        f"{shlex.quote(entrypoint_remote)}{argument_command}"
                    ),
                    "status=$?",
                    'printf "%s" "$status" > exit_code',
                    "exit \"$status\"",
                )
            )
            launch_path = posixpath.join(root, "launch.sh")
            with sftp.file(launch_path, "wb") as handle:
                handle.write(launch_script.encode("utf-8"))
            sftp.chmod(launch_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
            log_path = posixpath.join(output_remote, "train.log")
            command = (
                f"nohup sh {shlex.quote(launch_path)} > "
                f"{shlex.quote(log_path)} 2>&1 < /dev/null & echo $!"
            )
            _, stdout, stderr = client.exec_command(command, timeout=15)
            pid = stdout.read().decode("utf-8", errors="replace").strip()
            error = stderr.read().decode("utf-8", errors="replace").strip()
            if not pid.isdigit():
                raise ExperimentExecutorError(
                    f"Remote process did not start: {error or pid or 'unknown error'}"
                )
            with sftp.file(posixpath.join(root, "pid"), "wb") as handle:
                handle.write(pid.encode("ascii"))
        finally:
            client.close()
        return ExperimentResult(
            experiment_id=experiment_id,
            container_id=f"ssh:{self._connection['host']}:{pid}",
            status="running",
            output_path=self._local_output(experiment_id),
        )

    async def stream_logs(self, experiment_id: uuid.UUID) -> AsyncIterator[str]:
        client = await asyncio.to_thread(self._connect)
        sftp = await asyncio.to_thread(client.open_sftp)
        root = self._remote_root(sftp, experiment_id)
        log_path = posixpath.join(root, "output", "train.log")
        exit_path = posixpath.join(root, "output", "exit_code")
        offset = 0
        remainder = ""
        try:
            while True:
                chunk = await asyncio.to_thread(
                    self._read_from,
                    sftp,
                    log_path,
                    offset,
                )
                offset += len(chunk)
                text = remainder + chunk.decode("utf-8", errors="replace")
                lines = text.splitlines(keepends=True)
                remainder = ""
                if lines and not lines[-1].endswith(("\n", "\r")):
                    remainder = lines.pop()
                for line in lines:
                    yield line.rstrip("\r\n")
                if await asyncio.to_thread(self._exists, sftp, exit_path):
                    final_chunk = await asyncio.to_thread(
                        self._read_from,
                        sftp,
                        log_path,
                        offset,
                    )
                    if final_chunk:
                        remainder += final_chunk.decode(
                            "utf-8", errors="replace"
                        )
                    if remainder:
                        yield remainder.rstrip("\r\n")
                    break
                await asyncio.sleep(1)
            await asyncio.to_thread(
                self._download_tree,
                sftp,
                posixpath.join(root, "output"),
                self._local_output(experiment_id),
            )
        finally:
            await asyncio.to_thread(client.close)

    @staticmethod
    def _read_from(sftp: Any, path: str, offset: int) -> bytes:
        try:
            with sftp.file(path, "rb") as handle:
                handle.seek(offset)
                return handle.read()
        except OSError:
            return b""

    @staticmethod
    def _exists(sftp: Any, path: str) -> bool:
        try:
            sftp.stat(path)
            return True
        except OSError:
            return False

    @classmethod
    def _download_tree(cls, sftp: Any, remote: str, local: Path) -> None:
        local.mkdir(parents=True, exist_ok=True)
        for item in sftp.listdir_attr(remote):
            remote_item = posixpath.join(remote, item.filename)
            local_item = local / item.filename
            if stat.S_ISDIR(item.st_mode):
                cls._download_tree(sftp, remote_item, local_item)
            elif stat.S_ISREG(item.st_mode):
                sftp.get(remote_item, str(local_item))

    async def get_status(self, experiment_id: uuid.UUID) -> str:
        exit_code = await self.get_exit_code(experiment_id)
        return "exited" if exit_code is not None else "running"

    async def get_exit_code(self, experiment_id: uuid.UUID) -> int | None:
        return await asyncio.to_thread(self._get_exit_code_sync, experiment_id)

    def _get_exit_code_sync(self, experiment_id: uuid.UUID) -> int | None:
        client = self._connect()
        try:
            sftp = client.open_sftp()
            path = posixpath.join(
                self._remote_root(sftp, experiment_id),
                "output",
                "exit_code",
            )
            try:
                with sftp.file(path, "r") as handle:
                    return int(handle.read().decode("ascii").strip())
            except OSError:
                return None
        finally:
            client.close()

    async def stop(self, experiment_id: uuid.UUID) -> None:
        await asyncio.to_thread(self._signal, experiment_id, False)

    async def cleanup(self, experiment_id: uuid.UUID) -> None:
        await asyncio.to_thread(self._signal, experiment_id, True)

    def _signal(self, experiment_id: uuid.UUID, remove: bool) -> None:
        client = self._connect()
        try:
            sftp = client.open_sftp()
            root = self._remote_root(sftp, experiment_id)
            pid_path = posixpath.join(root, "pid")
            try:
                with sftp.file(pid_path, "r") as handle:
                    pid = handle.read().decode("ascii").strip()
            except OSError:
                pid = ""
            if pid.isdigit():
                client.exec_command(f"kill {pid} 2>/dev/null || true", timeout=10)
            if remove:
                # Root is deterministically scoped to this experiment UUID.
                client.exec_command(
                    f"rm -rf -- {shlex.quote(root)}",
                    timeout=30,
                )
        finally:
            client.close()
