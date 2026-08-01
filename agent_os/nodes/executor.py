from agent_os.agents.executor import build_executor_agent
from agent_os.schemas import ArchitectBrief, ExecutorReport
from agent_os.state import SimonState


def executor_node(state: SimonState) -> dict:
    """
    R4 Executor node.
    Requires state["plan"] to be an ArchitectBrief.
    Executes the plan using the sandboxed executor agent.
    Returns ExecutorReport in executor_output.
    """
    plan = state.get("plan")
    if not isinstance(plan, ArchitectBrief):
        raise ValueError("Executor requires an ArchitectBrief plan.")

    agent = build_executor_agent()
    user_message = f"Please execute this ArchitectBrief:\n{plan.model_dump_json()}"

    result = agent.invoke({"messages": [("user", user_message)]})

    if "structured_response" not in result or not isinstance(result["structured_response"], ExecutorReport):
        raise ValueError("Executor agent failed to return a valid ExecutorReport.")

    return {"executor_output": result["structured_response"]}
