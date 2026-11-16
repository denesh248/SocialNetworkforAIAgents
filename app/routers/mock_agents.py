"""In-process mock tenants that receive HMAC webhooks and may comment back."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import Agent, Comment, Post
from app.services.feedback import mark_engaged

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/mock-agents", tags=["mock-agents"])

_REPLY_TEMPLATES: dict[str, str] = {
    "PayPulse": (
        "PayPulse wallets add extra cashback when customers pay for {author} orders this week."
    ),
    "Northstar Bank": (
        "Northstar Bank cardholders get an extra 5% statement credit on {author} seasonal orders."
    ),
    "CartWave": (
        "CartWave Plus members can stack loyalty points on partner offers from {author}."
    ),
    "MealRun": (
        "MealRun can co-promote this with restaurant partners and late-night delivery windows."
    ),
}

_LLM_SYSTEM_PROMPT = (
    "You are an AI agent representing {company} in the {industry} industry. "
    "You received a business post from {author} and decided to engage. "
    "Write a SHORT (1-2 sentence) professional partnership comment with a concrete offer. "
    "Be specific. Do not use generic filler."
)

_NEVER_ENGAGE = {"voltride"}


def _draft_reply_llm(
    company: str, industry: str, author_company: str, title: str, content: str
) -> str | None:
    settings = get_settings()
    if not settings.use_openai:
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)
        system = _LLM_SYSTEM_PROMPT.format(
            company=company, industry=industry, author=author_company
        )
        user_msg = f"Post title: {title}\n\nPost content: {content}"
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=120,
            temperature=0.7,
        )
        reply = (response.choices[0].message.content or "").strip()
        return reply or None
    except Exception as exc:
        logger.warning("LLM reply failed for %s, falling back to template: %s", company, exc)
        return None


def _draft_reply_template(company: str, author_company: str, title: str, content: str) -> str:
    template = _REPLY_TEMPLATES.get(company, "{company} wants to partner on: {title}")
    return template.format(author=author_company, company=company, title=title, content=content)


def _draft_reply(
    company: str, industry: str, author_company: str, title: str, content: str
) -> str:
    llm_reply = _draft_reply_llm(company, industry, author_company, title, content)
    if llm_reply:
        return llm_reply
    return _draft_reply_template(company, author_company, title, content)


def _verify_signature(body: bytes, signature: str | None) -> None:
    settings = get_settings()
    expected = hmac.new(settings.webhook_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")


def _should_engage(agent: Agent, score: float) -> bool:
    if agent.slug.lower() in _NEVER_ENGAGE:
        return False
    return score >= 0.55


@router.post("/{company_slug}/webhook")
async def receive_webhook(
    company_slug: str,
    request: Request,
    x_agent_network_signature: str | None = Header(default=None),
) -> dict:
    body = await request.body()
    _verify_signature(body, x_agent_network_signature)

    payload = json.loads(body.decode("utf-8"))
    safe = payload.get("safe_data", {})
    post_id = payload.get("post_id")
    score = float(payload.get("relevance_score", 0))
    author_company = payload.get("author_company", safe.get("author_company", "Partner"))
    title = payload.get("title", safe.get("title", ""))
    content = payload.get("content", safe.get("content", ""))

    db: Session = SessionLocal()
    try:
        agent = db.query(Agent).filter(Agent.slug == company_slug.lower()).first()
        if not agent:
            raise HTTPException(status_code=404, detail=f"No mock agent for slug={company_slug}")

        if not _should_engage(agent, score):
            logger.info("%s ignored post %s (score=%.3f)", agent.company_name, post_id, score)
            return {"status": "ignored", "company": agent.company_name}

        post = db.query(Post).filter(Post.id == post_id).first()
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")

        existing = (
            db.query(Comment)
            .filter(Comment.post_id == post_id, Comment.author_agent_id == agent.id)
            .first()
        )
        if existing:
            return {"status": "already_commented", "comment_id": existing.id}

        reply = _draft_reply(
            company=agent.company_name,
            industry=agent.industry_category,
            author_company=author_company,
            title=title,
            content=content,
        )
        comment = Comment(post_id=post_id, author_agent_id=agent.id, content=reply)
        db.add(comment)
        db.commit()
        db.refresh(comment)
        mark_engaged(db, post_id, agent.id)

        return {
            "status": "engaged",
            "company": agent.company_name,
            "comment_id": comment.id,
            "content": reply,
            "reply_source": "llm" if get_settings().use_openai else "template",
        }
    finally:
        db.close()
