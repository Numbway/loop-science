from __future__ import annotations

import pytest

from app.schemas.ai import AgentResult
from app.services.experiment.error_recovery import (
    AutoErrorHandler,
    classify_failure,
    public_experiment_config,
    recovery_metadata,
)


def test_classify_common_failures() -> None:
    assert classify_failure("RuntimeError: CUDA out of memory").category == (
        "cuda_out_of_memory"
    )
    assert classify_failure("loss=nan at epoch 2").category == "non_finite_metric"
    assert classify_failure(
        "ModuleNotFoundError: No module named 'einops'"
    ).category == "missing_dependency"
    assert classify_failure("OSError: No space left on device").category == "disk_full"


@pytest.mark.asyncio
async def test_oom_reduces_nested_batch_size_and_retries_once() -> None:
    handler = AutoErrorHandler()
    first = await handler.handle(
        "RuntimeError: CUDA out of memory",
        {"training": {"batch_size": 64}},
    )

    assert first.fixed is True
    assert first.retry is True
    assert first.config["training"]["batch_size"] == 32
    assert first.metadata["status"] == "retrying"
    assert public_experiment_config(first.config) == {"training": {"batch_size": 32}}

    second = await handler.handle("CUDA out of memory", first.config)

    assert second.fixed is False
    assert second.retry is False
    assert second.metadata["status"] == "needs_attention"
    assert second.attempt == 1


@pytest.mark.asyncio
async def test_non_finite_loss_reduces_learning_rate() -> None:
    outcome = await AutoErrorHandler().handle(
        "line 8: non-finite loss=nan",
        {"training": {"learning_rate": 0.01}},
    )

    assert outcome.retry is True
    assert outcome.config["training"]["learning_rate"] == 0.005
    assert recovery_metadata(outcome.config)["category"] == "non_finite_metric"


@pytest.mark.asyncio
async def test_disk_full_never_deletes_artifacts() -> None:
    outcome = await AutoErrorHandler().handle(
        "OSError: [Errno 28] No space left on device",
        {},
    )

    assert outcome.fixed is False
    assert outcome.retry is False
    assert "disabled" in " ".join(outcome.log_messages)


@pytest.mark.asyncio
async def test_runtime_error_uses_repair_agent_and_requires_commit() -> None:
    class FakeAgent:
        async def fix_runtime_error(self, error_log: str) -> AgentResult:
            assert "SyntaxError" in error_log
            return AgentResult(
                success=True,
                iterations=2,
                modified_files=["train.py", "train.py"],
            )

    outcome = await AutoErrorHandler(repair_agent=FakeAgent()).handle(
        "SyntaxError: '(' was never closed",
        {"entrypoint": "train.py"},
    )

    assert outcome.fixed is True
    assert outcome.retry is True
    assert outcome.requires_commit is True
    assert outcome.modified_files == ("train.py",)
