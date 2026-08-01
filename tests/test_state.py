import pytest
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import TypeAdapter, ValidationError

from agent_os.graph import build_graph
from agent_os.routing import build_runtime_config
from agent_os.schemas import ArchitectBrief, BashResult, EditFileResult, ExecutorReport
from agent_os.state import SimonState


def test_simon_state_keys():
    """1. SimonState exposes exactly the seven required keys."""
    # TypedDict.__annotations__ gives the keys and types
    expected_keys = {
        "messages",
        "task",
        "plan",
        "executor_output",
        "approval",
        "human_feedback",
        "hot_context",
    }
    assert set(SimonState.__annotations__.keys()) == expected_keys
    # TypedDict fields are required unless declared with NotRequired.
    assert set(SimonState.__required_keys__) == expected_keys


def test_simon_state_validation_success():
    """2. Pydantic TypeAdapter(SimonState) accepts a complete valid state."""
    adapter = TypeAdapter(SimonState)
    valid_state = {
        "messages": [],
        "task": "Do something",
        "plan": "My plan",
        "executor_output": "Success",
        "approval": True,
        "human_feedback": "approved",
        "hot_context": "Some context"
    }
    # Should not raise exception
    validated = adapter.validate_python(valid_state)
    assert validated["task"] == "Do something"


def test_simon_state_validation_failure():
    """3. Validation rejects a state missing a required key."""
    adapter = TypeAdapter(SimonState)
    invalid_state = {
        "messages": [],
        "task": "Do something",
        "plan": "My plan",
        # Missing other keys
    }
    with pytest.raises(ValidationError):
        adapter.validate_python(invalid_state)


def fake_architect_node(state):
    return {"plan": ArchitectBrief(files=["dummy"], changes=["dummy"], verify_cmd="dummy")}


def test_build_graph_compiles():
    """4. build_graph() compiles without error."""
    graph = build_graph(
        architect_node_impl=fake_architect_node,
        checkpointer=InMemorySaver(),
    )
    assert graph is not None

    g = graph.get_graph()
    expected_nodes = {
        "__start__",
        "planner",
        "supervisor",
        "architect",
        "human_gate",
        "executor",
        "tool_dispatcher",
        "__end__",
    }
    assert set(g.nodes.keys()) == expected_nodes

    edges = {(e.source, e.target) for e in g.edges}
    expected_edges = {
        ("__start__", "planner"),
        ("planner", "supervisor"),
        ("supervisor", "architect"),
        ("supervisor", "executor"),
        ("supervisor", "tool_dispatcher"),
        ("supervisor", "__end__"),
        ("architect", "human_gate"),
        ("human_gate", "supervisor"),
        ("executor", "supervisor"),
        ("tool_dispatcher", "__end__"),
    }
    assert edges == expected_edges


def test_graph_invocation():
    """5. Invocation reaches the architect and pauses at the human gate."""
    graph = build_graph(
        architect_node_impl=fake_architect_node,
        checkpointer=InMemorySaver(),
    )
    initial_state = {
        "messages": [],
        "task": "Test task",
        "plan": None,
        "executor_output": None,
        "approval": None,
        "human_feedback": None,
        "hot_context": None,
    }

    config = build_runtime_config("thread-test-1")

    # Run the graph
    result = graph.invoke(initial_state, config=config)

    # Assert values
    assert result["task"] == "Test task"

    assert isinstance(result["plan"], ArchitectBrief)
    assert result["plan"].files == ["dummy"]

    assert result["executor_output"] is None
    assert result["approval"] is None
    assert result["human_feedback"] is None
    assert result["hot_context"] is None
    assert result["messages"] == []

def test_architect_brief_validation():
    """ArchitectBrief validates a correct payload."""
    brief = ArchitectBrief(files=["a.py"], changes=["fix"], verify_cmd="pytest")
    assert brief.files == ["a.py"]
    assert brief.changes == ["fix"]
    assert brief.verify_cmd == "pytest"


def test_architect_brief_missing_fields():
    """Missing fields fail validation."""
    with pytest.raises(ValidationError):
        ArchitectBrief(files=["a.py"])


def test_simon_state_plan_accepts_brief():
    """SimonState accepts both a string plan and ArchitectBrief."""
    adapter = TypeAdapter(SimonState)
    valid_state = {
        "messages": [],
        "task": "Do something",
        "plan": ArchitectBrief(files=["file1"], changes=["fix"], verify_cmd="ls"),
        "executor_output": None,
        "approval": None,
        "human_feedback": None,
        "hot_context": None,
    }
    validated = adapter.validate_python(valid_state)
    assert validated["plan"].files == ["file1"]


def test_executor_report_validation():
    report = ExecutorReport(diff="foo", verify_output="ok", success=True)
    assert report.success is True


def test_edit_file_result_validation():
    res = EditFileResult(path="foo", bytes_written=10)
    assert res.bytes_written == 10


def test_bash_result_validation():
    res = BashResult(args=["ls"], returncode=0, stdout="out", stderr="", timed_out=False)
    assert res.args == ["ls"]


def test_simon_state_executor_output_accepts_report():
    adapter = TypeAdapter(SimonState)
    valid_state = {
        "messages": [],
        "task": "Do something",
        "plan": None,
        "executor_output": ExecutorReport(diff="foo", verify_output="ok", success=True),
        "approval": None,
        "human_feedback": None,
        "hot_context": None,
    }
    validated = adapter.validate_python(valid_state)
    assert validated["executor_output"].success is True

    # Legacy string should also work
    valid_state["executor_output"] = "Legacy output string"
    validated2 = adapter.validate_python(valid_state)
    assert validated2["executor_output"] == "Legacy output string"
