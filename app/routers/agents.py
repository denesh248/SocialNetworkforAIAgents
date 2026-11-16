from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Agent, AgentStatus
from app.schemas import AgentPublic, AgentRegisterRequest, AgentResponse, AgentUpdateRequest, FeedbackStats
from app.services.embeddings import get_embedder
from app.services.feedback import apply_negative_feedback, engagement_stats

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


def _slugify(name: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in name).strip("-")
    return slug or "agent"


@router.post("/register", response_model=AgentResponse, status_code=201)
def register_agent(payload: AgentRegisterRequest, db: Session = Depends(get_db)) -> Agent:
    slug = payload.slug or _slugify(payload.company_name)
    if db.query(Agent).filter(Agent.slug == slug).first():
        raise HTTPException(status_code=409, detail=f"Slug '{slug}' is already registered")

    embedder = get_embedder()
    embedding = embedder.embed(
        f"{payload.company_name}. {payload.industry_category}. {payload.interest_manifesto}"
    )
    agent = Agent(
        slug=slug,
        company_name=payload.company_name,
        industry_category=payload.industry_category,
        webhook_url=payload.webhook_url,
        interest_manifesto=payload.interest_manifesto,
        interest_embedding=embedder.serialize(embedding),
        blocked_industries=",".join(payload.blocked_industries),
        status=AgentStatus.ACTIVE,
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


@router.get("", response_model=list[AgentPublic])
def list_agents(db: Session = Depends(get_db)) -> list[Agent]:
    return db.query(Agent).order_by(Agent.created_at.asc()).all()


@router.get("/{agent_id}", response_model=AgentPublic)
def get_agent(agent_id: str, db: Session = Depends(get_db)) -> Agent:
    agent = db.query(Agent).filter((Agent.id == agent_id) | (Agent.slug == agent_id)).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.patch("/{agent_id}", response_model=AgentPublic)
def update_agent(agent_id: str, payload: AgentUpdateRequest, db: Session = Depends(get_db)) -> Agent:
    agent = db.query(Agent).filter((Agent.id == agent_id) | (Agent.slug == agent_id)).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if payload.interest_manifesto:
        agent.interest_manifesto = payload.interest_manifesto
        embedder = get_embedder()
        agent.interest_embedding = embedder.serialize(
            embedder.embed(f"{agent.company_name}. {agent.industry_category}. {payload.interest_manifesto}")
        )
    if payload.webhook_url:
        agent.webhook_url = payload.webhook_url
    if payload.blocked_industries is not None:
        agent.blocked_industries = ",".join(payload.blocked_industries)
    if payload.status:
        try:
            agent.status = AgentStatus(payload.status.upper())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid status") from exc
    if payload.trust_score is not None:
        agent.trust_score = payload.trust_score

    db.commit()
    db.refresh(agent)
    return agent


@router.get("/{agent_id}/feedback", response_model=list[FeedbackStats])
def agent_feedback(agent_id: str, db: Session = Depends(get_db)) -> list[FeedbackStats]:
    agent = db.query(Agent).filter((Agent.id == agent_id) | (Agent.slug == agent_id)).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return engagement_stats(db, agent.id)


@router.post("/{agent_id}/feedback/apply-negative")
def agent_negative_feedback(agent_id: str, db: Session = Depends(get_db)) -> dict:
    agent = db.query(Agent).filter((Agent.id == agent_id) | (Agent.slug == agent_id)).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return apply_negative_feedback(db, agent.id)
