import asyncio
from pathlib import Path

from app.services.ai.code_agent import CodeAgent


def test_mock_framework_reads_runtime_recovery_overrides(tmp_path: Path) -> None:
    result = asyncio.run(
        CodeAgent(tmp_path).generate_framework(
            "paper",
            {"target_metrics": {"accuracy": 0.9}},
        )
    )

    assert result.success is True
    train_source = (tmp_path / "train.py").read_text(encoding="utf-8")
    assert 'os.getenv("EXPERIMENT_CONFIG", "{}")' in train_source
    assert 'runtime_value("batch_size", 64)' in train_source
    assert 'runtime_value("learning_rate", 0.001)' in train_source
    assert 'runtime_value("device", "auto")' in train_source
