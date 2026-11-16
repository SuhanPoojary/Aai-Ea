import time
from .common import event

def run(intent,plan,results):
    t=time.perf_counter(); risk=intent.get('risk','none'); fails=any(not r.get('ok') for r in results)
    reasons=[]
    intent_name = intent.get("intent")
    if intent_name == "human_assistance":
        reasons.append("customer requested human assistance")
    if intent_name in {"wrong_item", "return_request"}:
        reasons.append("damaged or incorrect product requires human replacement or refund review")
    if intent_name == "complaint" and intent.get("priority") == "high":
        reasons.append("customer reported an unresolved complaint")
    if intent_name == "delivery_delay":
        order_result = next((r for r in results if r.get("tool") == "get_order"), None)
        if not order_result or not order_result.get("ok"):
            reasons.append("delivery complaint could not be verified automatically")
        elif order_result.get("status") != "delivered":
            reasons.append("order is overdue or not confirmed delivered")
        else:
            reasons.append("delivery complaint conflicts with the recorded delivered status")
    if intent_name == "payment_failure":
        order_result = next((r for r in results if r.get("tool") == "get_order"), None)
        eligibility = next(
            (r for r in results if r.get("tool") == "check_refund_eligibility"),
            None,
        )
        if (
            not order_result
            or not order_result.get("ok")
            or order_result.get("status") in {"processing", "payment_failed"}
            or order_result.get("payment_status") != "success"
            or not eligibility
            or not eligibility.get("ok")
        ):
            reasons.append("payment and order status mismatch requires billing review")
    if risk in ('fraud','legal','data_breach'): reasons.append('sensitive security/legal issue')
    informational = intent.get("intent") in {
        "refund_policy", "refund_timeline", "change_of_mind_return"
    }
    if not informational and float(plan.get('confidence',0.5))<0.55:
        reasons.append('low plan confidence')
    reviewer_block = any(r.get("tool") == "reviewer" for r in results)
    if (
        not informational
        and reviewer_block
        and intent_name not in {"order_tracking", "refund_policy", "refund_timeline"}
        and not reasons
    ):
        reasons.append("automated resolution was rejected and needs human review")
    if not informational and fails and not reviewer_block:
        reasons.append('business tool failed or eligibility check blocked action')
    if intent_name == "refund_issue":
        reasons.append("unresolved refund issue requires billing review")
    escalated=bool(reasons)
    team={'fraud':'Trust & Safety','data_breach':'Security Response','legal':'Legal Support','billing':'Billing Operations','subscription':'Engineering Support'}.get(intent.get('category'),'Customer Support')
    sla=5 if risk in ('fraud','data_breach') else (15 if intent.get('priority')=='high' else 60)
    out={"escalate":escalated,"reasons":reasons,"team":team,"sla_minutes":sla,"decision":"escalate_to_human" if escalated else "continue_automatic_resolution"}
    return out,event("Escalation Agent","Evaluate risk, confidence and tool outcomes",out['decision']+(": "+', '.join(reasons) if reasons else ''),t)
