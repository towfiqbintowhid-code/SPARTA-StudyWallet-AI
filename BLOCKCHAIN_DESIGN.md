# Blockchain design: permissioned audit ledger with authorised parties

**Question from reviewers:** "Propose a blockchain here, but ensure who will be the authorised parties/stakeholders."

## 1. Why permissioned
A public chain is world-writable and exposes data. A student-finance system handles personal money data and must
know exactly who wrote each record. So the design is a **permissioned (consortium) ledger**: only enrolled parties
can append, each holds its own key, and every record is attributable (the Hyperledger Fabric model).

## 2. Authorised parties (implemented in `stakeholders.py`)
| Party | Real-world holder | May write | Notes |
|---|---|---|---|
| student | Account holder | LOGIN, CONFIRM, CANCEL, ALERT_SET | The only party that can approve money movement |
| agent | AI assistant | PROPOSE, INFO | Cannot confirm, cancel or execute |
| guardrail | Rule engine + ML fraud model | BLOCK, RISK, ALERT_TRIGGERED, INFO | Deterministic safety layer |
| bank | Bank / payment node | EXECUTE | Only party that records execution, and only after a student CONFIRM |
| auditor | University / regulator | (none) | Read-only: can verify chain and signatures |

## 3. Record format and checks
Entry = `{timestamp, actor, action, message, prev_hash, hash, sig}` with
`hash = SHA256(prev_hash | timestamp | actor | action | message)` and `sig = HMAC-SHA256(actor_key, hash)`.
1. Authorisation: `Ledger.log` raises `PermissionError` if the actor is not allowed that action.
2. Integrity: `verify_integrity()` recomputes every hash and link, so edits and deletions break the chain.
3. Authenticity: it also verifies every signature, so an attacker who re-computes all hashes still fails.
4. Consensus (production): independent nodes (bank, university, regulator) would each store a copy and endorse
   entries; this sandbox simulates all parties in one process with in-memory keys (stated limitation).

## 4. Public anchoring (optional extra)
Truncation of the newest entries is invisible to a single chain. Publishing the latest hash on a public chain
(`anchor_testnet.py`, Sepolia testnet) gives an external, timestamped proof. Run it yourself with a throwaway wallet.

## 5. What is deliberately not done
- No tokens, no smart contracts, no real-money settlement (Topic C is an off-chain topic).
- NFC: needs hardware and a native app; roadmap only.
