from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from time import time

import pytest
from tensorboard.compat.proto.event_pb2 import Event
from tensorboard.compat.proto.summary_pb2 import Summary
from tensorboard.summary.writer.event_file_writer import EventFileWriter

from app.services.experiment.monitor import (
    ExperimentMetrics,
    ExperimentMonitor,
    classify_log_level,
    parse_train_log,
)


class FakeExecutor:
    async def stream_logs(self, _experiment_id):
        for line in (
            "Epoch 1/2 loss=0.8 accuracy=0.5",
            "Epoch 2/2 loss=0.3 accuracy=0.9",
        ):
            yield line

    async def get_status(self, _experiment_id):
        return "exited"

    async def get_exit_code(self, _experiment_id):
        return 0


class FakeExperiment:
    def __init__(self) -> None:
        self.status = "running"
        self.metrics = None
        self.started_at = datetime.now(UTC) - timedelta(seconds=3)
        self.completed_at = None
        self.duration_seconds = None


class FakeSession:
    def __init__(self, experiment, logs) -> None:
        self.experiment = experiment
        self.logs = logs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def add(self, log) -> None:
        self.logs.append(log)

    async def get(self, _model, _experiment_id):
        return self.experiment

    async def commit(self) -> None:
        return None


def test_parse_train_log_extracts_progress_metrics_and_anomalies() -> None:
    summary = parse_train_log(
        [
            "Epoch 1/3 loss=0.8 accuracy=0.50",
            "Epoch 2/3 loss=0.3 accuracy=0.75",
            "WARNING validation_loss=nan",
        ]
    )

    assert summary.completed_epochs == 2
    assert summary.total_epochs == 3
    assert summary.latest_metrics == {"loss": 0.3, "accuracy": 0.75}
    assert summary.best_metrics == {"loss": 0.3, "accuracy": 0.75}
    assert len(summary.anomalies) == 2
    assert classify_log_level("CUDA error: out of memory") == "error"


def test_collect_metrics_reads_latest_tensorboard_scalars(tmp_path) -> None:
    experiment_id = uuid.uuid4()
    run_directory = tmp_path / "experiment_runs" / str(experiment_id) / "runs"
    writer = EventFileWriter(str(run_directory))
    for step, value in ((1, 0.6), (2, 0.9)):
        writer.add_event(
            Event(
                wall_time=time(),
                step=step,
                summary=Summary(
                    value=[Summary.Value(tag="validation/accuracy", simple_value=value)]
                ),
            )
        )
    writer.close()

    metrics = ExperimentMonitor(tmp_path).collect_metrics(experiment_id)

    assert metrics.scalars["validation/accuracy"] == pytest.approx(0.9)
    assert metrics.steps["validation/accuracy"] == 2
    assert metrics.event_files[0].startswith("runs")


@pytest.mark.asyncio
async def test_monitor_persists_live_logs_and_final_state(
    tmp_path, monkeypatch
) -> None:
    experiment_id = uuid.uuid4()
    experiment = FakeExperiment()
    logs = []
    progress = []

    async def capture_progress(experiment_id, line):
        progress.append((experiment_id, line))

    def session_factory():
        return FakeSession(experiment, logs)

    monitor = ExperimentMonitor(
        tmp_path,
        executor=FakeExecutor(),
        session_factory=session_factory,
        progress_callback=capture_progress,
    )
    monkeypatch.setattr(
        monitor,
        "collect_metrics",
        lambda _experiment_id: ExperimentMetrics(
            scalars={"accuracy": 0.95},
            steps={"accuracy": 2},
            event_files=("runs/events.out.tfevents.test",),
        ),
    )

    result = await monitor.monitor_experiment(experiment_id)

    assert [log.message for log in logs] == [
        "Epoch 1/2 loss=0.8 accuracy=0.5",
        "Epoch 2/2 loss=0.3 accuracy=0.9",
    ]
    assert result.status == "completed"
    assert result.metrics == {"loss": 0.3, "accuracy": 0.95}
    assert experiment.status == "completed"
    assert experiment.metrics == result.metrics
    assert experiment.duration_seconds >= 3
    assert [line for _experiment_id, line in progress] == [
        "Epoch 1/2 loss=0.8 accuracy=0.5",
        "Epoch 2/2 loss=0.3 accuracy=0.9",
    ]
