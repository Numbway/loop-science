"""Celery application configuration."""

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "loop_science",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.experiment_tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
)
