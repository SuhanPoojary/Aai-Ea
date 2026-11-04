import re, time
from .common import event
PATTERNS = [
    r"ignore (all )?(previous|prior) instructions",
    r"ignore (your )?polic",
    r"reveal (the )?(system prompt|secret|api key)",
    r"show me another customer",
    r"access another customer's",
    r"bypass (security|authentication)",
    r"guarantee (me )?(a )?refund",
]
def run(text: str):
    t=time.perf_counter(); hit=next((p for p in PATTERNS if re.search(p,text,re.I)),None)
    safe=hit is None
    return {"safe":safe,"reason":"Input passed safety checks" if safe else "Potential prompt injection or unauthorized data request"}, event("Guardrail Agent","Scan input for injection and unauthorized access", "Allowed" if safe else "Blocked: unsafe request",t,"success" if safe else "blocked")
