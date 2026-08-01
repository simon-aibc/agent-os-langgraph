import shlex

from agent_os.schemas import RouterDecision
from agent_os.skills import RegisteredSkill, SkillRegistry
from agent_os.tools.bash import bash
from agent_os.tools.edit_file import edit_file
from agent_os.tools.read_file import read_file


def parse_tier1_request(
    text: str,
    registry: SkillRegistry,
) -> RouterDecision | None:
    """Parse an explicit native-tool command without invoking an LLM."""
    skill = registry.deterministic_match(text)
    if skill is None:
        return None

    words = text.strip().split(maxsplit=1)
    if len(words) < 2:
        raise ValueError(f"Missing arguments for command '{skill.name}'")
    arguments_text = words[1].strip()

    if skill.name == "read_file":
        return RouterDecision(
            tool="read_file",
            confidence=1.0,
            arguments={"path": arguments_text},
        )

    if skill.name == "write_file":
        if "::" not in arguments_text:
            raise ValueError("Malformed write command: missing '::' separator")
        path, content = arguments_text.split("::", 1)
        path = path.strip()
        content = content.strip()
        if not path:
            raise ValueError("Missing path for write command")
        if not content:
            raise ValueError("Missing content for write command")
        return RouterDecision(
            tool="write_file",
            confidence=1.0,
            arguments={"path": path, "content": content},
        )

    if skill.name == "bash":
        try:
            command_arguments = shlex.split(arguments_text)
        except ValueError as error:
            raise ValueError(f"Malformed bash command: {error}") from error
        if not command_arguments:
            raise ValueError("Empty bash command")
        return RouterDecision(
            tool="bash",
            confidence=1.0,
            arguments={"cmd_args": command_arguments},
        )

    return None


def build_default_registry() -> SkillRegistry:
    registry = SkillRegistry()
    registry.register(
        RegisteredSkill(name="read_file", aliases=["read"], handler=read_file)
    )
    registry.register(
        RegisteredSkill(
            name="write_file",
            aliases=["write", "edit"],
            handler=edit_file,
        )
    )
    registry.register(RegisteredSkill(name="bash", aliases=[], handler=bash))
    return registry
