from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.project_wizard import (
    _preparation_status,
    browse_project_remote_data,
    import_project_remote_code,
    select_project_remote_data,
)
from app.models.credential_profile import CredentialProfile
from app.schemas.project_wizard import (
    RemoteCodeImportRequest,
    RemoteDataSelectionRequest,
)
from app.services.credentials import encrypt_credentials
from app.services.ssh import (
    RemoteDataEntry,
    RemoteDataListing,
    RemoteDataSelection,
    RemoteCodeImport,
)


class FakeSession:
    def __init__(self, profiles=None) -> None:
        self.commits = 0
        self.profiles = {profile.id: profile for profile in profiles or []}

    async def commit(self) -> None:
        self.commits += 1

    async def get(self, model, identifier):
        if model is CredentialProfile:
            return self.profiles.get(identifier)
        return None


def make_project() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        status="created",
        repo_path="",
        user_id=uuid.uuid4(),
        ai_credential_profile_id=None,
        ssh_credential_profile_id=None,
        paper_analysis={},
        preparation_config={},
        encrypted_credentials="",
    )


@pytest.mark.asyncio
async def test_remote_data_is_browsed_and_selected_through_project_ssh_profile(
) -> None:
    project = make_project()
    now = datetime.now(timezone.utc)
    ssh = CredentialProfile(
        id=uuid.uuid4(),
        user_id=project.user_id,
        name="A100 data server",
        kind="ssh",
        public_config={
            "host": "gpu.example.edu",
            "port": 22,
            "username": "researcher",
            "auth_type": "password",
            "host_key_fingerprint": "SHA256:test",
        },
        encrypted_credentials=encrypt_credentials({"password": "secret"}),
        verified=True,
        created_at=now,
        updated_at=now,
    )
    project.ssh_credential_profile_id = ssh.id
    db = FakeSession([ssh])

    class FakeBrowser:
        async def list_directory(self, config, secret, path):
            assert config["host"] == "gpu.example.edu"
            assert secret == {"password": "secret"}
            assert path == ""
            return RemoteDataListing(
                current_path="/home/researcher",
                parent_path="/home",
                entries=[
                    RemoteDataEntry(
                        name="prepared",
                        path="/home/researcher/prepared",
                        kind="folder",
                        size=0,
                    )
                ],
                truncated=False,
            )

        async def select(self, config, secret, path, kind):
            assert config["host"] == "gpu.example.edu"
            assert secret == {"password": "secret"}
            assert path == "/home/researcher/prepared"
            assert kind == "folder"
            return RemoteDataSelection(
                path=path,
                kind=kind,
                selected_name="prepared",
                file_count=3,
                total_bytes=4096,
            )

    listing = await browse_project_remote_data(
        path="",
        project=project,
        browser=FakeBrowser(),
        db=db,
    )
    assert listing.entries[0].path == "/home/researcher/prepared"

    selected = await select_project_remote_data(
        request=RemoteDataSelectionRequest(
            path="/home/researcher/prepared",
            kind="folder",
        ),
        project=project,
        browser=FakeBrowser(),
        db=db,
    )
    assert selected.ready is True
    assert selected.source == "remote"
    assert selected.path == "/home/researcher/prepared"
    assert project.preparation_config["data"]["ssh_profile_id"] == str(ssh.id)
    assert "storage_path" not in project.preparation_config["data"]

    project.ssh_credential_profile_id = None
    with pytest.raises(HTTPException) as exc_info:
        await browse_project_remote_data(
            path="",
            project=project,
            browser=FakeBrowser(),
            db=db,
        )
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_start_gate_requires_analysis_data_execution_and_reviewed_code(
    tmp_path,
) -> None:
    project = make_project()
    project.paper_analysis = {"summary": "Analyzed"}
    project.preparation_config = {
        "ai": {"configured": True},
        "data": {
            "ready": True,
            "source": "remote",
            "kind": "folder",
            "selected_name": "dataset",
            "remote_path": "/srv/data/dataset",
            "file_count": 2,
            "total_bytes": 10,
        },
        "execution": {
            "ready": True,
            "mode": "ssh",
            "host": "gpu.example.edu",
            "port": 22,
            "username": "researcher",
            "auth_type": "key",
            "host_key_fingerprint": "SHA256:server-key",
            "capabilities": {},
        },
    }
    now = datetime.now(timezone.utc)
    llm = CredentialProfile(
        id=uuid.uuid4(),
        user_id=project.user_id,
        name="Test LLM",
        kind="llm",
        public_config={"provider": "anthropic", "model": "test"},
        encrypted_credentials=encrypt_credentials(
            {"api_key": "sk-ant-api03-test"}
        ),
        verified=True,
        created_at=now,
        updated_at=now,
    )
    ssh = CredentialProfile(
        id=uuid.uuid4(),
        user_id=project.user_id,
        name="Test SSH",
        kind="ssh",
        public_config=project.preparation_config["execution"],
        encrypted_credentials=encrypt_credentials({"password": "test"}),
        verified=True,
        created_at=now,
        updated_at=now,
    )
    project.ai_credential_profile_id = llm.id
    project.ssh_credential_profile_id = ssh.id
    project.preparation_config["data"]["ssh_profile_id"] = str(ssh.id)
    db = FakeSession([llm, ssh])
    readiness = await _preparation_status(project, db)
    assert readiness.ready_to_generate is True
    assert readiness.ready_to_start is False
    assert "生成并审核实验代码" in readiness.missing

    project.repo_path = str(tmp_path / "git_repo")
    assert (await _preparation_status(project, db)).ready_to_start is True


