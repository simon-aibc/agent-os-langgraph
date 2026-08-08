from typing import Any, Literal

from langgraph.types import interrupt

from agent_os.connectors import MemoryWriteResult, WritableMemory
from agent_os.nodes.human_gate import normalize_human_feedback
from agent_os.policy import LocalPolicy
from agent_os.schemas import ActionProposal, MemoryWriteProposal


def evaluate_write_policy(ref: str, mode: str) -> Literal["auto", "gate"]:
    proposal = ActionProposal(
        tool="memory.write",
        arguments={"ref": ref, "mode": mode},
        side_effect="write",
    )
    decision = LocalPolicy().evaluate(proposal)
    return "auto" if decision.decision == "allow" else "gate"

def gated_write(
    connector: WritableMemory,
    proposal: MemoryWriteProposal,
    content: str,
    frontmatter: dict[str, Any] | None = None,
) -> MemoryWriteResult:
    action = ActionProposal(
        tool="memory.write",
        connector=proposal.connector,
        arguments={"ref": proposal.ref, "mode": proposal.mode},
        side_effect="write",
    )
    decision = LocalPolicy().evaluate(action)
    
    if decision.decision == "require_approval":
        feedback = normalize_human_feedback(interrupt(proposal.side_effect))
        if feedback.startswith("rejected"):
            return MemoryWriteResult(ref=proposal.ref, mode=proposal.mode, bytes_written=None, committed=False)
    elif decision.decision == "deny":
        return MemoryWriteResult(ref=proposal.ref, mode=proposal.mode, bytes_written=None, committed=False)
            
    return connector.write_note(proposal.ref, content, frontmatter=frontmatter, mode=proposal.mode)
