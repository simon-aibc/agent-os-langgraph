"""Semantic LLM Judge for post-execution acceptance criteria evaluation.

Evaluates natural language acceptance criteria against independent execution
evidence (verify_output, diff, artifacts) using an injected LLM.
Strictly evidence-bounded and fail-closed.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent_os.validation import LlmJudge, ValidationRule

logger = logging.getLogger(__name__)

_JUDGE_SYSTEM_PROMPT = """You are an objective acceptance criteria evaluator.
Your role is to evaluate whether a specific acceptance criterion is met based STRICTLY AND ONLY on the provided execution evidence.

Rules:
1. ONLY rely on the provided evidence (verify_output, diff, artifacts).
2. Do NOT invent, assume, or extrapolate facts not directly present in the evidence.
3. If the evidence lacks proof or is ambiguous, you must judge FAIL.
4. Format:
   First line MUST begin with either "PASS" or "FAIL".
   Second line should provide a concise 1-sentence factual justification based on the evidence.
"""


def _format_evidence_context(context: Mapping[str, object]) -> str:
    parts = []
    verify_output = context.get("verify_output")
    if verify_output:
        parts.append(f"=== Verify Command Output ===\n{verify_output}")

    diff = context.get("diff")
    if diff:
        parts.append(f"=== Code / File Diff ===\n{diff}")

    artifacts = context.get("artifacts")
    if artifacts:
        if isinstance(artifacts, (list, tuple)):
            art_str = "\n".join(f"- {a}" for a in artifacts)
        else:
            art_str = str(artifacts)
        parts.append(f"=== Generated Artifacts ===\n{art_str}")

    if not parts:
        return "(No execution evidence provided)"
    return "\n\n".join(parts)


def _parse_judge_response(response_text: str) -> tuple[bool, str]:
    """Extract PASS/FAIL and reasoning from LLM response."""
    lines = [
        line.strip() for line in response_text.strip().splitlines() if line.strip()
    ]
    if not lines:
        return False, "Judge returned empty response."

    first_line = lines[0].upper()
    reasoning = lines[1] if len(lines) > 1 else lines[0]

    if re.match(r"^PASS\b", first_line):
        return True, reasoning
    elif re.match(r"^FAIL\b", first_line):
        return False, reasoning

    return False, f"Indeterminate judge response: {lines[0]}"


def build_llm_judge(llm: Any) -> LlmJudge:
    """Construct an evidence-bounded LlmJudge callable wrapping an LLM."""

    def judge(
        rule: ValidationRule, evidence_context: Mapping[str, object]
    ) -> tuple[bool, str]:
        evidence_text = _format_evidence_context(evidence_context)
        user_prompt = f"""Evaluate this acceptance criterion:
Criterion ID: {rule.id}
Description: {rule.description}
Parameter: {rule.param or "(none)"}

Execution Evidence:
{evidence_text}
"""
        try:
            messages = [
                SystemMessage(content=_JUDGE_SYSTEM_PROMPT),
                HumanMessage(content=user_prompt),
            ]
            if hasattr(llm, "invoke"):
                response = llm.invoke(messages)
                content = (
                    response.content if hasattr(response, "content") else str(response)
                )
            elif callable(llm):
                response = llm(messages)
                content = (
                    response.content if hasattr(response, "content") else str(response)
                )
            else:
                return False, "LLM object is neither callable nor an invoker."

            if isinstance(content, list):
                text_parts = [
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                ]
                content = " ".join(text_parts)
            return _parse_judge_response(str(content))
        except Exception as exc:
            logger.warning("LLM judge evaluation failed: %s", exc)
            return False, f"LLM judge execution error: {type(exc).__name__}"

    return judge
