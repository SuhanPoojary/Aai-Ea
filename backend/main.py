
import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
import time

from fastapi import FastAPI, Depends, HTTPException
from fastapi import Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db.database import Base, engine, get_db, ensure_schema
from db.seed import seed_demo
from db.models import Customer, Order, Ticket, Conversation, AgentEvent
from db.models import UserAccount
from auth_utils import verify_password
from orchestrator.master_orchestrator import process_message
from config import FRONTEND_ORIGIN
from config import GROQ_API_KEY, GROQ_MODEL
from notifications import send_notification
from observability import increment, observe, snapshot
from rag.retrieval import cache_info


# --------------------------------------------------
# DATABASE INITIALIZATION
# --------------------------------------------------

Base.metadata.create_all(bind=engine)
ensure_schema()

with next(get_db()) as db:
    seed_demo(db)


# --------------------------------------------------
# FASTAPI APPLICATION
# --------------------------------------------------

app = FastAPI(
    title="AegisSupport API",
    version="2.0.0",
    description=(
        "Agentic customer support system with separate agents, "
        "master orchestration, MCP tools, and RAG retrieval."
    ),
)


@app.middleware("http")
async def record_request_metrics(request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - started) * 1000
    increment("http.requests")
    if response.status_code >= 400:
        increment("http.failures")
    observe(f"http.{request.method}.{request.url.path}", duration_ms)
    return response


# --------------------------------------------------
# CORS CONFIGURATION
# Supports Vite frontend on ports 5173 and 5174.
# --------------------------------------------------

