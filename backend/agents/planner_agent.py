import time
from .common import llm_json,event
from schemas import ActionPlan

def run(text,intent,context,docs):
    t=time.perf_counter(); order=context.get('order') or {}; intent_name=intent.get('intent','other')
    actions=[]
    if intent_name in ('wrong_item', 'return_request', 'replacement_request'):
        actions=['get_order','initiate_return']
    elif intent_name=='payment_failure': actions=['get_order','check_refund_eligibility']
    elif intent_name in ('refund', 'refund_issue'): actions=['check_refund_eligibility']
    elif intent_name in ('refund_policy', 'refund_timeline', 'change_of_mind_return'):
        actions=[]
    elif intent_name=='cancel_order': actions=['cancel_order']
    elif intent_name in ('order_tracking', 'delivery_delay'):
        actions=['get_order']
    elif intent_name=='account_locked': actions=['check_account']
    elif intent_name in ('fraud','data_breach','human_assistance','complaint','greeting'): actions=[]
    elif intent.get('order_id'): actions=['get_order']
    fallback={"summary":f"Handle {intent_name} request using verified context and retrieved policy.","steps":["Verify customer and relevant records","Apply the relevant support policy","Perform only eligible actions"],"actions":actions,"confidence":0.82 if docs else 0.58}
    out=llm_json("You are a support workflow planner. Return JSON keys summary,steps (array),actions (array of allowed tool names),confidence (0-1). Allowed tools: get_order, initiate_return, check_refund_eligibility, initiate_refund, cancel_order, check_account. Do not propose actions for fraud or data breach; escalate those. Use only supplied context and policy snippets.",f"Issue: {text}\nIntent: {intent}\nContext: {context}\nPolicy: {[d['id']+': '+d['text'] for d in docs]}",fallback)
    out.setdefault('actions',actions); out.setdefault('steps',fallback['steps']); out.setdefault('confidence',fallback['confidence'])
    allowed={'get_order','initiate_return','check_refund_eligibility','initiate_refund','cancel_order','check_account'}
    out['actions']=[a for a in out.get('actions',[]) if a in allowed]
    if intent_name in (
        'fraud', 'data_breach', 'human_assistance', 'complaint', 'greeting',
        'refund_policy', 'refund_timeline', 'change_of_mind_return',
    ):
        out['actions']=[]
    validated = ActionPlan.model_validate(out)
    return validated.model_dump(),event("Troubleshooting / Planner Agent","Create a policy-grounded action plan",f"{len(validated.steps)} steps · tools: {', '.join(validated.actions) or 'none'} · confidence {validated.confidence:.2f}",t)
