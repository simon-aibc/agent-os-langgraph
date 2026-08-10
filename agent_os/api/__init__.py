"""Stable public extension API for Agent OS.

Only names exported here are covered by the v2 compatibility policy.
"""

from agent_os.backends import (
    AuthStatus,
    BackendAdapter,
    BackendArtifact,
    BackendInvoker,
    BackendRegistry,
    BackendRole,
)
from agent_os.connectors import ConnectorRegistry, MemoryConnector
from agent_os.policy import LocalPolicy, PolicyEngine, apply_policy
from agent_os.schemas import ActionProposal, ExecutionResult, PolicyDecision
from agent_os.skill_packages import SkillPackageLoader
from agent_os.skills import RegisteredSkill, SkillHandler, SkillRegistry

__all__ = (
    "ActionProposal",
    "AuthStatus",
    "BackendAdapter",
    "BackendArtifact",
    "BackendInvoker",
    "BackendRegistry",
    "BackendRole",
    "ConnectorRegistry",
    "ExecutionResult",
    "LocalPolicy",
    "MemoryConnector",
    "PolicyDecision",
    "PolicyEngine",
    "RegisteredSkill",
    "SkillHandler",
    "SkillPackageLoader",
    "SkillRegistry",
    "apply_policy",
)
