import time
from .common import event

def run(intent,plan,results):
    t=time.perf_counter(); risk=intent.get('risk','none'); fails=any(not r.get('ok') for r in results)
    reasons=[]
    if intent.get("intent") == "human_assistance":
        reasons.append("customer requested human assistance")
    if intent.get("intent") == "complaint" and intent.get("priority") == "high":
        reasons.append("unresolved high-priority complaint")
    if risk in ('fraud','legal','data_breach'): reasons.append('sensitive security/legal issue')
    informational = intent.get("intent") in {
        "refund_policy", "refund_timeline", "change_of_mind_return"
    }
    if not informational and float(plan.get('confidence',0.5))<0.55:
        reasons.append('low plan confidence')
    reviewer_block = any(r.get("tool") == "reviewer" for r in results)
    if not informational and fails and not reviewer_block:
        reasons.append('business tool failed or eligibility check blocked action')
    if intent.get("intent") == "refund_issue":
        reasons.append("unresolved refund issue requires billing review")
    escalated=bool(reasons)
    team={'fraud':'Trust & Safety','data_breach':'Security Response','legal':'Legal Support','billing':'Billing Operations','subscription':'Engineering Support'}.get(intent.get('category'),'Customer Support')
    sla=5 if risk in ('fraud','data_breach') else (15 if intent.get('priority')=='high' else 60)
    out={"escalate":escalated,"reasons":reasons,"team":team,"sla_minutes":sla,"decision":"escalate_to_human" if escalated else "continue_automatic_resolution"}
    return out,event("Escalation Agent","Evaluate risk, confidence and tool outcomes",out['decision']+(": "+', '.join(reasons) if reasons else ''),t)
