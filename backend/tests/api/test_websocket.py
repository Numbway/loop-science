from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.websocket import get_realtime_broker
from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models.project import Project
from app.schemas.realtime import ProjectRealtimeEvent


class FakeSession:
    def __init__(self, project) -> None:
        self.project = project

    async def get(self, model, _identifier):
        return self.project if model is Project else None


class FakeBroker:
    def __init__(self, event) -> None:
        self.event = event
        self.closed = False

    @asynccontextmanager
    async def subscription(self, _project_id):
        async def events():
            yield self.event

        yield events()

    async def close(self):
        self.closed = True


def test_project_websocket_authenticates_and_streams_typed_events() -> None:
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    experiment_id = uuid.uuid4()
    project = SimpleNamespace(id=project_id, user_id=user_id)
    event = ProjectRealtimeEvent(
        type="experiment_started",
        project_id=project_id,
        experiment_id=experiment_id,
        status="running",
    )
    broker = FakeBroker(event)
    token = create_access_token({"sub": str(user_id)})
    app.dependency_overrides[get_db] = lambda: FakeSession(project)
    app.dependency_overrides[get_realtime_broker] = lambda: broker

    try:
        with TestClient(app).websocket_connect(
            f"/ws/projects/{project_id}",
            subprotocols=["bearer", token],
            headers={"origin": "http://localhost:3000"},
        ) as websocket:
            connected = websocket.receive_json()
            streamed = websocket.receive_json()
            accepted_subprotocol = websocket.accepted_subprotocol
    finally:
        app.dependency_overrides.clear()

    assert accepted_subprotocol == "bearer"
    assert connected["type"] == "connected"
    assert connected["project_id"] == str(project_id)
    assert streamed["type"] == "experiment_started"
    assert streamed["experiment_id"] == str(experiment_id)
    assert broker.closed is True


def test_project_websocket_rejects_invalid_token_before_accepting() -> None:
    project_id = uuid.uuid4()
    project = SimpleNamespace(id=project_id, user_id=uuid.uuid4())
    app.dependency_overrides[get_db] = lambda: FakeSession(project)

    try:
        with (
            pytest.raises(WebSocketDisconnect) as caught,
            TestClient(app).websocket_connect(
                f"/ws/projects/{project_id}",
                subprotocols=["bearer", "invalid-token"],
                headers={"origin": "http://localhost:3000"},
            ),
        ):
            pass
    finally:
        app.dependency_overrides.clear()

    assert caught.value.code == 4401