@pytest.mark.asyncio
async def test_existing_assets_workflow_imports_code_and_skips_paper_gates(
    tmp_path,
) -> None:
    project = make_project()
    project.preparation_config = {
        "workflow": "existing_assets",
    }
    now = datetime.now(timezone.utc)
    ssh = CredentialProfile(
        id=uuid.uuid4(),
        user_id=project.user_id,
        name="Existing assets server",
        kind="ssh",
        public_config={
            "ready": True,
            "host": "gpu.example.edu",
            "port": 22,
            "username": "researcher",
            "auth_type": "password",
            "host_key_fingerprint": "SHA256:test",
            "capabilities": {"python": "Python 3.11"},
        },
        encrypted_credentials=encrypt_credentials({"password": "secret"}),
        verified=True,
        created_at=now,
        updated_at=now,
    )
    project.ssh_credential_profile_id = ssh.id
    project.preparation_config["data"] = {
        "ready": True,
        "source": "remote",
        "kind": "folder",
        "selected_name": "dataset",
        "remote_path": "/srv/data/dataset",
        "file_count": 10,
        "total_bytes": 4096,
        "ssh_profile_id": str(ssh.id),
    }
    db = FakeSession([ssh])

    class FakeImporter:
        async def import_directory(
            self,
            config,
            secret,
            remote_path,
            entrypoint,
            destination,
        ):
            assert config["host"] == "gpu.example.edu"
            assert secret == {"password": "secret"}
            assert remote_path == "/srv/code/baseline"
            assert entrypoint == "src/train.py"
            source = destination / "src"
            source.mkdir()
            (source / "train.py").write_text("print('training')\n")
            return RemoteCodeImport(
                remote_path=remote_path,
                selected_name="baseline",
                entrypoint=entrypoint,
                file_count=1,
                total_bytes=18,
                skipped_count=2,
            )

    imported = await import_project_remote_code(
        request=RemoteCodeImportRequest(
            path="/srv/code/baseline",
            entrypoint="src/train.py",
            arguments="--data-path {data_path} --epochs 4",
        ),
        project=project,
        importer=FakeImporter(),
        storage_root=tmp_path,
        db=db,
    )
    readiness = await _preparation_status(project, db)

    assert imported.entrypoint == "src/train.py"
    assert imported.arguments == [
        "--data-path",
        "{data_path}",
        "--epochs",
        "4",
    ]
    assert imported.skipped_count == 2
    assert readiness.workflow == "existing_assets"
    assert readiness.api_key_ready is True
    assert readiness.paper_analysis_ready is True
    assert readiness.ready_to_generate is False
    assert readiness.ready_to_start is True
    assert (tmp_path / str(project.id) / "git_repo" / "src" / "train.py").is_file()
