import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.models.experiment import Experiment
from app.schemas.ai import AgentResult
from app.services.experiment import AutoErrorHandler, ExperimentResult, MonitorResult
from app.services.git.service import CommitInfo
from app.tasks import experiment_tasks
from app.tasks.experiment_tasks import (
    iterate_experiment_loop_task,
    monitor_experiment_task,
    run_experiment_task,
    should_continue,
)


class FakeStartSession:
    def __init__(self, experiment, project) -> None:
        self.experiment = experiment
        self.project = project

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def get(self, model, _value):
        return self.experiment if model is Experiment else self.project

    async def commit(self) -> None:
        return None


def test_should_continue_stops_for_paused_limit_or_target() -> None:
    assert not should_continue(
        project_status="paused",
        completed_iterations=0,
        max_iterations=3,
        target_metrics={},
        latest_metrics={},
    )
    assert not should_continue(
        project_status="running",
        completed_iterations=3,
        max_iterations=3,
        target_metrics={},
        latest_metrics={},
    )
    assert not should_continue(
        project_status="running",
        completed_iterations=1,
        max_iterations=3,
        target_metrics={"accuracy": 0.9},
        latest_metrics={"accuracy": 0.9},
    )


def test_should_continue_allows_an_unmet_target() -> None:
    assert should_continue(
        project_status="running",
        completed_iterations=1,
        max_iterations=3,
        target_metrics={"accuracy": 0.9},
        latest_metrics={"accuracy": 0.8},
    )


def test_run_task_bridges_to_async_executor(monkeypatch) -> None:
    experiment_id = uuid.uuid4()

    async def fake_start(value):
        return {"experiment_id": str(value), "status": "running"}

    monkeypatch.setattr(experiment_tasks, "_start_experiment", fake_start)
    result = run_experiment_task.apply(args=[str(experiment_id)]).get()

    assert result == {"experiment_id": str(experiment_id), "status": "running"}


@pytest.mark.asyncio
async def test_start_experiment_queues_monitor_after_container_launch(
    monkeypatch, tmp_path
) -> None:
    experiment_id = uuid.uuid4()
    project_id = uuid.uuid4()
    experiment = type(
        "PendingExperiment",
        (),
        {
            "id": experiment_id,
            "project_id": project_id,
            "status": "pending",
            "git_branch": "exp/1",
            "config": {"entrypoint": "train.py"},
            "started_at": None,
        },
    )()
    project = type(
        "RunningProject",
        (),
        {"id": project_id, "status": "running"},
    )()
    queued = []
    published = []

    async def fake_publish(event):
        published.append(event)
        return 1

    class FakeGitService:
        def __init__(self, _storage):
            return None

        def checkout_branch(self, _project_id, _branch):
            return None

        def _repository_path(self, _project_id):
            return tmp_path

    class FakeExecutor:
        def __init__(self, _storage):
            return None

        async def run_experiment(self, value, _code_path, _config):
            return ExperimentResult(value, "container-123", "running", Path(tmp_path))

    monkeypatch.setattr(
        experiment_tasks,
        "async_session_factory",
        lambda: FakeStartSession(experiment, project),
    )
    monkeypatch.setattr(experiment_tasks, "GitService", FakeGitService)
    monkeypatch.setattr(experiment_tasks, "ExperimentExecutor", FakeExecutor)
    monkeypatch.setattr(experiment_tasks, "publish_project_event", fake_publish)
    monkeypatch.setattr(monitor_experiment_task, "delay", queued.append)

    result = await experiment_tasks._start_experiment(experiment_id)

    assert result["status"] == "running"
    assert experiment.status == "running"
    assert queued == [str(experiment_id)]
    assert published[0].type == "experiment_started"
    assert published[0].project_id == project_id


@pytest.mark.asyncio
async def test_monitor_experiment_publishes_progress_and_completion(
    monkeypatch,
) -> None:
    experiment_id = uuid.uuid4()
    project_id = uuid.uuid4()
    experiment = type(
        "RunningExperiment",
        (),
        {"id": experiment_id, "project_id": project_id, "config": {}},
    )()
    events = []

    class LookupSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, _model, _identifier):
            return experiment

    class FakeBroker:
        def __init__(self, _redis_url):
            return None

        async def publish(self, event):
            events.append(event)
            return 1

        async def close(self):
            return None

    class FakeMonitor:
        def __init__(self, _storage, *, executor, progress_callback):
            assert executor is not None
            self.progress_callback = progress_callback

        async def monitor_experiment(self, value):
            await self.progress_callback(
                value,
                "Epoch 3/5 accuracy=0.82 loss=0.41",
            )
            return MonitorResult(
                experiment_id=value,
                status="completed",
                metrics={"accuracy": 0.9},
                log_lines=1,
                anomalies=(),
            )

    monkeypatch.setattr(
        experiment_tasks,
        "async_session_factory",
        lambda: LookupSession(),
    )
    monkeypatch.setattr(experiment_tasks, "RealtimeEventBroker", FakeBroker)
    monkeypatch.setattr(experiment_tasks, "ExperimentMonitor", FakeMonitor)

    result = await experiment_tasks._monitor_experiment(experiment_id)

    assert result["status"] == "completed"
    assert [event.type for event in events] == [
        "experiment_progress",
        "experiment_completed",
    ]
    assert events[0].epoch == 3
    assert events[0].total_epochs == 5
    assert events[0].metrics == {"accuracy": 0.82, "loss": 0.41}


