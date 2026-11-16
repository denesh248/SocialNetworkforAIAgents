from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Agent, AgentStatus


def require_agent(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> Agent | None:
    """Optional API-key gate. Enabled with REQUIRE_API_KEY=true."""
    settings = get_settings()
    if not settings.require_api_key:
        return None
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    agent = db.query(Agent).filter(Agent.api_key == x_api_key).first()
    if not agent:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if agent.status != AgentStatus.ACTIVE:
        raise HTTPException(status_code=403, detail="Agent is not active")
    return agent
