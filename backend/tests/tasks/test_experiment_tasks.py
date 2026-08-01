from app.tasks.experiment_tasks import should_continue


def test_should_continue_stops_for_paused_limit_or_target() -> None:
    assert not should_continue(project_status="paused", completed_iterations=0, max_iterations=3, target_metrics={}, latest_metrics={})
    assert not should_continue(project_status="running", completed_iterations=3, max_iterations=3, target_metrics={}, latest_metrics={})
    assert not should_continue(project_status="running", completed_iterations=1, max_iterations=3, target_metrics={"accuracy": 0.9}, latest_metrics={"accuracy": 0.9})


def test_should_continue_allows_an_unmet_target() -> None:
    assert should_continue(project_status="running", completed_iterations=1, max_iterations=3, target_metrics={"accuracy": 0.9}, latest_metrics={"accuracy": 0.8})
