from __future__ import annotations

import uuid

import pytest
from redis.exceptions import ConnectionError

from app.schemas.realtime import ProjectRealtimeEvent
from app.services.realtime import RealtimeEventBroker


class FakePubSub:
    def __init__(self, messages) -> None:
        self.messages = list(messages)
        self.subscribed = []
        self.unsubscribed = []
        self.closed = False

    async def subscribe(self, channel):
        self.subscribed.append(channel)

    async def get_message(self, **_kwargs):
        return self.messages.pop(0) if self.messages else None

    async def unsubscribe(self, channel):
        self.unsubscribed.append(channel)

    async def aclose(self):
        self.closed = True


class FakeRedis:
    def __init__(self, messages=()) -> None:
        self.pubsub_instance = FakePubSub(messages)
        self.published = []

    async def publish(self, channel, payload):
        self.published.append((channel, payload))
        return 2

    def pubsub(self):
        return self.pubsub_instance


@pytest.mark.asyncio
async def test_broker_publishes_and_subscribes_to_isolated_project_channel() -> None:
    project_id = uuid.uuid4()
    event = ProjectRealtimeEvent(
        type="experiment_started",
        project_id=project_id,
        experiment_id=uuid.uuid4(),
        status="running",
    )
    fake_redis = FakeRedis(
        [
            {"data": "not-json"},
            {
                "data": ProjectRealtimeEvent(
                    type="heartbeat",
                    project_id=uuid.uuid4(),
                ).model_dump_json()
            },
            {"data": event.model_dump_json()},
        ]
    )
    broker = RealtimeEventBroker("redis://unused", redis_client=fake_redis)

    subscribers = await broker.publish(event)
    subscription = broker.iter_events(project_id, heartbeat_seconds=0.01)
    received = await anext(subscription)
    await subscription.aclose()

    channel = RealtimeEventBroker.channel(project_id)
    assert subscribers == 2
    assert fake_redis.published[0][0] == channel
    assert received == event
    assert fake_redis.pubsub_instance.subscribed == [channel]
    assert fake_redis.pubsub_instance.unsubscribed == [channel]
    assert fake_redis.pubsub_instance.closed is True


@pytest.mark.asyncio
async def test_broker_heartbeats_and_disables_repeated_failed_publishes() -> None:
    project_id = uuid.uuid4()

    class FailingRedis(FakeRedis):
        async def publish(self, _channel, _payload):
            self.published.append("attempt")
            raise ConnectionError("offline")

    fake_redis = FailingRedis()
    broker = RealtimeEventBroker("redis://unused", redis_client=fake_redis)
    event = ProjectRealtimeEvent(type="heartbeat", project_id=project_id)

    assert await broker.publish(event) == 0
    assert await broker.publish(event) == 0
    subscription = broker.iter_events(project_id, heartbeat_seconds=0.01)
    heartbeat = await anext(subscription)
    await subscription.aclose()

    assert fake_redis.published == ["attempt"]
    assert heartbeat.type == "heartbeat"
    assert heartbeat.project_id == project_id
