from app.services.git.exceptions import DirtyWorkingTreeError, GitServiceError


def test_domain_error_exposes_stable_code_message_and_hint() -> None:
    error = DirtyWorkingTreeError(
        message="Repository contains uncommitted changes.",
        hint="Commit or manually resolve the changes before switching branches.",
    )

    assert isinstance(error, GitServiceError)
    assert error.code == "dirty_working_tree"
    assert error.message == "Repository contains uncommitted changes."
    assert error.hint == "Commit or manually resolve the changes before switching branches."
