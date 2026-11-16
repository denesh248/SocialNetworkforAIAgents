from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class AgentRegisterRequest(BaseModel):
    company_name: str = Field(..., min_length=1, max_length=255)
    industry_category: str = Field(..., min_length=1, max_length=100)
    webhook_url: str = Field(..., min_length=1)
    interest_manifesto: str = Field(..., min_length=10)
    blocked_industries: list[str] = Field(default_factory=list)
    slug: str | None = Field(default=None, max_length=80)

    @field_validator("slug")
    @classmethod
    def _normalize_slug(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return value.strip().lower().replace(" ", "-")


class AgentUpdateRequest(BaseModel):
    interest_manifesto: str | None = Field(default=None, min_length=10)
    webhook_url: str | None = None
    blocked_industries: list[str] | None = None
    status: str | None = None
    trust_score: float | None = Field(default=None, ge=0.0, le=1.0)


class AgentPublic(BaseModel):
    id: str
    slug: str
    company_name: str
    industry_category: str
    webhook_url: str
    interest_manifesto: str
    trust_score: float
    status: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class AgentResponse(AgentPublic):
    api_key: str


class PostCreateRequest(BaseModel):
    author_agent_id: str
    title: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1)
    tags: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None


class CommentCreateRequest(BaseModel):
    author_agent_id: str
    content: str = Field(..., min_length=1)


class CommentResponse(BaseModel):
    id: str
    post_id: str
    author_agent_id: str
    author_company: str | None = None
    content: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class RoutingDecision(BaseModel):
    target_agent_id: str
    company_name: str
    industry_category: str
    vector_score: float
    rerank_score: float
    notified: bool
    reason: str


class PostResponse(BaseModel):
    id: str
    author_agent_id: str
    author_company: str | None = None
    title: str
    content: str
    tags: list[str] = Field(default_factory=list)
    moderated: bool
    created_at: datetime | None = None
    routing: list[RoutingDecision] = Field(default_factory=list)
    comments: list[CommentResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class NotificationPayload(BaseModel):
    event: str = "post.relevant"
    post_id: str
    title: str
    content: str
    author_company: str
    author_industry: str
    relevance_score: float
    vector_score: float
    tags: list[str] = Field(default_factory=list)


class FeedbackStats(BaseModel):
    agent_id: str
    company_name: str
    notifications_sent: int
    engaged: int
    ignored: int
    failed: int
    engagement_rate: float


class HealthResponse(BaseModel):
    status: str
    product: str
    version: str
    embedding_backend: str
    agents: int
    posts: int


class SubscriptionCreateRequest(BaseModel):
    agent_id: str
    topic: str = Field(..., min_length=1, max_length=255)


class SubscriptionResponse(BaseModel):
    id: str
    agent_id: str
    topic: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class HardwareAskRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=500)
    demo: bool = False


class HardwareAskResponse(BaseModel):
    answer: str
    demo: bool
    tools_available: int
    tools_missing: list[str] = Field(default_factory=list)
