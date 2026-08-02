import uuid
import stat
from types import SimpleNamespace

import pytest

from app.services.experiment.executor import ExperimentExecutor, ExperimentExecutorError
from app.services.experiment.remote_executor import RemoteExperimentExecutor


class FakeContainer:
    id = "container-123"
    status = "running"

    def __init__(self) -> None:
        self.attrs = {"State": {"ExitCode": 0}}

    def reload(self) -> None:
        self.status = "exited"

    def stop(self) -> None:
        self.status = "exited"

    def remove(self, *, force: bool) -> None:
        assert force is False

    def logs(self, *, stream: bool, follow: bool):
        assert stream is True
        assert follow is True
        return iter([b"epoch=1\n", b"loss=0.1\n"])


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

    result = await executor.run_experiment(
        experiment_id, code_directory, {"entrypoint": "train.py"}
    )

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


@pytest.mark.asyncio
async def test_executor_streams_logs_and_manages_lifecycle(tmp_path) -> None:
    experiment_id = uuid.uuid4()
    executor = ExperimentExecutor(tmp_path, client=FakeClient())

    assert [line async for line in executor.stream_logs(experiment_id)] == [
        "epoch=1",
        "loss=0.1",
    ]
    assert await executor.get_status(experiment_id) == "exited"
    assert await executor.get_exit_code(experiment_id) == 0
    await executor.stop(experiment_id)
    await executor.cleanup(experiment_id)


class RecordingRemoteFile:
    def __init__(self, files: dict[str, bytes], path: str) -> None:
        self.files = files
        self.path = path
        self.content = bytearray()

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        self.files[self.path] = bytes(self.content)

    def write(self, value: bytes) -> None:
        self.content.extend(value)


class RecordingSftp:
    def __init__(self, data_path: str) -> None:
        self.data_path = data_path
        self.uploads: list[tuple[str, str]] = []
        self.files: dict[str, bytes] = {}
        self.directories = {"/", "/home", "/home/researcher"}

    def normalize(self, path: str) -> str:
        assert path == "."
        return "/home/researcher"

    def stat(self, path: str):
        if path == self.data_path:
            return SimpleNamespace(st_mode=stat.S_IFDIR)
        if path in self.directories:
            return SimpleNamespace(st_mode=stat.S_IFDIR)
        raise OSError(path)

    def mkdir(self, path: str) -> None:
        self.directories.add(path)

    def put(self, local: str, remote: str) -> None:
        self.uploads.append((local, remote))

    def file(self, path: str, _mode: str) -> RecordingRemoteFile:
        return RecordingRemoteFile(self.files, path)

    def chmod(self, _path: str, _mode: int) -> None:
        return None


class RecordingSshClient:
    def __init__(self, sftp: RecordingSftp) -> None:
        self.sftp = sftp
        self.closed = False

    def open_sftp(self) -> RecordingSftp:
        return self.sftp

    def exec_command(self, _command: str, timeout: int):
        assert timeout == 15

        def stream(value: bytes):
            return SimpleNamespace(read=lambda: value)

        return None, stream(b"4242\n"), stream(b"")

    def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_remote_executor_reuses_selected_server_data_without_uploading_it(
    tmp_path,
) -> None:
    experiment_id = uuid.uuid4()
    code_directory = tmp_path / "project" / "git_repo"
    code_directory.mkdir(parents=True)
    (code_directory / "train.py").write_text("print('train')\n")
    data_path = "/srv/research/prepared-dataset"
    sftp = RecordingSftp(data_path)
    client = RecordingSshClient(sftp)
    executor = RemoteExperimentExecutor(
        tmp_path,
        {"host": "gpu.example.edu"},
        {"password": "secret"},
        data_path,
    )
    executor._connect = lambda: client

    result = await executor.run_experiment(
        experiment_id,
        code_directory,
        {
            "entrypoint": "train.py",
            "arguments": ["--data-path", "{data_path}", "--epochs", "4"],
        },
    )

    assert result.container_id == "ssh:gpu.example.edu:4242"
    assert len(sftp.uploads) == 1
    assert sftp.uploads[0][0].endswith("train.py")
    assert all(data_path not in local for local, _remote in sftp.uploads)
    launch_script = next(
        content.decode("utf-8")
        for path, content in sftp.files.items()
        if path.endswith("/launch.sh")
    )
    assert f"export DATA_PATH={data_path}" in launch_script
    assert f'"data_path": "{data_path}"' in launch_script
    assert f"train.py --data-path {data_path} --epochs 4" in launch_script
    assert client.closed is True
