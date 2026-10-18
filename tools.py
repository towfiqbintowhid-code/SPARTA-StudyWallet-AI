"""Tools the agent can call. Money NEVER moves here except confirm_transfer (human-only, simulated).
State (pending/executed/audit) lives in a Ledger object, one per user session."""
import csv, json, math, threading, time, uuid
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
import guardrails as g
import stakeholders as sh
import fin_api, fraud_model

DATA = Path(__file__).parent / "data"
PROFILE = json.loads((DATA / "profile.json").read_text())
CCY = fin_api.SUPPORTED

class Ledger:
    """Per-session state, so two users never see each other's transfers.
    THREAD-SAFE: every state change (propose / confirm / cancel / log) runs under one re-entrant lock, so concurrent
    requests can never double-spend the daily cap, confirm the same code twice, or fork the audit chain.
    The audit log is a PERMISSIONED, hash-chained, signed log (see stakeholders.py + guardrails.chain_entry):
    each entry records the authorised party (actor) that wrote it, its hash depends on the previous entry, and it is
    HMAC-signed with that party's key, so edits, deletions and forged entries are detectable with verify_integrity()."""
    def __init__(self):
        self.pending, self.executed, self.alerts = {}, [], {}
        self._entries = []     # {"timestamp","message","actor","action","prev_hash","hash","sig"}
        self.lock = threading.RLock()
        self._keys = sh.new_keyring()
        self._proposal_times = []

    def __deepcopy__(self, memo):      # used by the tamper demo; the lock itself cannot be copied
        import copy
        n = Ledger(); n.pending, n.executed, n.alerts = copy.deepcopy(self.pending), copy.deepcopy(self.executed), copy.deepcopy(self.alerts)
        n._entries, n._keys, n._proposal_times = copy.deepcopy(self._entries), dict(self._keys), list(self._proposal_times)
        return n

    def log(self, msg, actor="guardrail", action="INFO"):
        if not sh.authorised(actor, action):
            raise PermissionError(f"'{actor}' is not authorised to write '{action}' entries")
        with self.lock:
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            prev_hash = self._entries[-1]["hash"] if self._entries else g.GENESIS_HASH
            h = g.chain_entry(prev_hash, msg, ts, actor, action)
            self._entries.append({"timestamp": ts, "message": msg, "actor": actor, "action": action,
                                  "prev_hash": prev_hash, "hash": h, "sig": sh.sign(self._keys[actor], h)})

    @property
    def audit(self):
        """Human-readable lines."""
        return [f"{e['timestamp'][-8:]} [{e.get('actor', 'system')}] {e['message']}" for e in self._entries]

    def verify_integrity(self) -> bool:
        """Recomputes the hash chain AND checks every party's signature; False if anything was edited, removed or forged."""
        with self.lock: return g.verify_chain(self._entries, self._keys)

    def recent_proposals(self, window=600):
        now = time.time(); return sum(1 for t in self._proposal_times if now - t < window)

    def sent_total(self): return sum(e["amount"] for e in self.executed)

LEDGER = Ledger()

def _lg(ledger): return LEDGER if ledger is None else ledger

