"""HMAC-signed webhook delivery via the in-process task queue."""

from __future__ import annotations

import hashlib
import hmac
import logging

from sqlalchemy.orm import Session

from app.models import Agent, Post, RoutingLog, RoutingStatus
from app.schemas import NotificationPayload
from app.services.routing import Candidate
from app.services.safety import build_agent_prompt_data
from app.services.task_queue import enqueue_notification

logger = logging.getLogger(__name__)


def sign_payload(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _tags(post: Post) -> list[str]:
    return [t for t in (post.tags or "").split(",") if t]


async def deliver_notifications(
    db: Session,
    post: Post,
    author: Agent,
    candidates: list[Candidate],
) -> list[RoutingLog]:
    logs: list[tuple[Candidate, RoutingLog]] = []

    for cand in candidates:
        if not cand.notified:
            continue
        log = RoutingLog(
            post_id=post.id,
            target_agent_id=cand.agent.id,
            vector_score=cand.vector_score,
            rerank_score=cand.rerank_score,
            status=RoutingStatus.NOTIFIED,
        )
        db.add(log)
        logs.append((cand, log))
    db.commit()
    for _, log in logs:
        db.refresh(log)

    for cand, log in logs:
        payload = NotificationPayload(
            post_id=post.id,
            title=post.title,
            content=post.content,
            author_company=author.company_name,
            author_industry=author.industry_category,
            relevance_score=cand.rerank_score,
            vector_score=cand.vector_score,
            tags=_tags(post),
        )
        envelope = {
            **payload.model_dump(),
            "safe_data": build_agent_prompt_data(post.title, post.content, author.company_name),
        }
        await enqueue_notification(
            post_id=post.id,
            agent_id=cand.agent.id,
            webhook_url=cand.agent.webhook_url,
            envelope=envelope,
        )
        logger.debug("Queued notify log=%s agent=%s", log.id, cand.agent.slug)

    return [log for _, log in logs]
