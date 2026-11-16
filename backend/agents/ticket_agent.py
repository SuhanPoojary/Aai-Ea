import time
import os
import re
from .common import event
from mcp_server.business_tools import create_ticket
from db.models import Customer, Ticket
from notifications import send_notification


def _ticket_data(ticket):
    return {
        "id": ticket.id,
        "customer_id": ticket.customer_id,
        "order_id": ticket.order_id,
        "issue": ticket.issue,
        "category": ticket.category,
        "priority": ticket.priority,
        "team": ticket.team,
        "status": ticket.status,
        "sla_minutes": ticket.sla_minutes,
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        "human_takeover": ticket.human_takeover,
    }


def lookup_tickets(db, customer_id, message="", ticket_id=None, order_id=None):
    """Return only the authenticated customer's freshly persisted ticket records."""
    rows = db.query(Ticket).filter(Ticket.customer_id == customer_id).order_by(
        Ticket.created_at.desc()
    ).all()
    requested_ticket = (ticket_id or "").upper()
    requested_order = (order_id or "").upper()
    if requested_ticket:
        rows = [ticket for ticket in rows if ticket.id.upper() == requested_ticket]
    elif requested_order:
        rows = [
            ticket for ticket in rows
            if (
                ticket.order_id == requested_order
                or requested_order in (ticket.issue or "").upper()
            )
        ]
    else:
        words = {
            word.lower()
            for word in re.findall(r"[a-zA-Z0-9]+", message or "")
            if len(word) > 3
        } - {"ticket", "status", "update", "issue", "complaint", "about", "what", "now"}
        if words:
            scored = [
                (
                    sum(word in (ticket.issue or "").lower() for word in words),
                    ticket,
                )
                for ticket in rows
            ]
            relevant = [ticket for score, ticket in scored if score]
            if relevant:
                rows = relevant
    return [_ticket_data(ticket) for ticket in rows]


def run(db,customer_id,text,intent,decision):
    t=time.perf_counter()
    if not decision.get('escalate'):
        return None,event("Ticket Generation Agent","Create a ticket only when escalation is required","Not required for this workflow",t,"skipped")
    ticket=create_ticket(
        db,
        customer_id,
        text,
        intent.get('category','other'),
        intent.get('priority','medium'),
        decision['team'],
        decision['sla_minutes'],
        order_id=decision.get("order_id"),
    )
    if not ticket.get("ok") or not ticket.get("ticket_id"):
        return None,event("Ticket Generation Agent","Persist escalated support ticket","Ticket could not be saved",t,"error")
    customer = db.get(Customer, customer_id)
    if customer and customer.email:
        send_notification(
            customer.email,
            f"AegisSupport ticket {ticket['ticket_id']}",
            f"Your issue was escalated to {ticket['team']}. "
            f"Initial response target: {ticket['sla_minutes']} minutes.",
        )
    supervisor_email = os.getenv("SUPERVISOR_EMAIL", "")
    if supervisor_email:
        send_notification(
            supervisor_email,
            f"Escalation {ticket['ticket_id']}",
            f"New {ticket['priority']} priority ticket for team {ticket['team']}.",
        )
    return ticket,event("Ticket Generation Agent","Create structured ticket with team and SLA",f"{ticket['ticket_id']} · {ticket['team']} · SLA {ticket['sla_minutes']} min",t)