ALLOWED_ORIGINS = list(
    {
        FRONTEND_ORIGIN.rstrip("/"),
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    }
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------
# REQUEST SCHEMAS
# --------------------------------------------------

class ChatInput(BaseModel):
    customer_id: str = "C001"
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None
    history: list[dict] = Field(default_factory=list)
    slots: dict = Field(default_factory=dict)


class TicketUpdate(BaseModel):
    status: str


class RegisterInput(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=5, max_length=150)
    password: str = Field(min_length=8, max_length=128)
    city: str = Field(default="Mumbai", max_length=80)


class LoginInput(BaseModel):
    email: str = Field(min_length=5, max_length=150)
    password: str = Field(min_length=1, max_length=128)


class SupervisorLoginInput(BaseModel):
    email: str = Field(min_length=5, max_length=150)
    password: str = Field(min_length=1, max_length=128)


# --------------------------------------------------
# AUTHENTICATION HELPERS
# --------------------------------------------------

TOKEN_SECRET = os.getenv("AEGIS_TOKEN_SECRET")
if not TOKEN_SECRET:
    # Development fallback. Set AEGIS_TOKEN_SECRET in .env
    # before using this application beyond a local demo.
    TOKEN_SECRET = secrets.token_urlsafe(32)
    print(
        "WARNING: AEGIS_TOKEN_SECRET is not configured. "
        "Sessions will become invalid after backend restart."
    )


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    iterations = 600_000
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return (
        f"pbkdf2_sha256${iterations}$"
        f"{base64.b64encode(salt).decode('ascii')}$"
        f"{base64.b64encode(digest).decode('ascii')}"
    )


def _encode_token(account: UserAccount) -> str:
    payload = {
        "sub": account.id,
        "customer_id": account.customer_id,
        "role": account.role,
        "exp": int(time.time()) + 60 * 60 * 24,
    }
    payload_bytes = json.dumps(
        payload, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    encoded_payload = base64.urlsafe_b64encode(payload_bytes).rstrip(b"=")
    signature = hmac.new(
        TOKEN_SECRET.encode("utf-8"),
        encoded_payload,
        hashlib.sha256,
    ).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=")
    return (
        encoded_payload.decode("ascii")
        + "."
        + encoded_signature.decode("ascii")
    )


def _encode_supervisor_token() -> str:
    payload = {
        "sub": "supervisor",
        "customer_id": None,
        "role": "supervisor",
        "exp": int(time.time()) + 60 * 60 * 8,
    }
    encoded_payload = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).rstrip(b"=")
    signature = hmac.new(
        TOKEN_SECRET.encode("utf-8"),
        encoded_payload,
        hashlib.sha256,
    ).digest()
    return encoded_payload.decode() + "." + base64.urlsafe_b64encode(signature).rstrip(b"=").decode()


def _decode_token(token: str) -> dict:
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
        expected_signature = hmac.new(
            TOKEN_SECRET.encode("utf-8"),
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        actual_signature = base64.urlsafe_b64decode(
            encoded_signature + "=" * (-len(encoded_signature) % 4)
        )
        if not hmac.compare_digest(actual_signature, expected_signature):
            raise ValueError("Invalid token signature")

        payload = json.loads(
            base64.urlsafe_b64decode(
                encoded_payload + "=" * (-len(encoded_payload) % 4)
            )
        )
        if not isinstance(payload, dict) or int(payload["exp"]) < int(time.time()):
            raise ValueError("Expired token")
        return payload
    except (
        KeyError,
        TypeError,
        ValueError,
        UnicodeDecodeError,
        binascii.Error,
        json.JSONDecodeError,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired authentication token.",
        ) from None


def require_customer(
    authorization: str | None,
    db: Session,
) -> tuple[UserAccount, Customer]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Authentication required.",
        )

    payload = _decode_token(authorization[7:].strip())
    account = db.get(UserAccount, payload.get("sub"))
    if not account or not account.is_active:
        raise HTTPException(
            status_code=401,
            detail="Account is inactive or no longer exists.",
        )

    customer = db.get(Customer, account.customer_id)
    if not customer:
        raise HTTPException(
            status_code=401,
            detail="Customer account is no longer available.",
        )
    return account, customer


def require_supervisor(
    authorization: str | None,
    db: Session,
) -> tuple[UserAccount, Customer]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required.")
    payload = _decode_token(authorization[7:].strip())
    if payload.get("role") == "supervisor" and payload.get("sub") == "supervisor":
        return UserAccount(id=-1, customer_id="", email="", password_hash="", role="supervisor"), Customer(
            id="SUPERVISOR", name="Supervisor", email="", city="", tier="Operations"
        )
    account, customer = require_customer(authorization, db)
    if account.role != "supervisor":
        raise HTTPException(status_code=403, detail="Supervisor role required.")
    return account, customer


# --------------------------------------------------
# HEALTH CHECK
# --------------------------------------------------

@app.get("/api/health")
def health():
    return {
        "ok": True,
        "service": "AegisSupport API",
        "version": "2.0.0",
        "database": "configured",
        "features": [
            "separate-agents",
            "master-orchestration",
            "MCP-tools",
            "RAG-retrieval",
            "conversation-memory",
            "ticket-management",
            "SLA-tracking",
        ],
    }


@app.get("/api/metrics")
def metrics(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    require_supervisor(authorization, db)
    return {
        "metrics": snapshot(),
        "rag_cache": cache_info(),
        "privacy": {
            "secrets_logged": False,
            "customer_content_logged": False,
        },
    }


# --------------------------------------------------
# CUSTOMERS
# --------------------------------------------------

@app.get("/api/customers")
def customers(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    require_supervisor(authorization, db)
    rows = db.query(Customer).order_by(Customer.id).all()

    return [
        {
            "id": c.id,
            "name": c.name,
            "tier": c.tier,
            "city": c.city,
            "email": c.email,
        }
        for c in rows
    ]


# --------------------------------------------------
# CUSTOMER ORDERS
# --------------------------------------------------

@app.get("/api/orders/{customer_id}")
def orders(
    customer_id: str,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    require_supervisor(authorization, db)
    customer = db.get(Customer, customer_id)

    if not customer:
        raise HTTPException(
            status_code=404,
            detail="Customer not found.",
        )

    rows = (
        db.query(Order)
        .filter(Order.customer_id == customer_id)
        .all()
    )

    return [
        {
            "id": o.id,
            "item": o.item,
            "delivered_item": o.delivered_item,
            "status": o.status,
            "amount": o.amount,
            "payment_status": o.payment_status,
            "eta": o.eta,
        }
        for o in rows
    ]


# --------------------------------------------------
# CUSTOMER SUPPORT CHAT
# --------------------------------------------------

@app.post("/api/chat")
def chat(
    payload: ChatInput,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    require_supervisor(authorization, db)
    if not payload.message.strip():
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty.",
        )

    if not db.get(Customer, payload.customer_id):
        raise HTTPException(
            status_code=404,
            detail="Unknown demo customer. Choose a seeded customer.",
        )

    try:
        return process_message(
            db,
            payload.customer_id,
            payload.message.strip(),
            payload.conversation_id,
            payload.history,
            payload.slots,
        )
    except HTTPException:
        raise
    except Exception as exc:
        # Keep detailed exceptions in the backend terminal.
        print(f"Support workflow error: {type(exc).__name__}: {exc}")

        raise HTTPException(
            status_code=500,
            detail="The support workflow encountered an error. Check the backend terminal.",
        ) from exc


# --------------------------------------------------
# SUPPORT TICKET QUEUE
# --------------------------------------------------

@app.get("/api/tickets")
def tickets(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    require_supervisor(authorization, db)
    rows = (
        db.query(Ticket)
        .order_by(Ticket.created_at.desc())
        .all()
    )

    return [
        {
            "id": t.id,
            "customer_id": t.customer_id,
            "issue": t.issue,
            "category": t.category,
            "priority": t.priority,
            "team": t.team,
            "status": t.status,
            "sla_minutes": t.sla_minutes,
            "created_at": (
                t.created_at.isoformat()
                if t.created_at
                else None
            ),
            "human_takeover": t.human_takeover,
        }
        for t in rows
    ]


# --------------------------------------------------
# TICKET LIFECYCLE / HUMAN TAKEOVER
# --------------------------------------------------

@app.patch("/api/tickets/{ticket_id}")
def update_ticket(
    ticket_id: str,
    payload: TicketUpdate,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    require_supervisor(authorization, db)
    status_by_key = {
        status.casefold(): status
        for status in (
            "Opened",
            "Assigned",
            "Pending customer",
            "In Progress",
            "Resolved",
            "Closed",
        )
    }
    normalized_status = status_by_key.get(payload.status.strip().casefold())
    if not normalized_status:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid ticket status. Allowed values: {sorted(status_by_key.values())}",
        )

    ticket = db.get(Ticket, ticket_id)

    if not ticket:
        raise HTTPException(
            status_code=404,
            detail="Ticket not found.",
        )

    ticket.status = normalized_status

    if normalized_status == "Assigned":
        ticket.human_takeover = True

    db.commit()
    db.refresh(ticket)
    customer = db.get(Customer, ticket.customer_id)
    if customer and customer.email:
        send_notification(
            customer.email,
            f"Ticket {ticket.id} status update",
            f"Your ticket status is now {ticket.status}.",
        )

    return {
        "ok": True,
        "id": ticket.id,
        "status": ticket.status,
        "human_takeover": ticket.human_takeover,
    }


# --------------------------------------------------
# SUPERVISOR ANALYTICS
# --------------------------------------------------

@app.get("/api/analytics")
def analytics(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    require_supervisor(authorization, db)
    total = db.query(Conversation).count()
    tickets_total = db.query(Ticket).count()

    escalated = (
        db.query(Conversation)
        .filter(Conversation.outcome == "escalated")
        .count()
    )

    action_taken = (
        db.query(Conversation)
        .filter(Conversation.outcome == "action_taken")
        .count()
    )

    agent_events = db.query(AgentEvent).count()
    customer_count = db.query(Customer).count()
    order_count = db.query(Order).count()

    return {
        "conversations": total,
        "tickets": tickets_total,
        "escalations": escalated,
        "actions_taken": action_taken,
        "agent_events": agent_events,
        "customers": customer_count,
        "orders": order_count,
        "resolution_rate": (
            round(max(0, total - escalated) / total * 100, 1)
            if total
            else 0
        ),
        "response_version": "response-v2",
        "prompt_version": "prompt-v2",
    }


# --------------------------------------------------
# AGENT EXECUTION EVENTS
# --------------------------------------------------

@app.get("/api/events")
def events(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    require_supervisor(authorization, db)
    rows = (
        db.query(AgentEvent)
        .order_by(AgentEvent.id.desc())
        .limit(80)
        .all()
    )

    return [
        {
            "id": e.id,
            "conversation_id": e.conversation_id,
            "agent": e.agent,
            "action": e.action,
            "output": e.output,
            "status": e.status,
            "duration_ms": e.duration_ms,
            "correlation_id": e.correlation_id,
            "created_at": (
                e.created_at.isoformat()
                if e.created_at
                else None
            ),
        }
        for e in rows
    ]


# --------------------------------------------------
# KNOWLEDGE BASE
# --------------------------------------------------

@app.get("/api/knowledge")
def knowledge(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    require_supervisor(authorization, db)
    from rag.retrieval import load_articles

    return load_articles()


# --------------------------------------------------
# AUTHENTICATION
# --------------------------------------------------

@app.post("/api/auth/register")
def register(payload: RegisterInput, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    if db.query(UserAccount).filter(UserAccount.email == email).first():
        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists.",
        )

    customer_number = 1
    while db.get(Customer, f"C{customer_number:03d}"):
        customer_number += 1
    customer = Customer(
        id=f"C{customer_number:03d}",
        name=payload.name.strip(),
        email=email,
        city=payload.city.strip() or "Mumbai",
        tier="Standard",
        account_status="Active",
    )
    db.add(customer)
    db.flush()

    account = UserAccount(
        customer_id=customer.id,
        email=email,
        password_hash=hash_password(payload.password),
        role="customer",
        is_active=True,
    )
    db.add(account)
    db.commit()
    db.refresh(account)

    return {
        "access_token": _encode_token(account),
        "token_type": "bearer",
        "customer": {
            "id": customer.id,
            "name": customer.name,
            "email": customer.email,
            "city": customer.city,
            "tier": customer.tier,
        },
    }


@app.post("/api/auth/login")
def login(payload: LoginInput, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    account = db.query(UserAccount).filter(UserAccount.email == email).first()
    if (
        not account
        or not account.is_active
        or not verify_password(payload.password, account.password_hash)
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password.",
        )

    customer = db.get(Customer, account.customer_id)
    if not customer:
        raise HTTPException(
            status_code=401,
            detail="Customer account is no longer available.",
        )

    return {
        "access_token": _encode_token(account),
        "token_type": "bearer",
        "customer": {
            "id": customer.id,
            "name": customer.name,
            "email": customer.email,
            "city": customer.city,
            "tier": customer.tier,
        },
    }


@app.post("/api/auth/supervisor/login")
def supervisor_login(payload: SupervisorLoginInput):
    configured_email = os.getenv("SUPERVISOR_EMAIL", "").strip().lower()
    configured_password = os.getenv("SUPERVISOR_PASSWORD", "")
    if (
        not configured_email
        or not configured_password
        or not hmac.compare_digest(payload.email.strip().lower(), configured_email)
        or not hmac.compare_digest(payload.password, configured_password)
    ):
        raise HTTPException(status_code=401, detail="Invalid supervisor credentials.")
    return {
        "access_token": _encode_supervisor_token(),
        "token_type": "bearer",
        "role": "supervisor",
    }


@app.get("/api/auth/me")
def current_customer(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    _, customer = require_customer(authorization, db)
    return {
        "id": customer.id,
        "name": customer.name,
        "email": customer.email,
        "city": customer.city,
        "tier": customer.tier,
    }


@app.get("/api/my/orders")
def my_orders(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    _, customer = require_customer(authorization, db)
    rows = (
        db.query(Order)
        .filter(Order.customer_id == customer.id)
        .all()
    )
    return [
        {
            "id": order.id,
            "item": order.item,
            "delivered_item": order.delivered_item,
            "status": order.status,
            "amount": order.amount,
            "payment_status": order.payment_status,
            "courier": order.courier,
            "eta": order.eta,
        }
        for order in rows
    ]


@app.post("/api/my/chat")
def my_chat(
    payload: ChatInput,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    _, customer = require_customer(authorization, db)
    if not payload.message.strip():
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty.",
        )
    try:
        # The authenticated identity determines the customer.
        # Ignore any customer_id supplied in the request body.
        return process_message(
            db,
            customer.id,
            payload.message.strip(),
            payload.conversation_id,
            payload.history,
            payload.slots,
        )
    except HTTPException:
        raise
    except Exception as exc:
        print(
            f"Authenticated support workflow error: "
            f"{type(exc).__name__}: {exc}"
        )
        raise HTTPException(
            status_code=500,
            detail=(
                "The support workflow encountered an error. "
                "Check the backend terminal."
            ),
        ) from exc


# --------------------------------------------------
# ROOT
# --------------------------------------------------

@app.get("/")
def root():
    return {
        "service": "AegisSupport API",
        "docs": "/docs",
        "health": "/api/health",
    }
