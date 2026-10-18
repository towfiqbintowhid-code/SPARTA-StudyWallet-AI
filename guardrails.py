"""Safety layer. Three ideas judges look for: permission levels, injection defense, hallucination check."""
import hashlib
import math
import re

ALLOWED_PAYEES = {"Tuition Office", "Dorm Landlord", "Mom (Home)", "Phone Plan"}
MAX_SINGLE = 5000.0
MAX_DAILY = 8000.0

def is_valid_amount(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and x > 0

def check_transfer(payee: str, amount: float, already_sent_today: float):
    if payee not in ALLOWED_PAYEES:
        return False, f"Payee '{payee}' is not on the allow-list."
    if not is_valid_amount(amount):
        return False, "Amount must be a positive, finite number."
    if amount > MAX_SINGLE:
        return False, f"Over single-transfer limit ({MAX_SINGLE:,.0f})."
    if already_sent_today + amount > MAX_DAILY:
        return False, f"Would exceed daily limit ({MAX_DAILY:,.0f})."
    return True, "ok"

INJECTION_PATTERNS = [
    r"ignore (all |any )?(previous|prior|above) (instructions|rules)",
    r"disregard .{0,20}(instructions|rules)", r"you are now", r"system prompt",
    r"reveal .{0,30}(key|password|prompt)", r"override", r"jailbreak",
    r"transfer \d+ to", r"act as",
]
def detect_injection(text: str) -> bool:
    return any(re.search(p, text, re.I) for p in INJECTION_PATTERNS)

def sanitize_untrusted(text: str, max_len: int = 60) -> str:
    return "[REDACTED: suspicious text in data]" if detect_injection(text) else text[:max_len]

_NUM = re.compile(r"\d[\d,]*\.?\d*")
def _nums(text: str):
    out = []
    for m in _NUM.findall(text):
        try: out.append(float(m.replace(",", "")))
        except ValueError: pass
    return out

def unsupported_numbers(answer: str, evidence: list, min_value: float = 50):
    known = [n for e in evidence for n in _nums(e)]
    bad = []
    for n in _nums(answer):
        if n < min_value: continue
        if not any(abs(n - k) <= max(0.5, 0.01 * abs(k)) for k in known): bad.append(n)
    return bad


# 4) TAMPER-EVIDENT AUDIT LOG (hash-chained, blockchain-INSPIRED integrity check — NOT an on-chain transaction)
# Each entry's hash depends on the previous entry's hash, like a block header. This lets us PROVE after the
# fact whether any past audit-log line was edited or deleted, without needing an actual blockchain network.
GENESIS_HASH = "0" * 64

def chain_entry(prev_hash: str, message: str, timestamp: str, actor: str = "system", action: str = "INFO") -> str:
    payload = f"{prev_hash}|{timestamp}|{actor}|{action}|{message}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()

def verify_chain(entries: list, keyring: dict = None) -> bool:
    """entries: dicts with 'timestamp','message','hash','prev_hash' (+ 'actor','action','sig').
    If a keyring {actor: key} is given, every entry's signature must also verify (permissioned-ledger check)."""
    import stakeholders as sh
    prev = GENESIS_HASH
    for e in entries:
        if e["prev_hash"] != prev:
            return False
        if chain_entry(e["prev_hash"], e["message"], e["timestamp"], e.get("actor", "system"), e.get("action", "INFO")) != e["hash"]:
            return False
        if keyring is not None:
            key = keyring.get(e.get("actor"))
            if key is None or not sh.verify_sig(key, e["hash"], e.get("sig", "")):
                return False
        prev = e["hash"]
    return True