def _txns():
    with open(DATA / "transactions.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows: r["amount"] = float(r["amount"]); r["date"] = date.fromisoformat(r["date"])
    return rows

def get_balance(ledger=None):
    lg = _lg(ledger)
    bal = PROFILE["opening_balance"] + sum(r["amount"] for r in _txns()) - lg.sent_total()
    return {"balance": round(bal, 2), "currency": PROFILE["account_ccy"]}

def spending_summary(days: int = 30):
    if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 365:
        return {"error": "days must be a whole number between 1 and 365"}
    rows = _txns(); end = max(r["date"] for r in rows); start = end - timedelta(days=days)
    cat, memo_flags = defaultdict(float), 0
    for r in rows:
        if r["date"] > start and r["amount"] < 0:
            cat[r["category"]] += -r["amount"]
            if g.detect_injection(r["description"]): memo_flags += 1
    total = sum(cat.values()); top = sorted(cat.items(), key=lambda x: -x[1])
    return {"days": days, "total_spent": round(total, 2), "currency": PROFILE["account_ccy"],
            "by_category": {k: round(v, 2) for k, v in top},
            "top_category": top[0][0] if top else None, "suspicious_memos_ignored": memo_flags}

def _rates(base):
    return fin_api.fx_rates(base)

def fx_quote(amount: float, from_ccy: str, to_ccy: str):
    if not g.is_valid_amount(amount): return {"error": "amount must be a positive, finite number"}
    f, t = str(from_ccy).upper(), str(to_ccy).upper()
    if f not in CCY or t not in CCY: return {"error": f"Supported currencies: {sorted(CCY)}"}
    rates, source = _rates(f)
    return {"amount": amount, "from": f, "to": t, "rate": round(rates[t], 6),
            "converted": round(amount * rates[t], 2), "rate_source": source,
            "note": "Mid-market rate. Bank/remittance fees NOT included."}

def _monthly_flows():
    rows = _txns(); end = max(r["date"] for r in rows); start = end - timedelta(days=90)
    w = [r for r in rows if r["date"] > start]
    return (sum(r["amount"] for r in w if r["amount"] > 0) / 3,
            -sum(r["amount"] for r in w if r["amount"] < 0) / 3)

def recent_transactions(limit: int = 10):
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 30:
        return {"error": "limit must be a whole number between 1 and 30"}
    rows = sorted(_txns(), key=lambda r: r["date"], reverse=True)[:limit]
    return {"currency": PROFILE["account_ccy"], "transactions": [
        {"date": r["date"].isoformat(), "description": g.sanitize_untrusted(r["description"]),
         "category": g.sanitize_untrusted(r["category"]), "amount": r["amount"]} for r in rows]}

def savings_plan(goal_amount: float, months: int):
    if not g.is_valid_amount(goal_amount): return {"error": "goal must be a positive, finite number"}
    if not isinstance(months, int) or isinstance(months, bool) or not 1 <= months <= 120:
        return {"error": "months must be a whole number between 1 and 120"}
    inc, spend = _monthly_flows()
    need = goal_amount / months
    return {"goal": goal_amount, "months": months, "avg_monthly_income": round(inc, 2),
            "avg_monthly_spend": round(spend, 2), "avg_monthly_surplus": round(inc - spend, 2),
            "required_per_month": round(need, 2), "feasible": (inc - spend) >= need,
            "currency": PROFILE["account_ccy"]}

def _rate_alert_for(lg, f, to):
    """Checks a user-set rate alert for this currency pair (None if no alert is set)."""
    al = lg.alerts.get((f, to))
    if not al: return None
    rate = _rates(f)[0][to]; hit = rate < al["threshold"]
    out = {"pair": f"{f}->{to}", "current_rate": round(rate, 6), "threshold": round(al["threshold"], 6), "triggered": hit}
    if hit:
        out["advice"] = "Current rate is BELOW your threshold. Consider waiting or comparing providers before sending."
        lg.log(f"RATE ALERT {f}->{to}: {rate:.4f} < threshold {al['threshold']:.4f}", "guardrail", "ALERT_TRIGGERED")
    return out

def set_rate_alert(from_ccy: str, to_ccy: str, threshold: float = None, pct_drop: float = None, ledger=None):
    """In-app notification when the rate falls BELOW a threshold. Two modes: an absolute `threshold`, or `pct_drop`
    (% below today's rate, recommended: no need to guess an absolute number). Alerts are advisory; they never move money."""
    lg = _lg(ledger); f, t = str(from_ccy).upper(), str(to_ccy).upper()
    if f not in CCY or t not in CCY or f == t: return {"error": f"Pick two different currencies from {sorted(CCY)}"}
    if (threshold is None) == (pct_drop is None): return {"error": "Give exactly one of threshold or pct_drop"}
    base = _rates(f)[0][t]
    if pct_drop is not None:
        if isinstance(pct_drop, bool) or not isinstance(pct_drop, (int, float)) or not math.isfinite(pct_drop) or not 0 < pct_drop <= 50:
            return {"error": "pct_drop must be between 0 and 50"}
        threshold = base * (1 - pct_drop / 100)
    elif not g.is_valid_amount(threshold): return {"error": "threshold must be a positive, finite number"}
    with lg.lock:
        lg.alerts[(f, t)] = {"threshold": float(threshold), "baseline": base}
        lg.log(f"RATE ALERT SET {f}->{t} below {threshold:.4f} (rate when set {base:.4f})", "student", "ALERT_SET")
    return {"pair": f"{f}->{t}", "alert_when_rate_below": round(threshold, 6), "rate_now": round(base, 6),
            "delivery": "in-app notification (demo); real SMS/email/push needs a provider integration"}

def check_rate_alerts(ledger=None):
    lg = _lg(ledger)
    with lg.lock:
        res = [_rate_alert_for(lg, f, t) for (f, t) in list(lg.alerts)]
    return {"alerts": res, "any_triggered": any(r["triggered"] for r in res)} if res else {"alerts": [], "note": "No alerts set."}

def propose_transfer(payee_name: str, amount: float, ledger=None, note: str = ""):
    lg = _lg(ledger)
    with lg.lock:
        ok, reason = g.check_transfer(payee_name, amount, lg.sent_total())
        if not ok:
            lg.log(f"BLOCKED propose {amount} -> {payee_name}: {reason}", "guardrail", "BLOCK")
            return {"status": "blocked", "reason": reason}
        risk = fraud_model.assess(amount, payee_name, str(note or "")[:300], lg.recent_proposals())
        lg._proposal_times.append(time.time())
        code = uuid.uuid4().hex[:6].upper()
        lg.pending[code] = {"payee": payee_name, "amount": amount, "risk": risk}
        lg.log(f"PROPOSED {amount} -> {payee_name} [{code}] ml_risk={risk['level']}({risk['score']})", "agent", "PROPOSE")
        if risk["level"] != "low": lg.log(f"ML RISK {risk['level'].upper()} [{code}]: {'; '.join(risk['reasons']) or 'combined signals'}", "guardrail", "RISK")
        res = {"status": "pending_human_confirmation", "code": code, "payee": payee_name, "amount": amount, "fraud_risk": risk,
               "message": "Nothing has been sent. The user must press Confirm in the app."}
        if risk["level"] == "high":
            res["requires_extra_confirmation"] = True
            res["message"] = "HIGH scam/fraud risk. Nothing has been sent. The user must tick 'I understand the risk' and press Confirm."
        if payee_name == "Mom (Home)":
            ra = _rate_alert_for(lg, PROFILE["account_ccy"], PROFILE["home_ccy"])
            if ra: res["rate_alert"] = ra
        return res

def confirm_transfer(code: str, ledger=None, acknowledged_risk: bool = False):
    lg = _lg(ledger)
    with lg.lock:     # whole check-then-act sequence is atomic: no double-confirm, no cap race
        p = lg.pending.get(code)
        if not p: return {"status": "error", "reason": "Unknown or expired code."}
        if p.get("risk", {}).get("level") == "high" and not acknowledged_risk:
            return {"status": "needs_risk_acknowledgement", "reason": "High scam/fraud risk: explicit acknowledgement required."}
        lg.pending.pop(code)
        ok, reason = g.check_transfer(p["payee"], p["amount"], lg.sent_total())
        if not ok: lg.log(f"BLOCKED confirm [{code}]: {reason}", "guardrail", "BLOCK"); return {"status": "blocked", "reason": reason}
        lg.log(f"CONFIRMED by account holder [{code}]", "student", "CONFIRM")
        rec = {"payee": p["payee"], "amount": p["amount"]}; lg.executed.append(rec)
        lg.log(f"EXECUTED (simulated) {rec['amount']} -> {rec['payee']} [{code}]", "bank", "EXECUTE")
        return {"status": "executed_simulated", **rec}

def cancel_transfer(code: str, ledger=None):
    lg = _lg(ledger)
    with lg.lock:
        lg.pending.pop(code, None); lg.log(f"CANCELLED [{code}]", "student", "CANCEL")

def tuition_plan(amount: float, currency: str, months: int, ledger=None):
    if not g.is_valid_amount(amount): return {"error": "amount must be a positive, finite number"}
    if not isinstance(months, int) or isinstance(months, bool) or not 1 <= months <= 24:
        return {"error": "months must be a whole number between 1 and 24"}
    q = fx_quote(amount, currency, PROFILE["account_ccy"])
    if "error" in q: return q
    base = q["converted"]
    cost = {"base": base, "if_currency_up_5pct": round(base * 1.05, 2), "if_currency_up_10pct": round(base * 1.10, 2)}
    bal = get_balance(ledger)["balance"]; inc, spend = _monthly_flows(); surplus = inc - spend
    worst = cost["if_currency_up_10pct"]; shortfall = max(0.0, worst - bal)
    return {"tuition": amount, "tuition_ccy": q["from"], "months_until_due": months,
            "rate_used": q["rate"], "rate_source": q["rate_source"], "account_ccy": PROFILE["account_ccy"],
            "cost_in_account_ccy": cost, "current_balance": bal, "avg_monthly_surplus": round(surplus, 2),
            "shortfall_in_worst_case": round(shortfall, 2),
            "set_aside_per_month_worst_case": round(shortfall / months, 2),
            "affordable_in_worst_case": bal + surplus * months >= worst,
            "note": "Scenarios are simple stress tests, not forecasts. Fees not included."}

def compare_remittance(amount: float, to_ccy: str = "", ledger=None):
    if not g.is_valid_amount(amount): return {"error": "amount must be a positive, finite number"}
    to = (to_ccy or PROFILE["home_ccy"]).upper(); src = PROFILE["account_ccy"]
    q = fx_quote(amount, src, to)
    if "error" in q: return q
    out = fin_api.SandboxRemittanceAPI().quotes(amount, q["rate"])
    if not out: return {"error": "amount is too small to cover provider fees"}
    res = {"send": amount, "from": src, "to": to, "mid_market_rate": q["rate"], "rate_source": q["rate_source"],
           "ranked": out, "best": out[0]["provider"], "extra_vs_worst": round(out[0]["recipient_gets"] - out[-1]["recipient_gets"], 2),
           "illustrative_provider_data": True, "note": "Provider fees are ILLUSTRATIVE placeholders; verify real quotes before sending."}
    lg = _lg(ledger)
    with lg.lock: ra = _rate_alert_for(lg, src, to)
    if ra: res["rate_alert"] = ra
    return res
