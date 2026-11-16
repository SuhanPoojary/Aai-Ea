from datetime import datetime, timezone
from sqlalchemy import String, Integer, Text, DateTime, Boolean, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base


def utc_now():
    return datetime.now(timezone.utc)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    tier: Mapped[str] = mapped_column(String(30), default="Standard")
    email: Mapped[str] = mapped_column(String(150), default="", index=True)
    city: Mapped[str] = mapped_column(String(80), default="Mumbai")
    account_status: Mapped[str] = mapped_column(String(30), default="Active")


class UserAccount(Base):
    """Login identity kept separate from the existing customer table."""
    __tablename__ = "user_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.id"), unique=True, index=True
    )
    email: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="customer")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    category: Mapped[str] = mapped_column(String(80), default="General")
    description: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[float] = mapped_column(Float, default=0)
    stock: Mapped[int] = mapped_column(Integer, default=0)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    item: Mapped[str] = mapped_column(String(150))
    delivered_item: Mapped[str] = mapped_column(String(150), default="")
    status: Mapped[str] = mapped_column(String(40), default="processing")
    amount: Mapped[float] = mapped_column(Float, default=0)
    payment_status: Mapped[str] = mapped_column(String(50), default="success")
    courier: Mapped[str] = mapped_column(String(80), default="Aegis Express")
    eta: Mapped[str] = mapped_column(String(80), default="")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    product_name: Mapped[str] = mapped_column(String(150))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[float] = mapped_column(Float, default=0)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    amount: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(50), default="success")
    method: Mapped[str] = mapped_column(String(40), default="UPI")
    transaction_ref: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Shipment(Base):
    __tablename__ = "shipments"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), unique=True, index=True)
    courier: Mapped[str] = mapped_column(String(80), default="Aegis Express")
    tracking_code: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(40), default="processing")
    estimated_delivery: Mapped[str] = mapped_column(String(80), default="")


class ReturnRequest(Base):
    __tablename__ = "return_requests"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="Requested")
    resolution: Mapped[str] = mapped_column(String(40), default="Replacement")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    order_id: Mapped[str | None] = mapped_column(
        ForeignKey("orders.id"), nullable=True, index=True
    )
    issue: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(50), default="other")
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    team: Mapped[str] = mapped_column(String(60), default="Customer Support")
    status: Mapped[str] = mapped_column(String(30), default="Opened")
    sla_minutes: Mapped[int] = mapped_column(Integer, default=60)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    human_takeover: Mapped[bool] = mapped_column(Boolean, default=False)


class ConversationState(Base):
    __tablename__ = "conversation_states"

    conversation_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    current_intent: Mapped[str] = mapped_column(String(80), default="general_question")
    previous_intent: Mapped[str] = mapped_column(String(80), default="")
    selected_order_id: Mapped[str] = mapped_column(String(30), default="")
    selected_ticket_id: Mapped[str] = mapped_column(String(30), default="")
    active_issue_category: Mapped[str] = mapped_column(String(50), default="other")
    last_action: Mapped[str] = mapped_column(String(120), default="")
    pending_clarification: Mapped[str] = mapped_column(Text, default="")
    recent_context: Mapped[str] = mapped_column(Text, default="[]")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    user_text: Mapped[str] = mapped_column(Text)
    assistant_text: Mapped[str] = mapped_column(Text)
    intent: Mapped[str] = mapped_column(String(80), default="other")
    outcome: Mapped[str] = mapped_column(String(40), default="answered")
    response_version: Mapped[str] = mapped_column(String(40), default="response-v1")
    prompt_version: Mapped[str] = mapped_column(String(40), default="prompt-v1")
    llm_provider: Mapped[str] = mapped_column(String(40), default="deterministic")
    model_name: Mapped[str] = mapped_column(String(120), default="")
    execution_duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AgentEvent(Base):
    __tablename__ = "agent_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(String(60), index=True)
    agent: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(160))
    output: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="success")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    correlation_id: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
