import uuid

from app.tasks import experiment_tasks
from app.tasks.experiment_tasks import (
    iterate_experiment_loop_task,
    run_experiment_task,
    should_continue,
)


def test_should_continue_stops_for_paused_limit_or_target() -> None:
    assert not should_continue(project_status="paused", completed_iterations=0, max_iterations=3, target_metrics={}, latest_metrics={})
    assert not should_continue(project_status="running", completed_iterations=3, max_iterations=3, target_metrics={}, latest_metrics={})
    assert not should_continue(project_status="running", completed_iterations=1, max_iterations=3, target_metrics={"accuracy": 0.9}, latest_metrics={"accuracy": 0.9})


def test_should_continue_allows_an_unmet_target() -> None:
    assert should_continue(project_status="running", completed_iterations=1, max_iterations=3, target_metrics={"accuracy": 0.9}, latest_metrics={"accuracy": 0.8})


def test_run_task_bridges_to_async_executor(monkeypatch) -> None:
    experiment_id = uuid.uuid4()

    async def fake_start(value):
        return {"experiment_id": str(value), "status": "running"}

    monkeypatch.setattr(experiment_tasks, "_start_experiment", fake_start)
    result = run_experiment_task.apply(args=[str(experiment_id)]).get()

    assert result == {"experiment_id": str(experiment_id), "status": "running"}


def test_iterate_task_queues_next_experiment(monkeypatch) -> None:
    project_id = uuid.uuid4()
    experiment_id = uuid.uuid4()
    queued = []

    async def fake_next(_project_id):
        return str(experiment_id)

    monkeypatch.setattr(experiment_tasks, "_next_experiment_id", fake_next)
    monkeypatch.setattr(run_experiment_task, "delay", queued.append)
    result = iterate_experiment_loop_task.apply(args=[str(project_id)]).get()

    assert queued == [str(experiment_id)]
    assert result["status"] == "queued"
