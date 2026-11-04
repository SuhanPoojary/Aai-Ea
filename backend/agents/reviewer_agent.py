import time

from schemas import ActionPlan, CustomerContext, IntentResult, ReviewResult
from .common import event

SUPPORTED_ACTIONS = {
    "get_order",
    "check_refund_eligibility",
    "initiate_return",
    "cancel_order",
    "check_account",
}


def run(text, intent, context, plan):
    started = time.perf_counter()
    parsed_intent = IntentResult.model_validate(intent)
    parsed_context = CustomerContext.model_validate(context)
    parsed_plan = ActionPlan.model_validate(plan)
    actions = list(dict.fromkeys(parsed_plan.actions))

    if any(action not in SUPPORTED_ACTIONS for action in actions):
        reason = "The plan contains an unsupported business action."
        decision = "REJECTED"
        approved = []
    elif parsed_intent.risk in {"fraud", "data_breach", "legal"} and actions:
        reason = "Sensitive security or legal requests cannot execute automatically."
        decision = "REJECTED"
        approved = []
    elif not parsed_context.customer_found or not parsed_context.ownership_verified:
        reason = "Customer identity or order ownership could not be verified."
        decision = "REJECTED"
        approved = []
    elif any(action in {"get_order", "check_refund_eligibility", "initiate_return", "cancel_order"} for action in actions) and not parsed_context.order:
        reason = "The requested order action requires a verified order."
        decision = "REJECTED"
        approved = []
    elif "initiate_return" in actions and (
        not parsed_context.order
        or parsed_context.order.get("status") != "delivered"
        or not parsed_context.order.get("delivered_item")
        or parsed_context.order.get("delivered_item") == parsed_context.order.get("item")
    ):
        reason = "The order does not meet the deterministic return eligibility rules."
        decision = "REJECTED"
        approved = []
    elif "cancel_order" in actions and parsed_context.order.get("status") != "processing":
        reason = "Only processing orders can be cancelled."
        decision = "REJECTED"
        approved = []
    else:
        reason = "Plan passed deterministic identity, ownership, support, and eligibility checks."
        decision = "APPROVED"
        approved = actions

    result = ReviewResult(
        decision=decision,
        approved_actions=approved,
        reason=reason,
        arguments={
            "customer_id": parsed_context.customer_id,
            "order_id": (parsed_context.order or {}).get("id"),
        },
    )
    trace = event(
        "Reviewer Agent",
        "Validate plan against deterministic authorization and business rules",
        f"{decision}: {reason}",
        started,
        "success" if decision == "APPROVED" else "blocked",
    )
    return result.model_dump(), trace
