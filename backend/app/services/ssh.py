"""SSH authentication, capability probing, and reusable connections."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import posixpath
import stat
from dataclasses import dataclass
from io import StringIO
from pathlib import Path, PurePosixPath
from typing import Any


class SshConnectionError(RuntimeError):
    """Raised when an SSH target cannot be authenticated or inspected."""


@dataclass(frozen=True)
class SshProbeResult:
    host_key_fingerprint: str
    capabilities: dict[str, str | bool]


@dataclass(frozen=True)
class RemoteDataEntry:
    name: str
    path: str
    kind: str
    size: int


@dataclass(frozen=True)
class RemoteDataListing:
    current_path: str
    parent_path: str | None
    entries: list[RemoteDataEntry]
    truncated: bool


@dataclass(frozen=True)
class RemoteDataSelection:
    path: str
    kind: str
    selected_name: str
    file_count: int
    total_bytes: int


@dataclass(frozen=True)
class RemoteCodeImport:
    remote_path: str
    selected_name: str
    entrypoint: str
    file_count: int
    total_bytes: int
    skipped_count: int


def host_key_fingerprint(server_key: Any) -> str:
    """Return the OpenSSH-style SHA-256 fingerprint for a host key."""
    return "SHA256:" + base64.b64encode(
        hashlib.sha256(server_key.asbytes()).digest()
    ).decode("ascii").rstrip("=")


def load_private_key(private_key: str, passphrase: str = "") -> Any:
    """Parse common OpenSSH/PEM private-key formats."""
    import paramiko

    errors: list[str] = []
    for key_class in (
        paramiko.Ed25519Key,
        paramiko.RSAKey,
        paramiko.ECDSAKey,
    ):
        try:
            return key_class.from_private_key(
                StringIO(private_key),
                password=passphrase or None,
            )
        except Exception as exc:  # noqa: BLE001 - key format probing
            errors.append(type(exc).__name__)
    raise SshConnectionError(
        "Private key could not be parsed. Use an OpenSSH or PEM private key."
    )


def open_ssh_client(config: dict[str, Any], secret: dict[str, Any]) -> Any:
    """Open an authenticated Paramiko client from safe and secret settings."""
    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    connect_args: dict[str, Any] = {
        "hostname": config["host"],
        "port": int(config.get("port", 22)),
        "username": config["username"],
        "timeout": 12,
        "banner_timeout": 12,
        "auth_timeout": 12,
        "allow_agent": False,
        "look_for_keys": False,
    }
    if config.get("auth_type") == "key":
        connect_args["pkey"] = load_private_key(
            str(secret.get("private_key", "")),
            str(secret.get("passphrase", "")),
        )
    else:
        connect_args["password"] = str(secret.get("password", ""))
    try:
        client.connect(**connect_args)
        expected_fingerprint = str(
            config.get("host_key_fingerprint") or ""
        )
        if expected_fingerprint:
            actual_fingerprint = host_key_fingerprint(
                client.get_transport().get_remote_server_key()
            )
            if actual_fingerprint != expected_fingerprint:
                raise SshConnectionError(
                    "SSH host key changed since verification; connection refused."
                )
    except SshConnectionError:
        client.close()
        raise
    except Exception as exc:  # noqa: BLE001 - network/auth boundary
        client.close()
        raise SshConnectionError(
            f"SSH connection failed: {type(exc).__name__}: {exc}"
        ) from exc
    return client


class SshProbe:
    """Authenticate and inspect the minimum remote training capabilities."""

    async def test(
        self,
        config: dict[str, Any],
        secret: dict[str, Any],
    ) -> SshProbeResult:
        return await asyncio.to_thread(self._test_sync, config, secret)

    def _test_sync(
        self,
        config: dict[str, Any],
        secret: dict[str, Any],
    ) -> SshProbeResult:
        client = open_ssh_client(config, secret)
        try:
            server_key = client.get_transport().get_remote_server_key()
            fingerprint = host_key_fingerprint(server_key)
            python_version = self._run(client, "python3 --version 2>&1")
            if not python_version.lower().startswith("python "):
                raise SshConnectionError(
                    "SSH authentication succeeded, but python3 is unavailable "
                    "on the server."
                )
            capabilities = {
                "os": self._run(client, "uname -sr"),
                "python": python_version,
                "gpu": self._run(
                    client,
                    "nvidia-smi --query-gpu=name,memory.total "
                    "--format=csv,noheader 2>/dev/null || true",
                )
                or "未检测到 NVIDIA GPU",
                "torch": self._run(
                    client,
                    "python3 -c \"import torch; "
                    "print(torch.__version__, torch.cuda.is_available())\" "
                    "2>/dev/null || true",
                )
                or "未安装",
            }
            capabilities["python_ready"] = True
            return SshProbeResult(fingerprint, capabilities)
        finally:
            client.close()

    @staticmethod
    def _run(client: Any, command: str) -> str:
        _, stdout, stderr = client.exec_command(command, timeout=15)
        output = stdout.read().decode("utf-8", errors="replace").strip()
        error = stderr.read().decode("utf-8", errors="replace").strip()
        return output or error


class SshDataBrowser:
    """Browse and validate data already present on a verified SSH server."""

    max_entries = 500

    async def list_directory(
        self,
        config: dict[str, Any],
        secret: dict[str, Any],
        path: str = "",
    ) -> RemoteDataListing:
        return await asyncio.to_thread(
            self._list_directory_sync,
            config,
            secret,
            path,
        )

    async def select(
        self,
        config: dict[str, Any],
        secret: dict[str, Any],
        path: str,
        kind: str,
    ) -> RemoteDataSelection:
        return await asyncio.to_thread(
            self._select_sync,
            config,
            secret,
            path,
            kind,
        )

    def _list_directory_sync(
        self,
        config: dict[str, Any],
        secret: dict[str, Any],
        path: str,
    ) -> RemoteDataListing:
        client = open_ssh_client(config, secret)
        try:
            sftp = client.open_sftp()
            current = self._normalize(sftp, path or ".")
            attributes = sftp.listdir_attr(current)
            entries = [
                RemoteDataEntry(
                    name=item.filename,
                    path=posixpath.join(current, item.filename),
                    kind=(
                        "folder"
                        if stat.S_ISDIR(item.st_mode)
                        else "file"
                    ),
                    size=int(item.st_size or 0),
                )
                for item in attributes
                if stat.S_ISDIR(item.st_mode) or stat.S_ISREG(item.st_mode)
            ]
            entries.sort(key=lambda item: (item.kind != "folder", item.name.lower()))
            parent = (
                None
                if current == "/"
                else posixpath.dirname(current.rstrip("/")) or "/"
            )
            return RemoteDataListing(
                current_path=current,
                parent_path=parent,
                entries=entries[: self.max_entries],
                truncated=len(entries) > self.max_entries,
            )
        except SshConnectionError:
            raise
        except Exception as exc:  # noqa: BLE001 - SFTP boundary
            raise SshConnectionError(
                f"Remote data directory could not be opened: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        finally:
            client.close()

    def _select_sync(
        self,
        config: dict[str, Any],
        secret: dict[str, Any],
        path: str,
        kind: str,
    ) -> RemoteDataSelection:
        if kind not in {"file", "folder"}:
            raise SshConnectionError("Remote data must be a file or folder.")
        client = open_ssh_client(config, secret)
        try:
            sftp = client.open_sftp()
            selected = self._normalize(sftp, path)
            attributes = sftp.stat(selected)
            actual_kind = (
                "folder"
                if stat.S_ISDIR(attributes.st_mode)
                else "file"
                if stat.S_ISREG(attributes.st_mode)
                else "other"
            )
            if actual_kind != kind:
                raise SshConnectionError(
                    f"The selected remote path is not a {kind}."
                )
            if kind == "file":
                file_count = 1
                total_bytes = int(attributes.st_size or 0)
            else:
                children = sftp.listdir_attr(selected)
                files = [
                    item for item in children if stat.S_ISREG(item.st_mode)
                ]
                file_count = len(files)
                total_bytes = sum(int(item.st_size or 0) for item in files)
            return RemoteDataSelection(
                path=selected,
                kind=kind,
                selected_name=posixpath.basename(selected.rstrip("/")) or "/",
                file_count=file_count,
                total_bytes=total_bytes,
            )
        except SshConnectionError:
            raise
        except Exception as exc:  # noqa: BLE001 - SFTP boundary
            raise SshConnectionError(
                f"Remote data path could not be selected: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        finally:
            client.close()

    @staticmethod
    def _normalize(sftp: Any, path: str) -> str:
        if not path or "\x00" in path or "\n" in path or "\r" in path:
            raise SshConnectionError("Remote data path is invalid.")
        return str(sftp.normalize(path))


class SshCodeImporter:
    """Download a bounded, secret-filtered code snapshot over SFTP."""

    max_files = 5_000
    max_bytes = 250 * 1024 * 1024
    ignored_directories = {
        ".git",
        ".hg",
        ".svn",
        ".ssh",
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",
    }
    ignored_files = {
        ".env",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "id_rsa",
    }
    ignored_suffixes = {".key", ".pem", ".p12", ".pfx"}

    async def import_directory(
        self,
        config: dict[str, Any],
        secret: dict[str, Any],
        remote_path: str,
        entrypoint: str,
        destination: Path,
    ) -> RemoteCodeImport:
        return await asyncio.to_thread(
            self._import_directory_sync,
            config,
            secret,
            remote_path,
            entrypoint,
            destination,
        )

    def _import_directory_sync(
        self,
        config: dict[str, Any],
        secret: dict[str, Any],
        remote_path: str,
        entrypoint: str,
        destination: Path,
    ) -> RemoteCodeImport:
        normalized_entrypoint = self._entrypoint(entrypoint)
        destination = destination.resolve()
        destination.mkdir(parents=True, exist_ok=True)
        client = open_ssh_client(config, secret)
        try:
            sftp = client.open_sftp()
            root = SshDataBrowser._normalize(sftp, remote_path)
            attributes = sftp.stat(root)
            if not stat.S_ISDIR(attributes.st_mode):
                raise SshConnectionError(
                    "The selected remote code path must be a folder."
                )
            file_count = 0
            total_bytes = 0
            skipped_count = 0
            pending = [(root, PurePosixPath("."))]
            while pending:
                remote_directory, relative_directory = pending.pop()
                for item in sftp.listdir_attr(remote_directory):
                    name = str(item.filename)
                    if self._invalid_name(name):
                        skipped_count += 1
                        continue
                    relative = relative_directory / name
                    remote_item = posixpath.join(remote_directory, name)
                    if stat.S_ISDIR(item.st_mode):
                        if name in self.ignored_directories:
                            skipped_count += 1
                            continue
                        pending.append((remote_item, relative))
                        continue
                    if not stat.S_ISREG(item.st_mode) or self._ignore_file(name):
                        skipped_count += 1
                        continue
                    size = int(item.st_size or 0)
                    file_count += 1
                    total_bytes += size
                    if file_count > self.max_files or total_bytes > self.max_bytes:
                        raise SshConnectionError(
                            "Remote code exceeds the import limit of 5,000 files "
                            "or 250 MB."
                        )
                    local_item = (destination / Path(*relative.parts)).resolve()
                    if not local_item.is_relative_to(destination):
                        raise SshConnectionError(
                            "A remote code path escaped the import workspace."
                        )
                    local_item.parent.mkdir(parents=True, exist_ok=True)
                    sftp.get(remote_item, str(local_item))
            if file_count == 0:
                raise SshConnectionError(
                    "The selected remote code folder has no importable files."
                )
            local_entrypoint = (
                destination / Path(*normalized_entrypoint.parts)
            ).resolve()
            if (
                not local_entrypoint.is_relative_to(destination)
                or not local_entrypoint.is_file()
            ):
                raise SshConnectionError(
                    "The entrypoint was not found in the imported code folder."
                )
            return RemoteCodeImport(
                remote_path=root,
                selected_name=posixpath.basename(root.rstrip("/")) or "/",
                entrypoint=normalized_entrypoint.as_posix(),
                file_count=file_count,
                total_bytes=total_bytes,
                skipped_count=skipped_count,
            )
        except SshConnectionError:
            raise
        except Exception as exc:  # noqa: BLE001 - SFTP boundary
            raise SshConnectionError(
                f"Remote code could not be imported: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        finally:
            client.close()

    @staticmethod
    def _entrypoint(value: str) -> PurePosixPath:
        candidate = PurePosixPath(value.strip().replace("\\", "/"))
        if (
            not value.strip()
            or candidate.is_absolute()
            or ".." in candidate.parts
            or "\x00" in value
            or "\n" in value
            or "\r" in value
        ):
            raise SshConnectionError(
                "The entrypoint must be a relative file inside the code folder."
            )
        return candidate

    @staticmethod
    def _invalid_name(value: str) -> bool:
        return (
            value in {"", ".", ".."}
            or "/" in value
            or "\\" in value
            or "\x00" in value
            or "\n" in value
            or "\r" in value
        )

    def _ignore_file(self, name: str) -> bool:
        lower = name.lower()
        return (
            lower in self.ignored_files
            or lower.startswith(".env.")
            or Path(lower).suffix in self.ignored_suffixes
        )
