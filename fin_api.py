"""Financial API adapters (the integration points to real financial services).

 - FX rates: LIVE integration with the open.er-api.com public API, with a 60-second cache (so many users/threads
   do not hammer the API) and an automatic offline fallback to data/fx_cache.json (clearly labelled 'cached-sample').
 - Remittance providers: a SANDBOX adapter reading data/remit_providers.json (illustrative fees). The class
   interface (`quotes(amount, rate)`) is what a real provider API client (Wise, Remitly, bank API) would implement.
"""
import json, threading, time, urllib.request
from pathlib import Path

DATA = Path(__file__).parent / "data"
_FX_CACHE = json.loads((DATA / "fx_cache.json").read_text())
SUPPORTED = {k for k in _FX_CACHE if not k.startswith("_")}
_TTL, _store, _lock = 60.0, {}, threading.Lock()

def fx_rates(base: str):
    """Returns (rates_dict, source) where source is 'live' or 'cached-sample'. Thread-safe, 60 s TTL."""
    now = time.time()
    with _lock:
        hit = _store.get(base)
        if hit and now - hit[0] < _TTL: return hit[1], hit[2]
    try:
        with urllib.request.urlopen(f"https://open.er-api.com/v6/latest/{base}", timeout=4) as r:
            d = json.load(r)
        if d.get("result") == "success" and all(c in d["rates"] for c in SUPPORTED):
            out = (d["rates"], "live")
        else: raise ValueError("incomplete response")
    except Exception:
        out = (_FX_CACHE[base], "cached-sample")
    with _lock: _store[base] = (now, out[0], out[1])
    return out

class SandboxRemittanceAPI:
    """Swap this class for a real provider client in production."""
    def __init__(self): self.cfg = json.loads((DATA / "remit_providers.json").read_text())
    def quotes(self, amount: float, rate: float):
        out = []
        for pv in self.cfg["providers"]:
            fee = pv["flat_fee"] + amount * pv["fee_pct"] / 100
            if fee >= amount: continue
            got = (amount - fee) * rate * (1 - pv["fx_margin_pct"] / 100)
            out.append({"provider": pv["name"], "total_fee": round(fee, 2), "fx_margin_pct": pv["fx_margin_pct"], "recipient_gets": round(got, 2)})
        return sorted(out, key=lambda r: -r["recipient_gets"])
