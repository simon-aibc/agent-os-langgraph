from agent_os.routing import DEFAULT_RUNTIME_CONFIG, route_from_state


def test_default_runtime_config_limits_recursion_to_six_steps():
    """The shared runtime convention caps graph execution at six steps."""
    assert DEFAULT_RUNTIME_CONFIG == {"recursion_limit": 6}


def test_route_skill_first():
    """1. skill-first: if task matches a known skill keyword, return 'tool'."""
    # Even if other conditions are met, skill precedence should win
    state = {
        "messages": [],
        "task": "Please search for something",
        "plan": None,
        "executor_output": "Some output",  # Ordinarily maps to "end"
        "approval": True,                  # Ordinarily maps to "executor"
        "hot_context": None
    }
    assert route_from_state(state) == "tool"


def test_route_executor_output():
    """2. if executor_output is present, return 'end'."""
    state = {
        "messages": [],
        "task": "A normal task",
        "plan": None,
        "executor_output": "Task completed successfully",
        "approval": True,
        "hot_context": None
    }
    assert route_from_state(state) == "end"


def test_route_approval_true():
    """3. if approval is True, return 'executor'."""
    state = {
        "messages": [],
        "task": "A normal task",
        "plan": "My plan",
        "executor_output": None,
        "approval": True,
        "hot_context": None
    }
    assert route_from_state(state) == "executor"


def test_route_otherwise_architect():
    """4. otherwise return 'architect'."""
    state = {
        "messages": [],
        "task": "A normal task",
        "plan": None,
        "executor_output": None,
        "approval": None,
        "hot_context": None
    }
    assert route_from_state(state) == "architect"

    # Even if approval is False, it goes to architect
    state["approval"] = False
    assert route_from_state(state) == "architect"
