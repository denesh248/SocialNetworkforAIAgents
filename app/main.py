import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app import __version__
from app.config import get_settings
from app.database import SessionLocal, init_db
from app.demo.seed import seed_demo_agents
from app.models import Agent, Post
from app.routers import agents, hardware, mock_agents, posts
from app.routers.subscriptions import router as subscriptions_router
from app.schemas import FeedbackStats, HealthResponse
from app.services.embeddings import get_embedder
from app.services.feedback import engagement_stats, mark_ignored_stale
from app.services.task_queue import start_worker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    db: Session = SessionLocal()
    try:
        agents_seeded = seed_demo_agents(db)
        logger.info("Seeded/loaded %d RelayGrid demo agents", len(agents_seeded))
    finally:
        db.close()
    workers = start_worker(n_workers=3)
    logger.info("Async webhook task queue started")
    yield
    for task in workers:
        task.cancel()


app = FastAPI(
    title="RelayGrid",
    description=(
        "Event-driven B2B network where enterprise AI agents publish offers and "
        "RelayGrid routes them with a three-stage relevance engine. Includes HardAsk, "
        "a local hardware Q&A assistant."
    ),
    version=__version__,
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agents.router)
app.include_router(posts.router)
app.include_router(mock_agents.router)
app.include_router(subscriptions_router)
app.include_router(hardware.router)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    db = SessionLocal()
    try:
        return HealthResponse(
            status="ok",
            product="RelayGrid",
            version=__version__,
            embedding_backend=get_embedder().backend_name,
            agents=db.query(Agent).count(),
            posts=db.query(Post).count(),
        )
    finally:
        db.close()


@app.get("/api/v1/feedback", response_model=list[FeedbackStats])
def all_feedback() -> list[FeedbackStats]:
    db = SessionLocal()
    try:
        return engagement_stats(db)
    finally:
        db.close()


@app.post("/api/v1/feedback/mark-ignored")
def mark_ignored() -> dict:
    db = SessionLocal()
    try:
        n = mark_ignored_stale(db)
        return {"marked_ignored": n}
    finally:
        db.close()


@app.get("/")
def root():
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    settings = get_settings()
    return {
        "name": settings.app_name,
        "version": __version__,
        "docs": "/docs",
        "embedding_backend": get_embedder().backend_name,
        "openai_enabled": settings.use_openai,
    }
