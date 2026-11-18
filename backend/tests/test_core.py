from fastapi.testclient import TestClient

from db.database import SessionLocal
from db.models import ConversationState, ReturnRequest, UserAccount
from mcp_server.business_tools import initiate_return
from agents.reviewer_agent import run as review_plan


def test_return_request_is_persisted_and_deduplicated():
    with SessionLocal() as db:
        first = initiate_return(db, "C001", "ORD12345", "Wrong item")
        second = initiate_return(db, "C001", "ORD12345", "Wrong item")
        assert first["ok"] is True
        assert second["ok"] is False
        assert db.query(ReturnRequest).filter_by(order_id="ORD12345").count() == 1


def test_reviewer_rejects_unsupported_and_ineligible_actions():
    result, trace = review_plan(
        "refund this order",
        {"intent": "refund", "risk": "none", "priority": "medium"},
        {
            "customer_found": True,
            "customer_id": "C001",
            "ownership_verified": True,
            "order": {"id": "ORD12345", "status": "delivered", "item": "x", "delivered_item": "x"},
        },
        {"summary": "bad", "steps": [], "actions": ["initiate_refund"], "confidence": 1},
    )
    assert result["decision"] == "REJECTED"
    assert result["approved_actions"] == []
    assert trace["agent"] == "Reviewer Agent"


def test_api_authorization_and_supervisor_role():
    client = TestClient(__import__("main").app)
    assert client.get("/api/customers").status_code == 401
    customer_login = client.post(
        "/api/auth/login",
        json={"email": "aarav@example.test", "password": "Demo@12345"},
    )
    assert customer_login.status_code == 200
    customer_headers = {"Authorization": f"Bearer {customer_login.json()['access_token']}"}
    assert client.get("/api/customers", headers=customer_headers).status_code == 403
    supervisor_login = client.post(
        "/api/auth/supervisor/login",
        json={"email": "supervisor@example.test", "password": "TestSupervisor!123"},
    )
    assert supervisor_login.status_code == 200
    supervisor_headers = {"Authorization": f"Bearer {supervisor_login.json()['access_token']}"}
    assert client.get("/api/customers", headers=supervisor_headers).status_code == 200
    assert client.get("/api/orders/C002", headers=customer_headers).status_code == 403


def test_authenticated_chat_contains_reviewer_and_response_metadata():
    client = TestClient(__import__("main").app)
    login = client.post(
        "/api/auth/login",
        json={"email": "aarav@example.test", "password": "Demo@12345"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    response = client.post(
        "/api/my/chat",
        headers=headers,
        json={"message": "What is the status of ORD12345?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert any(item["agent"] == "Reviewer Agent" for item in body["trace"])
    assert body["response_metadata"]["response_version"] == "response-v2"


def test_ticket_status_reply_identifies_ticket_and_pending_status():
    from orchestrator.master_orchestrator import ticket_status_reply

    reply = ticket_status_reply({
        "id": "TCK-TEST1",
        "status": "Pending customer",
    })
    assert reply == (
        "Ticket TCK-TEST1 status: Pending customer. "
        "Our support team is waiting for additional information from you."
    )


def test_memory_restores_and_clears_pending_clarification():
    from agents.memory_agent import run as memory_run, save_state

    conversation_id = "CONV-MISSING-ORDER"
    with SessionLocal() as db:
        save_state(
            db,
            "C001",
            conversation_id,
            category="payment_failure",
            last_action="awaiting_order_selection",
            pending_clarification="order_id",
            history=[{"role": "assistant", "content": "Which order should I check?"}],
        )
        result, _ = memory_run(
            [],
            "yoga",
            {},
            db=db,
            customer_id="C001",
            conversation_id=conversation_id,
            intent="payment_failure",
        )
        assert result["slots"]["pending_clarification"] == "order_id"
        assert result["slots"]["category"] == "payment_failure"
        assert result["slots"]["last_action"] == "awaiting_order_selection"

        save_state(
            db,
            "C001",
            conversation_id,
            order_id="ORD12345",
            pending_clarification="",
        )
        db.expire_all()
        persisted = db.query(ConversationState).filter_by(
            conversation_id=conversation_id,
            customer_id="C001",
        ).first()
        assert persisted.pending_clarification == ""
        cleared = memory_run(
            [],
            "check that order",
            {},
            db=db,
            customer_id="C001",
            conversation_id=conversation_id,
        )[0]
        assert "pending_clarification" not in cleared["slots"]
