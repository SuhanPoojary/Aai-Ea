from db.database import SessionLocal
from db.models import Ticket
from mcp_server.business_tools import create_ticket
from orchestrator.master_orchestrator import process_message
from fastapi.testclient import TestClient


def _create_ticket(customer_id, issue):
    with SessionLocal() as db:
        result = create_ticket(
            db,
            customer_id,
            issue,
            "order",
            "medium",
            "Customer Support",
            60,
        )
        return result["ticket_id"]


def test_ticket_status_reads_latest_database_value_for_all_statuses():
    statuses = [
        ("Opened", "open and awaiting support review"),
        ("Assigned", "assigned to a support representative"),
        ("Pending customer", "additional information"),
        ("In Progress", "working on your issue"),
        ("Resolved", "marked as resolved"),
        ("Closed", "ticket has been closed"),
    ]

    for index, (status, expected) in enumerate(statuses):
        ticket_id = _create_ticket("C002", f"Synthetic status issue {index} ORD12006")
        with SessionLocal() as db:
            ticket = db.get(Ticket, ticket_id)
            ticket.status = status
            db.commit()
            result = process_message(
                db,
                "C002",
                f"What is the status of {ticket_id}?",
            )

        assert result["ticket"]["id"] == ticket_id
        assert result["ticket"]["status"] == status
        assert expected in result["reply"]


def test_multiple_tickets_require_clarification_and_order_lookup_is_scoped():
    first = _create_ticket("C003", "Delivery issue for ORD44100")
    second = _create_ticket("C003", "Payment issue for ORD44100")

    with SessionLocal() as db:
        ambiguous = process_message(db, "C003", "Any update on my complaint?")
        exact = process_message(db, "C003", f"Status of {second}")
        foreign = process_message(db, "C004", f"Status of {first}")

    assert first in ambiguous["reply"] and second in ambiguous["reply"]
    assert exact["ticket"]["id"] == second
    assert "couldn't find a support ticket" in foreign["reply"]


def test_follow_up_uses_ticket_context_without_stale_status():
    ticket_id = _create_ticket("C005", "Synthetic unresolved complaint")
    with SessionLocal() as db:
        first = process_message(
            db,
            "C005",
            f"What is the status of {ticket_id}?",
            conversation_id="CONV-TICKET-FOLLOW-UP",
        )
        ticket = db.get(Ticket, ticket_id)
        ticket.status = "Resolved"
        db.commit()
        second = process_message(
            db,
            "C005",
            "Is it resolved now?",
            conversation_id="CONV-TICKET-FOLLOW-UP",
            history=[],
            slots=first["memory"]["slots"],
        )

    assert first["ticket"]["status"] != second["ticket"]["status"]
    assert second["ticket"]["status"] == "Resolved"
    assert "marked as resolved" in second["reply"]


def test_supervisor_status_update_accepts_in_progress_and_pending_customer():
    from main import app

    ticket_id = _create_ticket("C006", "Supervisor lifecycle issue")
    client = TestClient(app)
    login = client.post(
        "/api/auth/supervisor/login",
        json={
            "email": "supervisor@example.test",
            "password": "TestSupervisor!123",
        },
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    for requested, canonical in (
        ("In Progress", "In Progress"),
        ("Pending Customer", "Pending customer"),
        ("Resolved", "Resolved"),
    ):
        response = client.patch(
            f"/api/tickets/{ticket_id}",
            headers=headers,
            json={"status": requested},
        )
        assert response.status_code == 200
        assert response.json()["status"] == canonical

    with SessionLocal() as db:
        assert db.get(Ticket, ticket_id).status == "Resolved"
