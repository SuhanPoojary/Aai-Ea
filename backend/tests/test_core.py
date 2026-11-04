from fastapi.testclient import TestClient

from db.database import SessionLocal
from db.models import ReturnRequest, UserAccount
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
