from orchestrator.master_orchestrator import process_message
from db.database import SessionLocal


def test_general_order_help_disambiguates_owned_orders():
    with SessionLocal() as db:
        result = process_message(db, "C001", "Can you help with my order?")

    assert result["decision"]["escalate"] is False
    assert "Noise-Cancelling Headphones X2" in result["reply"]
    assert "Yoga Mat Pro" in result["reply"]
    assert result["ticket"] is None


def test_tracking_without_id_uses_owned_order_choices():
    with SessionLocal() as db:
        result = process_message(db, "C001", "Where is my order?")

    assert result["intent"]["intent"] == "order_tracking"
    assert result["decision"]["escalate"] is False
    assert "ORD12345" in result["reply"]
    assert "ORD33410" in result["reply"]


def test_follow_up_reuses_verified_order_context():
    conversation_id = "CONV-FOLLOW-UP-TEST"
    with SessionLocal() as db:
        first = process_message(
            db,
            "C002",
            "Can you check ORD12006?",
            conversation_id=conversation_id,
        )
        second = process_message(
            db,
            "C002",
            "When will it arrive?",
            conversation_id=conversation_id,
            history=[],
            slots=first["memory"]["slots"],
        )

    assert first["context"]["order"]["id"] == "ORD12006"
    assert second["context"]["order"]["id"] == "ORD12006"
    assert "ORD12006" in second["reply"]
    assert second["decision"]["escalate"] is False


def test_frustration_receives_empathetic_fallback():
    with SessionLocal() as db:
        result = process_message(
            db,
            "C001",
            "I'm really frustrated with this experience.",
        )

    assert "frustrating" in result["reply"].lower()
    assert "reviewer agent" not in result["reply"].lower()
    assert "database" not in result["reply"].lower()


def test_product_name_lookup_uses_owned_order_data():
    with SessionLocal() as db:
        result = process_message(
            db,
            "C001",
            "What is the status of my Yoga Mat Pro order?",
        )

    assert result["context"]["order"]["id"] == "ORD33410"
    assert "processing" in result["reply"].lower()
    assert "ORD33410" in result["reply"]


def test_explicit_human_request_creates_escalation():
    with SessionLocal() as db:
        result = process_message(
            db,
            "C001",
            "Please let me speak to a human agent.",
        )

    assert result["intent"]["intent"] == "human_assistance"
    assert result["decision"]["escalate"] is True
    assert result["ticket"]["team"] == "Customer Support"
    assert "human" in result["reply"].lower()


def test_server_history_is_used_when_client_history_is_empty():
    conversation_id = "CONV-SERVER-HISTORY-TEST"
    with SessionLocal() as db:
        first = process_message(
            db,
            "C001",
            "Check my Noise-Cancelling Headphones X2 order.",
            conversation_id=conversation_id,
        )
        second = process_message(
            db,
            "C001",
            "Has it shipped?",
            conversation_id=conversation_id,
            history=[],
            slots={},
        )

    assert first["context"]["order"]["id"] == "ORD12345"
    assert second["context"]["order"]["id"] == "ORD12345"
    assert "ORD12345" in second["reply"]


def test_refund_policy_fresh_conversation_uses_policy_content():
    with SessionLocal() as db:
        result = process_message(db, "C001", "What is your refund policy?")

    reply = result["reply"].lower()
    assert result["intent"]["intent"] == "refund_policy"
    assert result["knowledge"][0]["id"] == "KB-108"
    assert "order and payment status" in reply
    assert "eligibility" in reply
    assert "money has already been transferred" in reply
    assert "ticket" not in reply


def test_damaged_product_follow_up_keeps_kb_next_steps():
    conversation_id = "CONV-DAMAGED-FOLLOW-UP-TEST"
    with SessionLocal() as db:
        first = process_message(
            db,
            "C001",
            "My product arrived damaged. What should I do?",
            conversation_id=conversation_id,
        )
        second = process_message(
            db,
            "C001",
            "It is order ORD12345.",
            conversation_id=conversation_id,
            history=[],
            slots=first["memory"]["slots"],
        )

    assert first["intent"]["intent"] == "wrong_item"
    assert first["knowledge"][0]["id"] == "KB-101"
    assert "return request" in first["reply"].lower()
    assert "warehouse confirmation" in first["reply"].lower()
    assert "ORD12345" in second["reply"]
