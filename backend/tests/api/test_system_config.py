from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.api.project_wizard import select_project_configurations
from app.api.system_config import create_llm_config
from app.models.credential_profile import CredentialProfile
from app.schemas.system_config import (
    LlmProfileRequest,
    ProjectProfileSelectionRequest,
)
from app.services.credentials import decrypt_credentials


class FakeSession:
    def __init__(self, profiles: list[CredentialProfile] | None = None) -> None:
        self.profiles = {profile.id: profile for profile in profiles or []}
        self.commits = 0

    def add(self, value) -> None:
        now = datetime.now(timezone.utc)
        value.id = value.id or uuid.uuid4()
        value.created_at = value.created_at or now
        value.updated_at = value.updated_at or now
        self.profiles[value.id] = value

    async def get(self, model, identifier):
        if model is CredentialProfile:
            return self.profiles.get(identifier)
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        return None

    async def refresh(self, _value) -> None:
        return None


@pytest.mark.asyncio
async def test_llm_profile_is_user_scoped_and_encrypted() -> None:
    user = SimpleNamespace(id=uuid.uuid4())
    db = FakeSession()
    raw_key = "sk-ant-api03-system-profile-secret"

    response = await create_llm_config(
        request=LlmProfileRequest(
            name="实验室模型网关",
            api_key=raw_key,
            provider="openai_compatible",
            model="research-model-v2",
            base_url="https://models.example.edu/v1/",
        ),
        current_user=user,
        db=db,
    )

    saved = db.profiles[response.id]
    assert saved.user_id == user.id
    assert raw_key not in saved.encrypted_credentials
    assert decrypt_credentials(saved.encrypted_credentials)["api_key"] == raw_key
    assert response.public_config["masked_key"].endswith("cret")
    assert response.public_config["provider"] == "openai_compatible"
    assert response.public_config["model"] == "research-model-v2"
    assert response.public_config["base_url"] == "https://models.example.edu/v1"


@pytest.mark.asyncio
async def test_project_selects_profiles_by_reference_without_secret_copy() -> None:
    user_id = uuid.uuid4()
    llm = CredentialProfile(
        id=uuid.uuid4(),
        user_id=user_id,
        name="Claude 主配置",
        kind="llm",
        public_config={
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "base_url": "https://api.anthropic.com",
            "masked_key": "sk-ant-…cret",
        },
        encrypted_credentials="encrypted-llm",
        verified=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    ssh = CredentialProfile(
        id=uuid.uuid4(),
        user_id=user_id,
        name="A100 节点",
        kind="ssh",
        public_config={
            "mode": "ssh",
            "ready": True,
            "host": "gpu.example.edu",
            "port": 22,
            "username": "researcher",
            "auth_type": "key",
            "host_key_fingerprint": "SHA256:test",
            "capabilities": {},
        },
        encrypted_credentials="encrypted-ssh",
        verified=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    project = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        ai_credential_profile_id=None,
        ssh_credential_profile_id=None,
        preparation_config={},
        encrypted_credentials="",
        paper_analysis={},
        repo_path="",
    )
    db = FakeSession([llm, ssh])

    await select_project_configurations(
        request=ProjectProfileSelectionRequest(ai_profile_id=llm.id),
        project=project,
        db=db,
    )
    response = await select_project_configurations(
        request=ProjectProfileSelectionRequest(ssh_profile_id=ssh.id),
        project=project,
        db=db,
    )

    assert project.ai_credential_profile_id == llm.id
    assert project.ssh_credential_profile_id == ssh.id
    assert project.encrypted_credentials == ""
    assert response.ai_profile_id == llm.id
    assert response.ssh_profile_id == ssh.id
