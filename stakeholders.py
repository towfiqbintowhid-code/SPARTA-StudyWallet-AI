"""Permissioned-ledger model: WHO may write WHICH kind of audit entry.

A public blockchain lets anyone write. A financial system needs a *permissioned* ledger where only known,
authorised parties can append, and each entry is attributable. This module defines those parties and gives
each one a signing key (HMAC-SHA256). Every audit entry carries (actor, action, signature):
  - an actor writing an action it is not authorised for is rejected (PermissionError);
  - an attacker who edits an entry AND recomputes the hash chain still fails, because they cannot forge
    the actor's signature without that actor's key.
SIMULATION NOTE: in this sandbox all parties run in one process and keys live in memory. In production each
party would be a separate node holding its key in an HSM/KMS (the Hyperledger Fabric 'endorsement' idea).
"""
import hashlib, hmac, secrets

ROLE_ACTIONS = {
    "student":   {"LOGIN", "CONFIRM", "CANCEL", "ALERT_SET"},       # the human account holder
    "agent":     {"PROPOSE", "INFO"},                                 # the AI: may only PROPOSE, never execute
    "guardrail": {"BLOCK", "RISK", "ALERT_TRIGGERED", "INFO"},        # deterministic safety + ML risk layer
    "bank":      {"EXECUTE"},                                         # simulated bank node: only it records execution
    "auditor":   set(),                                               # university / regulator: read + verify only
}
ROLE_DESCRIPTIONS = {
    "student":   "Account holder. Signs in with OTP, confirms or cancels transfers, sets rate alerts.",
    "agent":     "AI assistant. Can only PROPOSE a transfer (L1). Cannot confirm, cancel or execute.",
    "guardrail": "Rule engine + ML fraud model. Records blocks, risk scores and rate-alert triggers.",
    "bank":      "Simulated bank node. The only party that records EXECUTE after a human CONFIRM.",
    "auditor":   "University / regulator. Read-only: can verify the chain and signatures, cannot write.",
}

def authorised(actor: str, action: str) -> bool:
    return action in ROLE_ACTIONS.get(actor, set())

def new_keyring() -> dict:
    return {a: secrets.token_bytes(32) for a in ROLE_ACTIONS}

def sign(key: bytes, entry_hash: str) -> str:
    return hmac.new(key, entry_hash.encode(), hashlib.sha256).hexdigest()

def verify_sig(key: bytes, entry_hash: str, sig: str) -> bool:
    return hmac.compare_digest(sign(key, entry_hash), sig or "")
