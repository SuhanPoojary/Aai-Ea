import time
from .common import event

def run(history, text, slots):
    t=time.perf_counter(); new=dict(slots or {})
    import re
    m=re.search(r'ORD\d{4,}',text,re.I)
    if m: new['order_id']=m.group(0).upper()
    hist=(history or [])[-8:]
    return {"history":hist+[ {"role":"user","content":text} ],"slots":new,"turn":len(history or [])//2+1},event("Memory Agent","Load conversation history and update slots",f"Turn {len(history or [])//2+1} · remembered order {new.get('order_id','none')}",t)
