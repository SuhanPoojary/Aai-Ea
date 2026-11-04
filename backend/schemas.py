from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


IntentName = Literal[
    "general_question", "greeting", "complaint", "human_assistance",
    "return_request", "list_orders", "order_items", "order_tracking",
    "delivery_delay",
    "wrong_item", "payment_failure", "refund", "refund_policy",
    "refund_timeline", "refund_issue", "change_of_mind_return",
    "cancel_order",
    "account_locked", "subscription", "coupon", "fraud", "data_breach",
    "unsafe_request", "order_item_lookup",
]
EventStatus = Literal[
    "success", "warning", "blocked", "skipped", "waiting_for_input", "error"
]


class IntentResult(BaseModel):
    model_config = ConfigDict(extra="allow")
    intent: str = "general_question"
    category: str = "other"
    priority: Literal["low", "medium", "high", "critical"] = "medium"
    sentiment: str = "neutral"
    risk: str = "none"
    order_id: str | None = None


class CustomerContext(BaseModel):
    model_config = ConfigDict(extra="allow")
    customer_found: bool = False
    customer_id: str
    ownership_verified: bool = False
    order: dict[str, Any] | None = None
    orders: list[dict[str, Any]] = Field(default_factory=list)


class KnowledgeResult(BaseModel):
    id: str
    title: str
    text: str
    score: float = Field(ge=0, le=1)


class ActionPlan(BaseModel):
    summary: str = ""
    steps: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0, le=1)


class ReviewResult(BaseModel):
    decision: Literal["APPROVED", "REJECTED"]
    approved_actions: list[str] = Field(default_factory=list)
    reason: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolExecutionResult(BaseModel):
    tool: str
    ok: bool
    message: str = ""
    correlation_id: str | None = None
    model_config = ConfigDict(extra="allow")


class EscalationDecision(BaseModel):
    escalate: bool = False
    reasons: list[str] = Field(default_factory=list)
    team: str = "Customer Support"
    sla_minutes: int = Field(default=60, ge=1)
    decision: str = "continue_automatic_resolution"


class AgentEvent(BaseModel):
    agent: str
    action: str
    output: str
    status: EventStatus = "success"
    duration_ms: int = Field(default=0, ge=0)
    correlation_id: str | None = None


class FinalResponse(BaseModel):
    reply: str = Field(min_length=1)
    sources: list[dict[str, Any]] = Field(default_factory=list)
