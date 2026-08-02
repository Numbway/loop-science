"""Redis Pub/Sub transport for project realtime events."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.schemas.realtime import ProjectRealtimeEvent


class RealtimeEventBroker:
    """Publish and subscribe to project events across API and Celery processes."""

    CHANNEL_PREFIX = "research-companion:project:"

    def __init__(
        self,
        redis_url: str,
        *,
        redis_client: Any | None = None,
    ) -> None:
        self._redis_url = redis_url
        self._redis = redis_client
        self._owns_client = redis_client is None
        self._publish_disabled = False

    @classmethod
    def channel(cls, project_id: uuid.UUID) -> str:
        return f"{cls.CHANNEL_PREFIX}{project_id}"

    def _client(self) -> Any:
        if self._redis is None:
            self._redis = Redis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=1.0,
                socket_timeout=2.0,
                health_check_interval=20,
            )
        return self._redis

    async def publish(self, event: ProjectRealtimeEvent) -> int:
        """Publish best-effort without letting Redis availability fail a task."""
        if self._publish_disabled:
            return 0
        try:
            subscribers = await self._client().publish(
                self.channel(event.project_id),
                event.model_dump_json(),
            )
        except (OSError, RedisError):
            self._publish_disabled = True
            return 0
        return int(subscribers)

    async def iter_events(
        self,
        project_id: uuid.UUID,
        *,
        heartbeat_seconds: float = 15.0,
    ) -> AsyncIterator[ProjectRealtimeEvent]:
        """Convenience iterator that owns its Redis subscription."""
        async with self.subscription(
            project_id,
            heartbeat_seconds=heartbeat_seconds,
        ) as events:
            async for event in events:
                yield event

    @asynccontextmanager
    async def subscription(
        self,
        project_id: uuid.UUID,
        *,
        heartbeat_seconds: float = 15.0,
    ) -> AsyncIterator[AsyncIterator[ProjectRealtimeEvent]]:
        """Open the Redis subscription before exposing its event iterator."""
        pubsub = self._client().pubsub()
        await pubsub.subscribe(self.channel(project_id))
        try:
            yield self._subscribed_events(
                pubsub,
                project_id,
                heartbeat_seconds=heartbeat_seconds,
            )
        finally:
            try:
                await pubsub.unsubscribe(self.channel(project_id))
            finally:
                await pubsub.aclose()

    async def _subscribed_events(
        self,
        pubsub: Any,
        project_id: uuid.UUID,
        *,
        heartbeat_seconds: float,
    ) -> AsyncIterator[ProjectRealtimeEvent]:
        loop = asyncio.get_running_loop()
        next_heartbeat = loop.time() + heartbeat_seconds
        while True:
            timeout = max(0.0, next_heartbeat - loop.time())
            message = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=timeout,
            )
            if message is None:
                if loop.time() < next_heartbeat:
                    await asyncio.sleep(min(0.01, timeout))
                    continue
                yield ProjectRealtimeEvent(
                    type="heartbeat",
                    project_id=project_id,
                )
                next_heartbeat = loop.time() + heartbeat_seconds
                continue
            raw_event = message.get("data")
            if isinstance(raw_event, bytes):
                raw_event = raw_event.decode("utf-8", errors="replace")
            if not isinstance(raw_event, str):
                continue
            try:
                event = ProjectRealtimeEvent.model_validate_json(raw_event)
            except ValidationError:
                continue
            if event.project_id == project_id:
                yield event
                next_heartbeat = loop.time() + heartbeat_seconds

    async def close(self) -> None:
        if self._owns_client and self._redis is not None:
            await self._redis.aclose()
            self._redis = None


async def publish_project_event(event: ProjectRealtimeEvent) -> int:
    """Publish one short-lived event from an API request or Celery task."""
    broker = RealtimeEventBroker(settings.REDIS_URL)
    try:
        return await broker.publish(event)
    finally:
        await broker.close()
