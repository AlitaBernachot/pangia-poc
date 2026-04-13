from fastapi import APIRouter

from app.agent.utils import get_active_agents, get_agent_labels

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/agents")
async def list_agents() -> dict:
    """Return the list of sub-agents currently enabled in the backend configuration.

    The frontend uses this to render the agent-selector toggle UI and to know
    which agents it can include in ``selected_agents`` when calling ``/api/chat``.
    """
    active = get_active_agents()
    labels = get_agent_labels()
    return {
        "agents": [
            {"key": k, "label": labels.get(k, k)}
            for k in active
        ]
    }
