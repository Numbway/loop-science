"""Reusable system configuration profiles owned by the current user."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.credential_profile import CredentialProfile
from app.models.project import Project
from app.models.user import User
from app.schemas.system_config import (
    CredentialProfileResponse,
    LlmProfileRequest,
)
from app.services.credentials import encrypt_credentials
from app.services.ssh import SshConnectionError, SshProbe

router = APIRouter(prefix="/api/system-configs", tags=["system-config"])
MAX_PRIVATE_KEY_BYTES = 128 * 1024


def get_ssh_probe() -> SshProbe:
    return SshProbe()


def _profile_name(value: str) -> str:
    name = value.strip()
    if not name or len(name) > 120:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="配置名称长度应为 1–120 个字符。",
        )
    return name


def _model_name(value: str) -> str:
    model = value.strip()
    if not model:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="模型 ID 不能为空。",
        )
    return model


def _base_url(value: str) -> str:
    base_url = value.strip().rstrip("/")
    parsed = urlsplit(base_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Base URL 必须是完整的 HTTP/HTTPS 地址，"
                "且不能包含账号、查询参数或片段。"
            ),
        )
    return base_url


def _profile_response(profile: CredentialProfile) -> CredentialProfileResponse:
    return CredentialProfileResponse(
        id=profile.id,
        name=profile.name,
        kind=profile.kind,
        public_config=profile.public_config or {},
        verified=profile.verified,
        last_verified_at=profile.last_verified_at,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


async def _owned_profile(
    profile_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> CredentialProfile:
    profile = await db.get(CredentialProfile, profile_id)
    if profile is None or profile.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="配置档案不存在。",
        )
    return profile


async def _commit_profile(
    db: AsyncSession,
    profile: CredentialProfile,
) -> CredentialProfileResponse:
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="同类型配置中已存在相同名称。",
        ) from exc
    await db.refresh(profile)
    return _profile_response(profile)


@router.get("", response_model=list[CredentialProfileResponse])
async def list_system_configs(
    kind: str | None = None,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[CredentialProfileResponse]:
    if kind not in {None, "llm", "ssh"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="配置类型只能是 llm 或 ssh。",
        )
    query = select(CredentialProfile).where(
        CredentialProfile.user_id == current_user.id
    )
    if kind:
        query = query.where(CredentialProfile.kind == kind)
    profiles = (
        await db.scalars(query.order_by(CredentialProfile.created_at.desc()))
    ).all()
    return [_profile_response(profile) for profile in profiles]


@router.post(
    "/llm",
    response_model=CredentialProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_llm_config(
    request: LlmProfileRequest,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> CredentialProfileResponse:
    key = request.api_key.strip()
    model = _model_name(request.model)
    if len(key) < 10:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="请输入有效的大模型 API Key。",
        )
    profile = CredentialProfile(
        user_id=current_user.id,
        name=_profile_name(request.name),
        kind="llm",
        public_config={
            "provider": request.provider,
            "model": model,
            "base_url": _base_url(request.base_url),
            "masked_key": f"{key[:7]}…{key[-4:]}",
        },
        encrypted_credentials=encrypt_credentials({"api_key": key}),
        verified=True,
        last_verified_at=datetime.now(timezone.utc),
    )
    db.add(profile)
    return await _commit_profile(db, profile)


@router.put("/llm/{profile_id}", response_model=CredentialProfileResponse)
async def update_llm_config(
    profile_id: uuid.UUID,
    request: LlmProfileRequest,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> CredentialProfileResponse:
    profile = await _owned_profile(profile_id, current_user, db)
    if profile.kind != "llm":
        raise HTTPException(status_code=409, detail="配置类型不匹配。")
    key = request.api_key.strip()
    model = _model_name(request.model)
    if len(key) < 10:
        raise HTTPException(status_code=422, detail="大模型 API Key 格式无效。")
    profile.name = _profile_name(request.name)
    profile.public_config = {
        "provider": request.provider,
        "model": model,
        "base_url": _base_url(request.base_url),
        "masked_key": f"{key[:7]}…{key[-4:]}",
    }
    profile.encrypted_credentials = encrypt_credentials({"api_key": key})
    profile.verified = True
    profile.last_verified_at = datetime.now(timezone.utc)
    return await _commit_profile(db, profile)


async def _ssh_secret(
    auth_type: str,
    password: str,
    passphrase: str,
    private_key: UploadFile | None,
) -> dict[str, str]:
    if auth_type == "password":
        if not password:
            raise HTTPException(status_code=422, detail="请输入 SSH 登录密码。")
        return {"password": password}
    if auth_type != "key":
        raise HTTPException(status_code=422, detail="SSH 认证方式无效。")
    if private_key is None:
        raise HTTPException(status_code=422, detail="请选择 SSH 私钥文件。")
    content = await private_key.read(MAX_PRIVATE_KEY_BYTES + 1)
    if not content or len(content) > MAX_PRIVATE_KEY_BYTES:
        raise HTTPException(status_code=422, detail="私钥为空或超过 128 KB。")
    try:
        key_text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="私钥必须是 UTF-8 文本。") from exc
    return {"private_key": key_text, "passphrase": passphrase}


async def _save_ssh_profile(
    *,
    profile: CredentialProfile,
    name: str,
    host: str,
    port: int,
    username: str,
    auth_type: str,
    password: str,
    passphrase: str,
    private_key: UploadFile | None,
    probe: SshProbe,
    db: AsyncSession,
) -> CredentialProfileResponse:
    connection = {
        "host": host.strip(),
        "port": port,
        "username": username.strip(),
        "auth_type": auth_type,
    }
    if not connection["host"] or not connection["username"] or not 1 <= port <= 65535:
        raise HTTPException(status_code=422, detail="服务器地址、端口或用户名无效。")
    secret = await _ssh_secret(auth_type, password, passphrase, private_key)
    try:
        result = await probe.test(connection, secret)
    except SshConnectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    profile.name = _profile_name(name)
    profile.public_config = {
        **connection,
        "mode": "ssh",
        "ready": True,
        "host_key_fingerprint": result.host_key_fingerprint,
        "capabilities": result.capabilities,
    }
    profile.encrypted_credentials = encrypt_credentials(secret)
    profile.verified = True
    profile.last_verified_at = datetime.now(timezone.utc)
    return await _commit_profile(db, profile)


@router.post(
    "/ssh",
    response_model=CredentialProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_ssh_config(
    name: str = Form(...),
    host: str = Form(...),
    port: int = Form(22),
    username: str = Form(...),
    auth_type: str = Form(...),
    password: str = Form(""),
    passphrase: str = Form(""),
    private_key: UploadFile | None = File(None),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
    probe: SshProbe = Depends(get_ssh_probe),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> CredentialProfileResponse:
    profile = CredentialProfile(
        user_id=current_user.id,
        name=_profile_name(name),
        kind="ssh",
        public_config={},
        encrypted_credentials="",
        verified=False,
    )
    db.add(profile)
    return await _save_ssh_profile(
        profile=profile,
        name=name,
        host=host,
        port=port,
        username=username,
        auth_type=auth_type,
        password=password,
        passphrase=passphrase,
        private_key=private_key,
        probe=probe,
        db=db,
    )


@router.put("/ssh/{profile_id}", response_model=CredentialProfileResponse)
async def update_ssh_config(
    profile_id: uuid.UUID,
    name: str = Form(...),
    host: str = Form(...),
    port: int = Form(22),
    username: str = Form(...),
    auth_type: str = Form(...),
    password: str = Form(""),
    passphrase: str = Form(""),
    private_key: UploadFile | None = File(None),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
    probe: SshProbe = Depends(get_ssh_probe),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> CredentialProfileResponse:
    profile = await _owned_profile(profile_id, current_user, db)
    if profile.kind != "ssh":
        raise HTTPException(status_code=409, detail="配置类型不匹配。")
    return await _save_ssh_profile(
        profile=profile,
        name=name,
        host=host,
        port=port,
        username=username,
        auth_type=auth_type,
        password=password,
        passphrase=passphrase,
        private_key=private_key,
        probe=probe,
        db=db,
    )


@router.delete("/{profile_id}")
async def delete_system_config(
    profile_id: uuid.UUID,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> dict[str, bool]:
    profile = await _owned_profile(profile_id, current_user, db)
    references = await db.scalar(
        select(func.count(Project.id)).where(
            or_(
                Project.ai_credential_profile_id == profile.id,
                Project.ssh_credential_profile_id == profile.id,
            )
        )
    )
    if references:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"仍有 {references} 个项目使用该配置，不能删除。",
        )
    await db.delete(profile)
    await db.commit()
    return {"deleted": True}
