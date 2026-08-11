import json

from agent_os.public_concierge import PublicChatRequest, load_public_concierge_profile
from agent_os.public_concierge_ai import PublicConciergeAI


def simos_public_chat(task: str, **_kwargs) -> dict[str, object]:
    """Execute one public Simos turn through the AgentOS skill boundary."""
    profile = load_public_concierge_profile()
    if profile is None:
        return {
            "status": "error",
            "content": "Simos public profile is not configured.",
        }

    try:
        payload = json.loads(str(task or ""))
        request = PublicChatRequest.model_validate(payload)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        return {
            "status": "error",
            "content": f"Invalid Simos public chat request: {error}",
        }

    response = PublicConciergeAI(profile).respond(request)
    return {
        "status": "completed",
        "content": response.answer,
        "response": response.model_dump(mode="json"),
    }
