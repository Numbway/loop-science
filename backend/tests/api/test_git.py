import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.deps import get_owned_project
from app.schemas.git import CreateExperimentBranchRequest


def test_branch_request_accepts_only_valid_experiment_node_ids() -> None:
    assert CreateExperimentBranchRequest(node_id="3-2", parent_commit_sha="a" * 40).node_id == "3-2"

    with pytest.raises(ValidationError):
        CreateExperimentBranchRequest(node_id="../main", parent_commit_sha="a" * 40)


@pytest.mark.asyncio
async def test_get_owned_project_returns_404_for_other_users() -> None:
    other_user_id = uuid.uuid4()
    project = SimpleNamespace(id=uuid.uuid4(), user_id=other_user_id)

    class FakeResult:
        def scalar_one_or_none(self):
            return project

    class FakeSession:
        async def execute(self, statement):
            return FakeResult()

    with pytest.raises(HTTPException) as exc_info:
        await get_owned_project(
            project_id=project.id,
            db=FakeSession(),
            current_user=SimpleNamespace(id=uuid.uuid4()),
        )

    assert exc_info.value.status_code == 404
