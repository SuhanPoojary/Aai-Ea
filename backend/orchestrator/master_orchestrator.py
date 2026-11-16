import os
import uuid, time
import re
from sqlalchemy.orm import Session
from db.models import Conversation, AgentEvent, Order
from agents.guardrail_agent import run as guardrail
from agents.intent_agent import run as intent_run
from agents.context_agent import run as context_run
from agents.memory_agent import run as memory_run
from agents.planner_agent import run as planner_run
from agents.reviewer_agent import run as reviewer_run
from agents.action_agent import run as action_run
from agents.escalation_agent import run as escalation_run
from agents.ticket_agent import run as ticket_run
from agents.ticket_agent import lookup_tickets
from agents.memory_agent import save_state
from agents.response_agent import run as response_run
from agents.knowledge_agent import run as knowledge_run


def is_list_orders_request(message: str) -> bool:
    """Recognize requests to list multiple or all of the customer's orders."""
    text = (message or "").lower().strip()
    patterns = [
        r"\blist\s+(all\s+)?(of\s+)?my\s+orders\b",
        r"\bshow\s+(me\s+)?(all\s+)?my\s+orders\b",
        r"\bwhat\s+are\s+my\s+orders\b",
        r"\bdisplay\s+(all\s+)?my\s+orders\b",
        r"\bmy\s+orders\b",
        r"\border\s+history\b",
        r"\bwhat\s+items\s+(did|have)\s+i\s+order(ed)?\b",
        r"\blist\s+(all\s+)?my\s+items\b",
        r"\btell\s+me\s+(the\s+)?list\s+of\s+items\s+i\s+ordered\b",
        r"\bshow\s+my\s+purchases\b",
        r"\bwhat\s+have\s+i\s+ordered\b",
    ]
    return any(re.search(pattern, text) for pattern in patterns)


def detect_order_id(message):
    match = re.search(
        r"\bORD[A-Z0-9-]*\d[A-Z0-9-]*\b",
        message or "",
        re.IGNORECASE,
    )
    return match.group(0).upper() if match else None


def detect_ticket_id(message):
    match = re.search(r"\bTCK-[A-Z0-9]+\b", message or "", re.IGNORECASE)
    return match.group(0).upper() if match else None


def ticket_status_reply(ticket):
    messages = {
        "Opened": "Your ticket is open and awaiting support review.",
        "Assigned": "Your ticket has been assigned to a support representative.",
        "Pending customer": "We need additional information from you.",
        "In Progress": "Our support team is working on your issue.",
        "Resolved": "Your issue has been marked as resolved by our support team.",
        "Closed": "Your ticket has been closed. Contact support if the issue persists.",
    }
    return messages.get(
        ticket["status"],
        f"Your ticket is currently {ticket['status']}.",
    )


def ticket_status_lookup(
    db,
    customer_id,
    message,
    intent,
    history,
    slots,
):
    if intent.get("intent") != "ticket_status":
        return None

    ticket_id = detect_ticket_id(message) or (slots or {}).get("ticket_id")
    order_id = detect_order_id(message) or (slots or {}).get("order_id")
    if not ticket_id and not order_id:
        for item in reversed(history or []):
            if item.get("role") != "user":
                continue
            ticket_id = detect_ticket_id(item.get("content", ""))
            order_id = order_id or detect_order_id(item.get("content", ""))
            if ticket_id or order_id:
                break

    tickets = lookup_tickets(
        db,
        customer_id,
        message=message,
        ticket_id=ticket_id,
        order_id=order_id,
    )
    if len(tickets) == 1:
        ticket = tickets[0]
        return {
            "reply": ticket_status_reply(ticket),
            "ticket": ticket,
            "tickets": tickets,
            "outcome": "answered",
        }
    if len(tickets) > 1:
        choices = ", ".join(
            f"{ticket['id']} ({ticket['status']})" for ticket in tickets
        )
        return {
            "reply": f"I found multiple support tickets: {choices}. Which ticket would you like an update on?",
            "ticket": None,
            "tickets": tickets,
            "outcome": "answered",
        }
    return {
        "reply": (
            "I couldn't find a support ticket matching that request. "
            "Please provide a ticket ID or tell me which order or issue you mean."
        ),
        "ticket": None,
        "tickets": [],
        "outcome": "answered",
    }


