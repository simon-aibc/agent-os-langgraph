from agent_os.schemas import (
    CodingPlan,
    CodingResult,
    ExecutionResult,
    PlanArtifact,
)


def test_plan_artifact_defaults():
    plan = PlanArtifact(summary="Test summary")
    assert plan.summary == "Test summary"
    assert plan.steps == []
    assert plan.proposed_actions == []
    assert plan.metadata == {}


def test_execution_result_defaults_and_success():
    result_completed = ExecutionResult(status="completed")
    assert result_completed.status == "completed"
    assert result_completed.success is True
    assert result_completed.outputs == {}
    assert result_completed.artifacts == []
    assert result_completed.errors == []
    assert result_completed.usage == {}

    result_failed = ExecutionResult(status="failed")
    assert result_failed.success is False

    result_waiting = ExecutionResult(status="waiting")
    assert result_waiting.success is False


def test_coding_plan_is_subclass():
    plan = CodingPlan(summary="Fix bugs", files=["main.py"], changes=[], verify_cmd="")
    assert isinstance(plan, PlanArtifact)
    assert plan.files == ["main.py"]
    assert plan.changes == []
    assert plan.verify_cmd == ""


def test_coding_result_is_subclass_and_success():
    result = CodingResult(status="completed", diff="test diff")
    assert isinstance(result, ExecutionResult)
    assert result.success is True
    assert result.diff == "test diff"
    assert result.verify_output == ""

    result_failed = CodingResult(status="failed", diff="bad diff")
    assert result_failed.success is False