@pytest.mark.asyncio
async def test_monitor_failure_invokes_recovery_with_anomaly_log(monkeypatch) -> None:
    experiment_id = uuid.uuid4()
    project_id = uuid.uuid4()
    experiment = type(
        "RunningExperiment",
        (),
        {"id": experiment_id, "project_id": project_id, "config": {}},
    )()
    events = []
    recovery_logs = []

    class LookupSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, _model, _identifier):
            return experiment

    class FakeBroker:
        def __init__(self, _redis_url):
            return None

        async def publish(self, event):
            events.append(event)
            return 1

        async def close(self):
            return None

    class FakeMonitor:
        def __init__(self, _storage, *, executor, progress_callback):
            assert executor is not None
            return None

        async def monitor_experiment(self, value):
            return MonitorResult(
                experiment_id=value,
                status="failed",
                metrics={},
                log_lines=1,
                anomalies=("line 1: RuntimeError: CUDA out of memory",),
            )

    async def fake_recovery(_experiment_id, error_log):
        recovery_logs.append(error_log)
        return await AutoErrorHandler().handle(error_log, {})

    monkeypatch.setattr(
        experiment_tasks,
        "async_session_factory",
        lambda: LookupSession(),
    )
    monkeypatch.setattr(experiment_tasks, "RealtimeEventBroker", FakeBroker)
    monkeypatch.setattr(experiment_tasks, "ExperimentMonitor", FakeMonitor)
    monkeypatch.setattr(
        experiment_tasks,
        "_attempt_error_recovery",
        fake_recovery,
    )

    result = await experiment_tasks._monitor_experiment(experiment_id)

    assert recovery_logs == ["line 1: RuntimeError: CUDA out of memory"]
    assert result["recovery"]["status"] == "retrying"
    assert events[0].type == "experiment_failed"


@pytest.mark.asyncio
async def test_failed_experiment_is_adjusted_logged_and_requeued(
    monkeypatch,
    tmp_path,
) -> None:
    experiment_id = uuid.uuid4()
    project_id = uuid.uuid4()
    experiment = type(
        "FailedExperiment",
        (),
        {
            "id": experiment_id,
            "project_id": project_id,
            "node_id": "2-1",
            "git_branch": "exp/2-1",
            "status": "failed",
            "config": {"training": {"batch_size": 64}},
            "started_at": datetime.now(UTC),
            "completed_at": datetime.now(UTC),
            "duration_seconds": 8,
        },
    )()
    project = type("Project", (), {"id": project_id})()
    persisted_logs = []
    published = []
    queued = []

    class RecoverySession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, model, _identifier):
            return experiment if model is Experiment else project

        def add(self, value):
            persisted_logs.append(value)

        async def commit(self):
            return None

    class FakeGitService:
        def __init__(self, _storage):
            return None

        def checkout_branch(self, _project_id, _branch):
            return None

        def _repository_path(self, _project_id):
            return tmp_path

    async def fake_cleanup(_experiment_id):
        return None

    async def fake_publish(event):
        published.append(event)
        return 1

    monkeypatch.setattr(
        experiment_tasks,
        "async_session_factory",
        lambda: RecoverySession(),
    )
    monkeypatch.setattr(experiment_tasks, "GitService", FakeGitService)
    monkeypatch.setattr(
        experiment_tasks,
        "_cleanup_container_for_retry",
        fake_cleanup,
    )
    monkeypatch.setattr(experiment_tasks, "publish_project_event", fake_publish)
    monkeypatch.setattr(run_experiment_task, "delay", queued.append)

    outcome = await experiment_tasks._attempt_error_recovery(
        experiment_id,
        "RuntimeError: CUDA out of memory",
    )

    assert outcome.retry is True
    assert experiment.status == "pending"
    assert experiment.config["training"]["batch_size"] == 32
    assert experiment.started_at is None
    assert persisted_logs
    assert all("[auto-recovery]" in log.message for log in persisted_logs)
    assert published[0].type == "experiment_recovery"
    assert published[0].recovery["status"] == "retrying"
    assert queued == [str(experiment_id)]


