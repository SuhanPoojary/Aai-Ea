import threading
import time
from collections import defaultdict
from contextlib import contextmanager


_lock = threading.Lock()
_counters = defaultdict(int)
_durations = defaultdict(list)


def increment(name: str, amount: int = 1) -> None:
    with _lock:
        _counters[name] += amount


def observe(name: str, duration_ms: float) -> None:
    with _lock:
        _durations[name].append(round(duration_ms, 2))


@contextmanager
def timed(name: str):
    started = time.perf_counter()
    try:
        yield
    finally:
        observe(name, (time.perf_counter() - started) * 1000)


def snapshot() -> dict:
    with _lock:
        counters = dict(_counters)
        durations = {
            name: {
                "count": len(values),
                "avg_ms": round(sum(values) / len(values), 2),
                "p95_ms": round(sorted(values)[max(0, int(len(values) * 0.95) - 1)], 2),
            }
            for name, values in _durations.items()
            if values
        }
    return {"counters": counters, "durations": durations}
