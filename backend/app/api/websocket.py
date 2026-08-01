"""Authenticated project-level WebSocket subscriptions."""

from __future__ import annotations

import uuid

from fastapi import (
    APIRouter,
    Depends,
    WebSocket,
    WebSocketDisconnect,
    WebSocketException,
)
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.project import Project
from app.schemas.realtime import ProjectRealtimeEvent
from app.services.realtime import RealtimeEventBroker

router = APIRouter(tags=["realtime"])

WS_UNAUTHORIZED = 4401
WS_FORBIDDEN = 4403
WS_NOT_FOUND = 4404


def get_realtime_broker() -> RealtimeEventBroker:
    return RealtimeEventBroker(settings.REDIS_URL)


def _bearer_subprotocol(websocket: WebSocket) -> str | None:
    protocols = [
        protocol.strip()
        for protocol in websocket.headers.get("sec-websocket-protocol", "").split(",")
        if protocol.strip()
    ]
    try:
        bearer_index = protocols.index("bearer")
        return protocols[bearer_index + 1]
    except (ValueError, IndexError):
        return None


async def authenticate_project_websocket(
    websocket: WebSocket,
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> Project:
    """Authenticate a browser subprotocol token and enforce project ownership."""
    origin = websocket.headers.get("origin")
    if origin and origin not in set(settings.CORS_ORIGINS):
        raise WebSocketException(code=WS_FORBIDDEN, reason="Origin is not allowed")

    token = _bearer_subprotocol(websocket)
    payload = decode_access_token(token) if token else None
    subject = payload.get("sub") if payload else None
    try:
        user_id = uuid.UUID(subject) if subject else None
    except (TypeError, ValueError):
        user_id = None
    if user_id is None:
        raise WebSocketException(
            code=WS_UNAUTHORIZED,
            reason="Invalid or expired token",
        )

    project = await db.get(Project, project_id)
    if project is None:
        raise WebSocketException(code=WS_NOT_FOUND, reason="Project not found")
    if project.user_id != user_id:
        raise WebSocketException(code=WS_NOT_FOUND, reason="Project not found")
    return project


@router.websocket("/ws/projects/{project_id}")
async def project_websocket(
    websocket: WebSocket,
    project: Project = Depends(authenticate_project_websocket),  # noqa: B008
    broker: RealtimeEventBroker = Depends(get_realtime_broker),  # noqa: B008
) -> None:
    """Push project experiment state changes without browser polling."""
    await websocket.accept(subprotocol="bearer")
    try:
        async with broker.subscription(project.id) as events:
            await websocket.send_text(
                ProjectRealtimeEvent(
                    type="connected",
                    project_id=project.id,
                ).model_dump_json()
            )
            async for event in events:
                await websocket.send_text(event.model_dump_json())
    except WebSocketDisconnect:
        pass
    except (OSError, RedisError):
        await websocket.close(code=1011, reason="Realtime transport unavailable")
    finally:
        await broker.close()