@pytest.mark.asyncio
async def test_successful_retry_closes_recovery_audit_trail(monkeypatch) -> None:
    experiment_id = uuid.uuid4()
    project_id = uuid.uuid4()
    experiment = type(
        "RecoveredExperiment",
        (),
        {
            "id": experiment_id,
            "project_id": project_id,
            "config": {
                "_recovery": {
                    "status": "retrying",
                    "category": "cuda_out_of_memory",
                    "attempt": 1,
                    "max_attempts": 1,
                    "message": "Retrying",
                    "action": "Batch size reduced",
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            },
        },
    )()
    persisted_logs = []

    class RecoverySession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, _model, _identifier):
            return experiment

        def add(self, value):
            persisted_logs.append(value)

        async def commit(self):
            return None

    monkeypatch.setattr(
        experiment_tasks,
        "async_session_factory",
        lambda: RecoverySession(),
    )

    result = await experiment_tasks._mark_recovery_succeeded(experiment_id)

    assert result[0] == project_id
    assert result[1]["status"] == "recovered"
    assert experiment.config["_recovery"]["status"] == "recovered"
    assert persisted_logs[0].level == "info"


@pytest.mark.asyncio
async def test_runtime_repair_must_be_committed_before_retry(
    monkeypatch,
    tmp_path,
) -> None:
    experiment_id = uuid.uuid4()
    project_id = uuid.uuid4()
    experiment = type(
        "FailedExperiment",
        (),
        {
            "id": experiment_id,
            "project_id": project_id,
            "node_id": "3-1",
            "git_branch": "exp/3-1",
            "status": "failed",
            "config": {"entrypoint": "train.py"},
            "started_at": datetime.now(UTC),
            "completed_at": datetime.now(UTC),
            "duration_seconds": 2,
        },
    )()
    project = type("Project", (), {"id": project_id})()
    logs = []
    queued = []
    committed = []

    class RecoverySession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, model, _identifier):
            return experiment if model is Experiment else project

        def add(self, value):
            logs.append(value)

        async def commit(self):
            return None

    class FakeGitService:
        def __init__(self, _storage):
            return None

        def checkout_branch(self, _project_id, branch):
            assert branch == "exp/3-1"

        def _repository_path(self, _project_id):
            return tmp_path

        def commit_changes(self, _project_id, message):
            committed.append(message)
            return CommitInfo("a" * 40, message, "exp/3-1")

    class FakeCodeAgent:
        def __init__(self, workspace):
            assert workspace == tmp_path

        async def fix_runtime_error(self, error_log):
            assert "SyntaxError" in error_log
            return AgentResult(
                success=True,
                iterations=2,
                modified_files=["train.py"],
            )

    async def fake_cleanup(_experiment_id):
        return None

    async def fake_publish(_event):
        return 1

    monkeypatch.setattr(
        experiment_tasks,
        "async_session_factory",
        lambda: RecoverySession(),
    )
    monkeypatch.setattr(experiment_tasks, "GitService", FakeGitService)
    monkeypatch.setattr(experiment_tasks, "CodeAgent", FakeCodeAgent)
    monkeypatch.setattr(
        experiment_tasks,
        "_cleanup_container_for_retry",
        fake_cleanup,
    )
    monkeypatch.setattr(experiment_tasks, "publish_project_event", fake_publish)
    monkeypatch.setattr(run_experiment_task, "delay", queued.append)

    outcome = await experiment_tasks._attempt_error_recovery(
        experiment_id,
        "SyntaxError: '(' was never closed",
    )

    assert outcome.retry is True
    assert committed == ["Auto-recover experiment 3-1"]
    assert any("Committed validated repair" in log.message for log in logs)
    assert queued == [str(experiment_id)]


def test_monitor_task_bridges_to_async_monitor(monkeypatch) -> None:
    experiment_id = uuid.uuid4()

    async def fake_monitor(value):
        return {
            "experiment_id": str(value),
            "status": "completed",
            "metrics": {"accuracy": 0.9},
        }

    monkeypatch.setattr(experiment_tasks, "_monitor_experiment", fake_monitor)
    result = monitor_experiment_task.apply(args=[str(experiment_id)]).get()

    assert result["status"] == "completed"
    assert result["metrics"] == {"accuracy": 0.9}


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
