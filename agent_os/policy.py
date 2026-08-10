from collections.abc import Callable
from typing import Any, Literal, Protocol

from langgraph.types import interrupt

from agent_os.nodes.human_gate import normalize_human_feedback
from agent_os.schemas import ActionProposal, ExecutionResult, PolicyDecision


class PolicyEngine(Protocol):
    def evaluate(
        self,
        proposal: ActionProposal,
        *,
        workspace: Any = None,
        context: Any = None,
    ) -> PolicyDecision:
        ...


class LocalPolicy:
    def __init__(self, rules: dict[str, Any] | None = None) -> None:
        self.rules = rules or {}

    def evaluate(
        self,
        proposal: ActionProposal,
        *,
        workspace: Any = None,
        context: Any = None,
    ) -> PolicyDecision:
        # Default taxonomy
        decision: Literal["allow", "deny", "require_approval"] = "require_approval"
        
        # Backward compat logic for write_policy on AI/Logs and AI/Briefs
        if proposal.side_effect == "write" and proposal.arguments and "ref" in proposal.arguments:
            ref = str(proposal.arguments["ref"])
            mode = str(proposal.arguments.get("mode", ""))
            normalized_ref = ref.lstrip("/")
            is_log = normalized_ref.startswith("AI/Logs/") or normalized_ref.startswith("agentos/logs/")
            if is_log and mode == "append":
                return PolicyDecision(decision="allow", policy_id="builtin-logs", reason="Logs can be appended automatically")
            is_brief = normalized_ref.startswith("AI/Briefs/") or normalized_ref.startswith("agentos/briefs/")
            if is_brief and mode in ("append", "create"):
                return PolicyDecision(decision="allow", policy_id="builtin-briefs", reason="Briefs can be appended/created automatically")

        # Map side_effect to default decision
        if proposal.side_effect in ("read", "none"):
            decision = "allow"
        elif proposal.side_effect in ("payment", "privileged"):
            decision = "deny"
        else: # write, network, communication
            decision = "require_approval"
            
        return PolicyDecision(
            decision=decision,
            policy_id="default",
            reason=f"Default taxonomy for {proposal.side_effect}",
        )


def apply_policy(
    engine: PolicyEngine,
    proposal: ActionProposal,
    *,
    workspace: Any = None,
    context: Any = None,
    execute_fn: Callable[[ActionProposal], ExecutionResult],
) -> ExecutionResult:
    decision = engine.evaluate(proposal, workspace=workspace, context=context)
    
    if decision.decision == "allow":
        return execute_fn(proposal)
        
    elif decision.decision == "require_approval":
        # Interrupt with human-readable proposal
        msg = f"Proposal: {proposal.tool} with side_effect={proposal.side_effect}. Reason: {decision.reason}"
        feedback = normalize_human_feedback(interrupt(msg))
        if feedback.startswith("approved"):
            return execute_fn(proposal)
        return ExecutionResult(status="cancelled", outputs={}, errors=["User rejected"], artifacts=[])
        
    # Deny
    return ExecutionResult(status="failed", outputs={}, errors=[decision.reason], artifacts=[])
