import time
import os
from .common import event
from mcp_server.business_tools import create_ticket
from db.models import Customer
from notifications import send_notification

def run(db,customer_id,text,intent,decision):
    t=time.perf_counter()
    if not decision.get('escalate'):
        return None,event("Ticket Generation Agent","Create a ticket only when escalation is required","Not required for this workflow",t,"skipped")
    ticket=create_ticket(db,customer_id,text,intent.get('category','other'),intent.get('priority','medium'),decision['team'],decision['sla_minutes'])
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
