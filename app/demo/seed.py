"""Seed original RelayGrid demo tenants (not cloned brand names)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Agent, AgentStatus, Subscription
from app.services.embeddings import get_embedder

DEMO_AGENTS = [
    {
        "company_name": "MealRun",
        "industry_category": "Food Delivery",
        "slug": "mealrun",
        "api_key": "demo-mealrun-key",
        "interest_manifesto": (
            "We care about checkout partnerships, late-night food campaigns, "
            "UPI and wallet cashback, restaurant merchant offers, and courier capacity."
        ),
    },
    {
        "company_name": "CartWave",
        "industry_category": "E-commerce",
        "slug": "cartwave",
        "api_key": "demo-cartwave-key",
        "interest_manifesto": (
            "We care about marketplace sales events, loyalty points stacking, "
            "card and wallet checkout offers, and cross-brand shopping campaigns."
        ),
    },
    {
        "company_name": "PayPulse",
        "industry_category": "Payments & Fintech",
        "slug": "paypulse",
        "api_key": "demo-paypulse-key",
        "interest_manifesto": (
            "We care about food delivery discounts, marketplace promotions, "
            "merchant cashback, card partnerships, and instant wallet offers."
        ),
    },
    {
        "company_name": "Northstar Bank",
        "industry_category": "Banking & Cards",
        "slug": "northstar-bank",
        "api_key": "demo-northstar-key",
        "interest_manifesto": (
            "We care about credit-card cashback on food and shopping, "
            "seasonal merchant partnerships, EMI campaigns, and co-branded payment offers."
        ),
    },
    {
        "company_name": "VoltRide",
        "industry_category": "Automotive",
        "slug": "voltride",
        "api_key": "demo-voltride-key",
        "interest_manifesto": (
            "We care about electric two-wheeler launches, dealer financing, "
            "battery-swap networks, spare-parts logistics, and vehicle insurance partners."
        ),
        "blocked_industries": ["Food Delivery"],
    },
]

DEMO_SUBSCRIPTIONS = {
    "paypulse": ["wallet cashback", "food delivery"],
    "northstar-bank": ["card cashback"],
}


def seed_demo_agents(db: Session, reset: bool = False) -> list[Agent]:
    settings = get_settings()
    embedder = get_embedder()

    if reset:
        db.query(Agent).delete()
        db.commit()

    created: list[Agent] = []
    for spec in DEMO_AGENTS:
        existing = db.query(Agent).filter(Agent.slug == spec["slug"]).first()
        if existing:
            created.append(existing)
            continue

        manifesto = spec["interest_manifesto"]
        embedding = embedder.embed(f"{spec['company_name']}. {spec['industry_category']}. {manifesto}")
        agent = Agent(
            slug=spec["slug"],
            company_name=spec["company_name"],
            industry_category=spec["industry_category"],
            webhook_url=f"{settings.mock_agent_base_url}/{spec['slug']}/webhook",
            interest_manifesto=manifesto,
            interest_embedding=embedder.serialize(embedding),
            blocked_industries=",".join(spec.get("blocked_industries", [])),
            status=AgentStatus.ACTIVE,
            trust_score=1.0,
            api_key=spec["api_key"],
        )
        db.add(agent)
        created.append(agent)

    db.commit()
    for agent in created:
        db.refresh(agent)

    for slug, topics in DEMO_SUBSCRIPTIONS.items():
        agent = next((a for a in created if a.slug == slug), None)
        if not agent:
            continue
        for topic in topics:
            exists = (
                db.query(Subscription)
                .filter(Subscription.agent_id == agent.id, Subscription.topic == topic)
                .first()
            )
            if exists:
                continue
            db.add(Subscription(agent_id=agent.id, topic=topic))
    db.commit()
    return created
