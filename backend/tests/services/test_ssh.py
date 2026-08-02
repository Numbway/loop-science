from __future__ import annotations

import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import ssh
from app.services.ssh import SshCodeImporter, SshDataBrowser


class FakeSftp:
    def normalize(self, path: str) -> str:
        return "/home/researcher" if path == "." else path

    def listdir_attr(self, path: str):
        assert path == "/home/researcher"
        return [
            SimpleNamespace(
                filename="dataset.csv",
                st_mode=stat.S_IFREG,
                st_size=128,
            ),
            SimpleNamespace(
                filename="prepared",
                st_mode=stat.S_IFDIR,
                st_size=0,
            ),
            SimpleNamespace(
                filename="dataset-link",
                st_mode=stat.S_IFLNK,
                st_size=0,
            ),
        ]

    def stat(self, path: str):
        if path == "/home/researcher/dataset.csv":
            return SimpleNamespace(st_mode=stat.S_IFREG, st_size=128)
        raise OSError(path)


class FakeClient:
    def __init__(self) -> None:
        self.sftp = FakeSftp()
        self.closed = False

    def open_sftp(self) -> FakeSftp:
        return self.sftp

    def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_ssh_data_browser_lists_and_validates_remote_files(
    monkeypatch,
) -> None:
    clients: list[FakeClient] = []

    def open_client(_config, _secret):
        client = FakeClient()
        clients.append(client)
        return client

    monkeypatch.setattr(ssh, "open_ssh_client", open_client)
    browser = SshDataBrowser()

    listing = await browser.list_directory({}, {}, "")
    selected = await browser.select(
        {},
        {},
        "/home/researcher/dataset.csv",
        "file",
    )

    assert listing.current_path == "/home/researcher"
    assert listing.parent_path == "/home"
    assert [(entry.name, entry.kind) for entry in listing.entries] == [
        ("prepared", "folder"),
        ("dataset.csv", "file"),
    ]
    assert selected.path == "/home/researcher/dataset.csv"
    assert selected.file_count == 1
    assert selected.total_bytes == 128
    assert all(client.closed for client in clients)


class ImportSftp:
    def normalize(self, path: str) -> str:
        return path

    def stat(self, path: str):
        assert path == "/srv/code/baseline"
        return SimpleNamespace(st_mode=stat.S_IFDIR, st_size=0)

    def listdir_attr(self, path: str):
        if path == "/srv/code/baseline":
            return [
                SimpleNamespace(
                    filename="train.py",
                    st_mode=stat.S_IFREG,
                    st_size=16,
                ),
                SimpleNamespace(
                    filename="src",
                    st_mode=stat.S_IFDIR,
                    st_size=0,
                ),
                SimpleNamespace(
                    filename=".env",
                    st_mode=stat.S_IFREG,
                    st_size=20,
                ),
                SimpleNamespace(
                    filename=".venv",
                    st_mode=stat.S_IFDIR,
                    st_size=0,
                ),
            ]
        if path == "/srv/code/baseline/src":
            return [
                SimpleNamespace(
                    filename="model.py",
                    st_mode=stat.S_IFREG,
                    st_size=14,
                )
            ]
        raise OSError(path)

    def get(self, remote: str, local: str) -> None:
        content = (
            "print('train')\n"
            if remote.endswith("train.py")
            else "class Model:\n    pass\n"
        )
        Path(local).write_text(content)


class ImportClient:
    def __init__(self) -> None:
        self.sftp = ImportSftp()
        self.closed = False

    def open_sftp(self) -> ImportSftp:
        return self.sftp

    def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_ssh_code_importer_filters_secrets_and_dependency_directories(
    monkeypatch,
    tmp_path,
) -> None:
    client = ImportClient()
    monkeypatch.setattr(ssh, "open_ssh_client", lambda *_args: client)

    imported = await SshCodeImporter().import_directory(
        {},
        {},
        "/srv/code/baseline",
        "train.py",
        tmp_path,
    )

    assert imported.file_count == 2
    assert imported.skipped_count == 2
    assert imported.entrypoint == "train.py"
    assert (tmp_path / "train.py").is_file()
    assert (tmp_path / "src" / "model.py").is_file()
    assert not (tmp_path / ".env").exists()
    assert not (tmp_path / ".venv").exists()
    assert client.closed is True
