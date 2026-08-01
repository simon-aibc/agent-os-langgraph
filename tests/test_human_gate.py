from unittest.mock import patch

import pytest

from agent_os.nodes.human_gate import human_gate_node, normalize_human_feedback
from agent_os.schemas import ArchitectBrief
from agent_os.state import SimonState


def make_state(plan: str | ArchitectBrief | None) -> SimonState:
    return {
        "messages": [],
        "task": "review this plan",
        "plan": plan,
        "executor_output": None,
        "human_feedback": None,
        "hot_context": None,
    }


def test_normalize_human_feedback_approved():
    assert normalize_human_feedback("approved") == "approved"
    assert normalize_human_feedback("y") == "approved"
    assert normalize_human_feedback("yes") == "approved"
    assert normalize_human_feedback(" YEs ") == "approved"


def test_normalize_human_feedback_rejected():
    assert normalize_human_feedback("rejected") == "rejected: no reason provided"
    assert normalize_human_feedback("n") == "rejected: no reason provided"
    assert normalize_human_feedback("no") == "rejected: no reason provided"

    # Check reason retention (case insensitive for prefix, retains case for reason)
    assert normalize_human_feedback("rejected: I don't like it") == "rejected: I don't like it"
    assert normalize_human_feedback("REJECTED:  Bad plan ") == "rejected: Bad plan"
    assert normalize_human_feedback("rejected:") == "rejected: no reason provided"
    assert normalize_human_feedback("REJECTED:   ") == "rejected: no reason provided"


def test_normalize_human_feedback_invalid():
    with pytest.raises(ValueError):
        normalize_human_feedback("")
    with pytest.raises(ValueError):
        normalize_human_feedback("maybe")
    with pytest.raises(ValueError):
        normalize_human_feedback(123)


def test_human_gate_node_non_architect_brief():
    with pytest.raises(ValueError, match="requires an ArchitectBrief"):
        human_gate_node(make_state("just a string"))


@patch("agent_os.nodes.human_gate.interrupt")
def test_human_gate_node_interrupts(mock_interrupt):
    mock_interrupt.return_value = "y"

    plan = ArchitectBrief(files=["a.py"], changes=["fix"], verify_cmd="ls")
    result = human_gate_node(make_state(plan))

    mock_interrupt.assert_called_once()
    args = mock_interrupt.call_args.args
    assert "ArchitectBrief JSON" in args[0]
    assert '"a.py"' in args[0]
    assert '"verify_cmd": "ls"' in args[0]

    assert result == {"human_feedback": "approved"}