def is_ticket_follow_up(message):
    text = (message or "").lower()
    return (
        re.search(r"\b(status|update|resolved|closed|assigned|progress)\b", text)
        or any(
            phrase in text
            for phrase in (
                "what's the status",
                "whats the status",
                "what about now",
                "any update",
                "has it been resolved",
                "what happened to my complaint",
            )
        )
    )


def is_tracking_request(message, intent):
    text = (message or "").lower()
    label = str(intent.get("intent", "")).lower()
    tracking_words = (
        "track",
        "tracking",
        "where is my order",
        "delivery status",
        "when will it arrive",
        "where is my package",
        "shipment status",
    )
    return (
        any(word in text for word in tracking_words)
        or "track" in label
        or "delivery" in label
        or "shipment" in label
    )


def order_reference_is_ambiguous(message, intent):
    text = (message or "").lower()
    return (
        intent.get("intent") in {
            "order_tracking",
            "wrong_item",
            "cancel_order",
            "refund",
            "refund_issue",
            "payment_failure",
        }
        and not detect_order_id(message)
        and not any(
            phrase in text
            for phrase in ("this order", "that order", "this item", "that item")
        )
    )


def is_order_related_message(message, intent):
    text = (message or "").lower()
    return (
        intent.get("intent") in {
            "order_tracking", "delivery_delay", "wrong_item", "return_request",
            "cancel_order", "refund", "refund_issue", "payment_failure",
        }
        or re.search(
            r"\b(my|an|the)\s+(order|item|package|delivery)\b",
            text,
        )
    )


def clarification_for_missing_order(intent, context):
    if intent.get("intent") not in {
        "payment_failure",
        "return_request",
        "replacement_request",
    } or context.get("order"):
        return None
    orders = context.get("orders") or []
    if len(orders) > 1:
        choices = ", ".join(
            f"{order.get('item', 'item')} ({order.get('id')})"
            for order in orders
        )
        return f"Which order should I check? I found: {choices}."
    if len(orders) == 1:
        return (
            f"Which order should I check? Please confirm order "
            f"{orders[0].get('id')}."
        )
    return "Please share the order ID so I can check the payment or replacement request."


def save_early_reply(
    db,
    conversation_id,
    customer_id,
    message,
    reply,
    intent,
    trace,
    outcome,
):
    conversation = Conversation(
        id=conversation_id + "-" + uuid.uuid4().hex[:6],
        customer_id=customer_id,
        user_text=message,
        assistant_text=reply,
        intent=intent.get("intent", "other"),
        outcome=outcome,
    )
    db.add(conversation)
    for event in trace:
        db.add(
            AgentEvent(
                conversation_id=conversation_id,
                agent=event["agent"],
                action=event["action"],
                output=event["output"],
                status=event.get("status", "success"),
                duration_ms=event.get("duration_ms", 0),
                correlation_id=event.get("correlation_id", conversation_id),
            )
        )
    db.commit()


def load_conversation_history(db, customer_id, conversation_id):
    if not conversation_id:
        return []
    rows = (
        db.query(Conversation)
        .filter(
            Conversation.customer_id == customer_id,
            Conversation.id.like(f"{conversation_id}%"),
        )
        .order_by(Conversation.created_at.asc())
        .limit(12)
        .all()
    )
    history = []
    for row in rows:
        history.extend(
            [
                {"role": "user", "content": row.user_text},
                {"role": "assistant", "content": row.assistant_text},
            ]
        )
    return history[-12:]


