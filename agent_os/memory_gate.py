from typing import Any, Literal

from langgraph.types import interrupt

from agent_os.connectors import MemoryWriteResult, WritableMemory
from agent_os.nodes.human_gate import normalize_human_feedback
from agent_os.schemas import MemoryWriteProposal


def evaluate_write_policy(ref: str, mode: str) -> Literal["auto", "gate"]:
    normalized_ref = ref.lstrip("/")
    is_log = normalized_ref.startswith("AI/Logs/") or normalized_ref.startswith("agentos/logs/")
    if is_log and mode == "append":
        return "auto"
    return "gate"


def gated_write(
    connector: WritableMemory,
    proposal: MemoryWriteProposal,
    content: str,
    frontmatter: dict[str, Any] | None = None,
) -> MemoryWriteResult:
    policy = evaluate_write_policy(proposal.ref, proposal.mode)
    
    if policy == "gate":
        # Pass the side_effect or the whole proposal to interrupt. We'll pass the side_effect for simplicity
        # or the proposal so the user can see the preview. 
        # The brief says: interrupt(proposal.side_effect)
        feedback = normalize_human_feedback(interrupt(proposal.side_effect))
        if feedback.startswith("rejected"):
            return MemoryWriteResult(ref=proposal.ref, mode=proposal.mode, bytes_written=None, committed=False)
            
    return connector.write_note(proposal.ref, content, frontmatter=frontmatter, mode=proposal.mode)
