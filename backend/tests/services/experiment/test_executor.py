import uuid

import pytest

from app.services.experiment.executor import ExperimentExecutor, ExperimentExecutorError


class FakeContainer:
    id = "container-123"
    status = "running"

    def reload(self) -> None:
        self.status = "exited"

    def stop(self) -> None:
        self.status = "exited"

    def remove(self, *, force: bool) -> None:
        assert force is False


class FakeContainers:
    def __init__(self) -> None:
        self.container = FakeContainer()
        self.run_arguments = None

    def run(self, *args, **kwargs):
        self.run_arguments = args, kwargs
        return self.container

    def get(self, _name: str) -> FakeContainer:
        return self.container


class FakeClient:
    def __init__(self) -> None:
        self.containers = FakeContainers()


@pytest.mark.asyncio
async def test_run_experiment_isolates_code_and_output(tmp_path) -> None:
    experiment_id = uuid.uuid4()
    code_directory = tmp_path / "project" / "git_repo"
    code_directory.mkdir(parents=True)
    client = FakeClient()
    executor = ExperimentExecutor(tmp_path, client=client, sandbox_mode=True)

    result = await executor.run_experiment(experiment_id, code_directory, {"entrypoint": "train.py"})

    _, options = client.containers.run_arguments
    assert result.container_id == "container-123"
    assert result.output_path == tmp_path / "experiment_runs" / str(experiment_id)
    assert options["network_disabled"] is True
    assert options["read_only"] is True
    assert options["environment"] == {"SANDBOX_MODE": "1"}
    assert options["volumes"][str(code_directory)]["mode"] == "ro"
    assert (result.output_path / "config.json").is_file()


@pytest.mark.asyncio
async def test_executor_rejects_code_outside_storage(tmp_path) -> None:
    executor = ExperimentExecutor(tmp_path, client=FakeClient())

    with pytest.raises(ExperimentExecutorError):
        await executor.run_experiment(uuid.uuid4(), tmp_path.parent, {})
