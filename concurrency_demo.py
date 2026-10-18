"""Proves the ledger lock matters: races 12 threads confirming the same 6 pending transfers (18,000 proposed vs an
8,000 daily cap). Runs the identical workload WITHOUT and WITH the lock, 20 times each, and counts cap violations."""
import time
from concurrent.futures import ThreadPoolExecutor
import guardrails as g, tools as T

class _NoLock:
    def __enter__(self): return self
    def __exit__(self, *a): return False

def _run(use_lock, rounds=20):
    orig, bad = g.check_transfer, 0
    g.check_transfer = lambda *a, **k: (lambda r: (time.sleep(0.002), r)[1])(orig(*a, **k))     # widen the race window
    try:
        for _ in range(rounds):
            lg = T.Ledger()
            if not use_lock: lg.lock = _NoLock()
            codes = [T.propose_transfer("Dorm Landlord", 3000, lg)["code"] for _ in range(6)]
            with ThreadPoolExecutor(12) as ex: list(ex.map(lambda c: T.confirm_transfer(c, lg), codes * 2))
            bad += lg.sent_total() > g.MAX_DAILY
    finally: g.check_transfer = orig
    return bad

def demo():
    return {"rounds": 20, "violations_without_lock": _run(False), "violations_with_lock": _run(True)}

if __name__ == "__main__": print(demo())
