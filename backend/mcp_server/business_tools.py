from sqlalchemy.orm import Session
from db.models import Order, Ticket, ReturnRequest
from datetime import datetime, timezone
import uuid

def get_order(db: Session, customer_id: str, order_id: str):
    order=db.get(Order,order_id)
    if not order or order.customer_id != customer_id: return {"ok":False,"message":"Order not found for this customer."}
    return {"ok":True,"order_id":order.id,"item":order.item,"delivered_item":order.delivered_item,"status":order.status,"amount":order.amount,"payment_status":order.payment_status,"eta":order.eta,"courier":order.courier}

def check_refund_eligibility(db: Session, customer_id: str, order_id: str):
    order=db.get(Order,order_id)
    if not order or order.customer_id!=customer_id: return {"ok":False,"eligible":False,"message":"Order not found for this customer."}
    eligible=order.payment_status=='debited_not_confirmed' or order.status in ('delivered','processing','payment_failed')
    return {"ok":True,"eligible":eligible,"order_id":order.id,"amount":order.amount,"message":"Eligible for review; final approval follows policy." if eligible else "Not eligible under the demo rules."}

def initiate_return(db: Session, customer_id: str, order_id: str, reason: str = "Wrong or damaged item"):
    order=db.get(Order,order_id)
    if not order or order.customer_id!=customer_id: return {"ok":False,"message":"Order not found for this customer."}
    if order.status!='delivered' or not order.delivered_item or order.delivered_item==order.item: return {"ok":False,"message":"Demo return requires a delivered item mismatch or an eligible delivered order."}
    existing = db.query(ReturnRequest).filter(
        ReturnRequest.customer_id == customer_id,
        ReturnRequest.order_id == order_id,
        ReturnRequest.status.in_(("Requested", "Approved", "In Progress")),
    ).first()
    if existing:
        return {"ok":False,"message":"A return request already exists for this order.","return_id":existing.id,"order_id":order.id}
    return_id = "RET-" + uuid.uuid4().hex[:10].upper()
    request = ReturnRequest(
        id=return_id,
        order_id=order.id,
        customer_id=customer_id,
        reason=reason[:1000],
        status="Requested",
        resolution="Replacement",
        created_at=datetime.now(timezone.utc),
    )
    try:
        db.add(request)
        db.commit()
    except Exception:
        db.rollback()
        return {"ok":False,"message":"Return request could not be saved."}
    return {"ok":True,"return_id":return_id,"order_id":order.id,"message":"Return request created. Replacement is subject to warehouse confirmation."}

def cancel_order(db: Session, customer_id: str, order_id: str):
    order=db.get(Order,order_id)
    if not order or order.customer_id!=customer_id: return {"ok":False,"message":"Order not found for this customer."}
    if order.status!='processing': return {"ok":False,"message":f"Order cannot be cancelled because current status is {order.status}."}
    order.status='cancelled'; db.commit()
    return {"ok":True,"order_id":order.id,"status":"cancelled","message":"Order cancelled in demo database."}

def check_account(db: Session, customer_id: str):
    from db.models import Customer
    c=db.get(Customer,customer_id)
    return {"ok":bool(c),"customer_id":customer_id,"account_status":c.account_status if c else "unknown","tier":c.tier if c else "unknown"}

def create_ticket(
    db: Session,
    customer_id: str,
    issue: str,
    category: str,
    priority: str,
    team: str,
    sla_minutes: int,
    order_id: str | None = None,
):
    normalized_issue = " ".join((issue or "").lower().split())
    existing = db.query(Ticket).filter(
        Ticket.customer_id == customer_id,
        Ticket.category == category,
        Ticket.status.in_(("Opened", "Assigned", "Pending customer")),
    ).all()
    for ticket in existing:
        existing_issue = " ".join((ticket.issue or "").lower().split())
        stop_words = {"a", "an", "and", "for", "issue", "order", "the", "with"}
        issue_tokens = set(normalized_issue.split()) - stop_words
        existing_tokens = set(existing_issue.split()) - stop_words
        shared_issue_ratio = (
            len(issue_tokens & existing_tokens) / min(len(issue_tokens), len(existing_tokens))
            if issue_tokens and existing_tokens
            else 0
        )
        if existing_issue == normalized_issue or (
            normalized_issue and ticket.issue and
            any(token.startswith("ord") for token in normalized_issue.split())
            and any(token.startswith("ord") for token in existing_issue.split())
            and next((token for token in normalized_issue.split() if token.startswith("ord")), None)
            == next((token for token in existing_issue.split() if token.startswith("ord")), None)
            and shared_issue_ratio >= 0.6
            and (not order_id or ticket.order_id == order_id)
        ):
            return {
                "ok": True,
                "ticket_id": ticket.id,
                "team": ticket.team,
                "priority": ticket.priority,
                "sla_minutes": ticket.sla_minutes,
                "status": ticket.status,
                "duplicate": True,
            }
    tid='TCK-'+uuid.uuid4().hex[:7].upper()
    ticket=Ticket(
        id=tid,
        customer_id=customer_id,
        order_id=order_id,
        issue=issue,
        category=category,
        priority=priority,
        team=team,
        sla_minutes=sla_minutes,
        status='Opened',
        created_at=datetime.now(timezone.utc),
        human_takeover=False,
    )
    try:
        db.add(ticket)
        db.commit()
    except Exception:
        db.rollback()
        return {"ok": False, "message": "Support ticket could not be saved."}
    return {"ok":True,"ticket_id":tid,"team":team,"priority":priority,"sla_minutes":sla_minutes,"status":"Opened"}
