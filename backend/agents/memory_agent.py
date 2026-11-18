import json
import re
import time
from datetime import datetime, timezone
from .common import event
from db.models import ConversationState


def load_state(db, customer_id, conversation_id):
    if not db or not conversation_id:
        return None
    return db.query(ConversationState).filter(
        ConversationState.conversation_id == conversation_id,
        ConversationState.customer_id == customer_id,
    ).first()


def save_state(
    db,
    customer_id,
    conversation_id,
    *,
    intent=None,
    order_id=None,
    ticket_id=None,
    category=None,
    last_action=None,
    pending_clarification=None,
    history=None,
):
    if not db or not conversation_id:
        return
    state = load_state(db, customer_id, conversation_id)
    if not state:
        state = ConversationState(
            conversation_id=conversation_id,
            customer_id=customer_id,
        )
        db.add(state)
    if intent:
        state.previous_intent = state.current_intent
        state.current_intent = intent
    if order_id:
        state.selected_order_id = order_id
    if ticket_id:
        state.selected_ticket_id = ticket_id
    if category:
        state.active_issue_category = category
    if last_action is not None:
        state.last_action = last_action
    if pending_clarification is not None:
        state.pending_clarification = pending_clarification
    if history is not None:
        state.recent_context = json.dumps(history[-8:], ensure_ascii=True)
    state.updated_at = datetime.now(timezone.utc)
    db.commit()
    return state


def run(history, text, slots, db=None, customer_id=None, conversation_id=None, intent=None):
    t=time.perf_counter(); new=dict(slots or {})
    persisted = load_state(db, customer_id, conversation_id)
    if persisted:
        if persisted.selected_order_id:
            new.setdefault("order_id", persisted.selected_order_id)
        if persisted.selected_ticket_id:
            new.setdefault("ticket_id", persisted.selected_ticket_id)
        if persisted.pending_clarification:
            new.setdefault(
                "pending_clarification",
                persisted.pending_clarification
            )
        if persisted.active_issue_category:
            new.setdefault("category", persisted.active_issue_category)
        if persisted.last_action:
            new.setdefault("last_action", persisted.last_action)
    import re
    m=re.search(r'\bORD[A-Z0-9-]*\d[A-Z0-9-]*\b',text,re.I)
    if m: new['order_id']=m.group(0).upper()
    ticket=re.search(r'\bTCK-[A-Z0-9]+\b',text,re.I)
    if ticket: new['ticket_id']=ticket.group(0).upper()
    hist=(history or [])[-8:]
    updated_history = hist + [{"role":"user","content":text}]
    if db and customer_id and conversation_id:
        save_state(
            db,
            customer_id,
            conversation_id,
            order_id=new.get("order_id"),
            ticket_id=new.get("ticket_id"),
            intent=intent,
            history=updated_history,
        )
    return {
        "history": updated_history,
        "slots": new,
        "state": persisted,
        "turn": len(history or [])//2+1,
    }, event(
        "Memory Agent",
        "Load durable customer conversation state and update references",
        f"Turn {len(history or [])//2+1} · order {new.get('order_id','none')} · ticket {new.get('ticket_id','none')}",
        t,
    )