def process_message(db: Session, customer_id: str, message: str, conversation_id: str|None=None, history=None, slots=None):
    started = time.perf_counter()
    cid=conversation_id or 'CONV-'+uuid.uuid4().hex[:10].upper(); trace=[]; slots=slots or {}
    persisted_history = load_conversation_history(db, customer_id, conversation_id)
    history = persisted_history or (history or [])
    safe,ev=guardrail(message); trace.append(ev)
    if not safe['safe']:
        reply="I can't help with requests to bypass security or access another customer's information. I can help with your own account or order."
        intent={"intent":"unsafe_request","category":"security","priority":"high","sentiment":"negative","risk":"none","order_id":None}
        trace.append({"agent":"Response Agent","action":"Return safe refusal","output":reply,"duration_ms":0,"status":"blocked"})
        outcome="blocked"; docs=[]; results=[]; ticket=None; decision={"escalate":False,"reasons":[safe['reason']],"decision":"blocked","team":"Security","sla_minutes":5}; ctx={}; plan={"steps":[],"actions":[],"confidence":1}
        mem={"history":history,"slots":slots,"turn":len(history)//2+1}
    else:
        intent,ev=intent_run(message); trace.append(ev)
        mem,ev=memory_run(
            history,
            message,
            slots,
            db=db,
            customer_id=customer_id,
            conversation_id=cid,
            intent=intent.get("intent"),
        ); trace.append(ev)
        state = mem.get("state")
        if (
            state
            and state.selected_ticket_id
            and is_ticket_follow_up(message)
            and not detect_order_id(message)
            and not detect_ticket_id(message)
        ):
            intent.update({
                "intent": "ticket_status",
                "category": "support",
                "priority": "low",
                "risk": "none",
            })
            trace.append({
                "agent": "Master Orchestrator",
                "action": "Route contextual ticket follow-up",
                "output": f"Active ticket {state.selected_ticket_id} selected from durable conversation state.",
                "duration_ms": 0,
                "status": "success",
            })
        status_result = ticket_status_lookup(
            db,
            customer_id,
            message,
            intent,
            history,
            mem.get("slots", slots),
        )
        if status_result:
            trace.append({
                "agent": "Ticket Agent",
                "action": "Read latest customer-owned ticket status",
                "output": (
                    f"Retrieved {len(status_result['tickets'])} current ticket record(s)."
                ),
                "duration_ms": 0,
                "status": "success",
            })
            save_early_reply(
                db,
                cid,
                customer_id,
                message,
                status_result["reply"],
                intent,
                trace,
                status_result["outcome"],
            )
            return {
                "conversation_id": cid,
                "customer_id": customer_id,
                "reply": status_result["reply"],
                "intent": intent,
                "context": {"tickets": status_result["tickets"]},
                "knowledge": [],
                "plan": {
                    "steps": ["Retrieve the latest customer-owned ticket record"],
                    "actions": [],
                    "confidence": 1.0,
                },
                "tool_results": [],
                "decision": {
                    "escalate": False,
                    "decision": "ticket_status_retrieved",
                    "reasons": [],
                    "team": "Customer Support",
                    "sla_minutes": 60,
                },
                "ticket": status_result["ticket"],
                "tickets": status_result["tickets"],
                "trace": trace,
                "memory": {
                    "turn": len(history) // 2 + 1,
                    "slots": mem.get("slots", slots),
                },
                "outcome": status_result["outcome"],
            }
        if is_list_orders_request(message):
            customer_orders = (
                db.query(Order)
                .filter(Order.customer_id == customer_id)
                .order_by(Order.id)
                .all()
            )
            order_data = [
                {
                    "id": order.id,
                    "item": order.item,
                    "status": order.status,
                    "amount": order.amount,
                    "payment_status": order.payment_status,
                    "eta": order.eta,
                    "delivered_item": order.delivered_item,
                }
                for order in customer_orders
            ]
            reply = (
                f"I found {len(order_data)} order"
                f"{'' if len(order_data) == 1 else 's'} in your account."
            )
            intent["intent"] = "list_orders"
            trace.append(
                {
                    "agent": "Master Orchestrator",
                    "action": "Retrieve authenticated order history",
                    "output": f"Retrieved {len(order_data)} order(s).",
                    "duration_ms": 0,
                    "status": "success",
                }
            )
            trace.append(
                {
                    "agent": "Response Agent",
                    "action": "Return order history",
                    "output": reply,
                    "duration_ms": 0,
                    "status": "success",
                }
            )
            save_early_reply(
                db,
                cid,
                customer_id,
                message,
                reply,
                intent,
                trace,
                "answered",
            )
            return {
                "conversation_id": cid,
                "customer_id": customer_id,
                "reply": reply,
                "intent": intent,
                "context": {"orders": order_data},
                "knowledge": [],
                "plan": {
                    "steps": ["Retrieve authenticated order history"],
                    "actions": [],
                    "confidence": 1.0,
                },
                "tool_results": [],
                "decision": {
                    "escalate": False,
                    "reasons": [],
                    "decision": "order_history_retrieved",
                    "team": "Customer Support",
                    "sla_minutes": 60,
                },
                "ticket": None,
                "trace": trace,
                "memory": {
                    "turn": len(history) // 2 + 1,
                    "slots": mem.get("slots", slots),
                },
                "outcome": "answered",
            }
        explicit_order_id = (
            detect_order_id(message) or intent.get("order_id")
        )
        if not explicit_order_id and history:
            previous_user_messages = [
                item.get("content", "")
                for item in reversed(history)
                if item.get("role") == "user"
            ]
            customer_orders = (
                db.query(Order)
                .filter(Order.customer_id == customer_id)
                .all()
            )
            for previous_message in previous_user_messages:
                previous_order_id = detect_order_id(previous_message)
                if previous_order_id:
                    explicit_order_id = previous_order_id
                    break
                previous_lower = previous_message.lower()
                matched_previous_order = next(
                    (
                        order for order in customer_orders
                        if order.item and order.item.lower() in previous_lower
                    ),
                    None,
                )
                if matched_previous_order:
                    explicit_order_id = matched_previous_order.id
                    break
        if not explicit_order_id:
            customer_orders = (
                db.query(Order)
                .filter(Order.customer_id == customer_id)
                .all()
            )
            message_lower = message.lower()
            matched_order = next(
                (
                    order for order in customer_orders
                    if order.item and order.item.lower() in message_lower
                ),
                None,
            )
            if matched_order:
                explicit_order_id = matched_order.id
                intent["intent"] = "order_item_lookup"
                intent["order_id"] = matched_order.id
        intent_name = intent.get("intent", "").lower()
        message_lower = message.lower()
        use_previous_order = (
            intent_name not in {
                "list_orders",
                "order_items",
                "general_question",
                "order_item_lookup",
            }
            and any(
                word in message_lower.split()
                for word in ["it", "its", "that", "this", "there", "them"]
            )
        )
        order_id = explicit_order_id
        if not order_id and use_previous_order:
            order_id = mem.get("slots", {}).get("order_id")
        if order_id:
            order_id = str(order_id).upper()
        ctx,ev=context_run(db,customer_id,order_id,message); trace.append(ev)
        if not order_id:
            candidates = ctx.get("matching_orders") or []
            owned_orders = ctx.get("orders") or []
            if len(candidates) == 1:
                order_id = candidates[0]["id"]
                ctx,ev=context_run(db,customer_id,order_id,message); trace.append(ev)
            elif len(owned_orders) == 1 and is_order_related_message(message, intent):
                order_id = owned_orders[0]["id"]
                ctx,ev=context_run(db,customer_id,order_id,message); trace.append(ev)
        if order_id:
            save_state(
                db,
                customer_id,
                cid,
                order_id=order_id,
                intent=intent.get("intent"),
                category=intent.get("category"),
                history=history,
            )
        if order_id and not ctx.get("order"):
            reply = (
                "I couldn't find that order in your account. Please check "
                "the order ID and try again."
            )
            trace.append(
                {
                    "agent": "Master Orchestrator",
                    "action": "Block unauthorized order lookup",
                    "output": "Order ownership could not be verified.",
                    "duration_ms": 0,
                    "status": "blocked",
                }
            )
            trace.append(
                {
                    "agent": "Response Agent",
                    "action": "Explain order lookup restriction",
                    "output": reply,
                    "duration_ms": 0,
                    "status": "success",
                }
            )
            save_early_reply(
                db,
                cid,
                customer_id,
                message,
                reply,
                intent,
                trace,
                "blocked",
            )
            return {
                "conversation_id": cid,
                "customer_id": customer_id,
                "reply": reply,
                "intent": intent,
                "context": ctx,
                "knowledge": [],
                "plan": {"steps": [], "actions": [], "confidence": 1},
                "tool_results": [],
                "decision": {
                    "escalate": False,
                    "decision": "blocked",
                    "reasons": ["Order ownership could not be verified."],
                },
                "ticket": None,
                "trace": trace,
                "memory": {
                    "turn": len(history) // 2 + 1,
                    "slots": mem.get("slots", slots),
                },
                "outcome": "blocked",
            }
        missing_order_reply = clarification_for_missing_order(intent, ctx)
        if missing_order_reply:
            trace.append({
                "agent": "Master Orchestrator",
                "action": "Request missing order reference",
                "output": missing_order_reply,
                "duration_ms": 0,
                "status": "waiting_for_input",
            })
            save_early_reply(
                db,
                cid,
                customer_id,
                message,
                missing_order_reply,
                intent,
                trace,
                "waiting_for_input",
            )
            return {
                "conversation_id": cid,
                "customer_id": customer_id,
                "reply": missing_order_reply,
                "intent": intent,
                "context": ctx,
                "knowledge": [],
                "plan": {"steps": ["Request an order reference"], "actions": [], "confidence": 1},
                "tool_results": [],
                "decision": {
                    "escalate": False,
                    "decision": "waiting_for_input",
                    "reasons": ["Order reference is required."],
                    "team": "Customer Support",
                    "sla_minutes": 60,
                },
                "ticket": None,
                "trace": trace,
                "memory": {
                    "turn": len(history) // 2 + 1,
                    "slots": mem.get("slots", slots),
                },
                "outcome": "waiting_for_input",
            }
        if intent.get("intent") in {
            "list_orders",
            "order_items",
            "order_tracking",
        }:
            docs = []
            trace.append(
                {
                    "agent": "Knowledge Retrieval Agent",
                    "action": (
                        "Skip policy retrieval for database-backed order query"
                    ),
                    "output": (
                        "The request can be answered from verified order records."
                    ),
                    "duration_ms": 0,
                    "status": "skipped",
                }
            )
        else:
            retrieval_query = (
                f"{intent.get('intent', '')} "
                f"{intent.get('category', '')} {message}"
            )
            docs, ev = knowledge_run(retrieval_query, intent=intent.get("intent"))
            trace.append(ev)
        plan,ev=planner_run(message,intent,ctx,docs); trace.append(ev)
        if order_reference_is_ambiguous(message, intent) and not ctx.get("order"):
            plan["actions"] = []
        review,ev=reviewer_run(message,intent,ctx,plan); trace.append(ev)
        plan["actions"] = review["approved_actions"]
        if review["decision"] == "REJECTED":
            results=[{"tool":"reviewer","ok":False,"message":review["reason"],"correlation_id":cid}]
            trace.append({"agent":"Action / MCP Tools Agent","action":"Skip tools because the plan was rejected","output":review["reason"],"duration_ms":0,"status":"blocked","correlation_id":cid})
        else:
            results,ev=action_run(db,customer_id,order_id,plan,correlation_id=cid); trace.append(ev)
        decision,ev=escalation_run(intent,plan,results); trace.append(ev)
        decision["order_id"] = order_id
        ticket,ev=ticket_run(db,customer_id,message,intent,decision); trace.append(ev)
        if ticket and ticket.get("ticket_id"):
            save_state(
                db,
                customer_id,
                cid,
                intent=intent.get("intent"),
                order_id=order_id,
                ticket_id=ticket["ticket_id"],
                category=intent.get("category"),
                last_action="ticket_created",
                history=history,
            )
        answer,ev=response_run(message,intent,ctx,docs,results,decision,ticket,history=history); trace.append(ev); reply=answer['reply']; docs=answer['sources']; outcome='escalated' if decision['escalate'] else ('action_taken' if any(r.get('ok') for r in results) else 'answered')
    conv=Conversation(
        id=cid+'-'+uuid.uuid4().hex[:6],
        customer_id=customer_id,
        user_text=message,
        assistant_text=reply,
        intent=intent.get('intent','other'),
        outcome=outcome,
        response_version="response-v2",
        prompt_version="prompt-v2",
        llm_provider="groq" if os.getenv("GROQ_API_KEY") else "deterministic",
        model_name=os.getenv("GROQ_MODEL", "") if os.getenv("GROQ_API_KEY") else "",
        execution_duration_ms=round((time.perf_counter() - started) * 1000),
    )
    db.add(conv)
    for e in trace:
        db.add(AgentEvent(conversation_id=cid,agent=e['agent'],action=e['action'],output=e['output'],status=e.get('status','success'),duration_ms=e.get('duration_ms',0),correlation_id=e.get("correlation_id", cid)))
    db.commit()
    return {
        "conversation_id": cid,
        "customer_id": customer_id,
        "reply": reply,
        "intent": intent,
        "context": ctx,
        "knowledge": docs,
        "plan": plan,
        "tool_results": results,
        "decision": decision,
        "ticket": ticket,
        "trace": trace,
        "memory": {"turn": len(history)//2+1, "slots": mem.get("slots", slots)},
        "outcome": outcome,
        "response_metadata": {
            "response_version": "response-v2",
            "prompt_version": "prompt-v2",
            "llm_provider": "groq" if os.getenv("GROQ_API_KEY") else "deterministic",
            "model_name": os.getenv("GROQ_MODEL", "") if os.getenv("GROQ_API_KEY") else "",
            "execution_duration_ms": round((time.perf_counter() - started) * 1000),
        },
    }
