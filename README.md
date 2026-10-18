# StudyWallet AI

An AI agent for international students that handles everyday cross-border money tasks in a sandbox. It can analyse spending,
convert currencies, plan savings, stress-test a foreign-currency tuition bill, compare remittance providers and prepare transfers.
It can only propose transfers; a person must approve each one.

Built for the **2026 Shenzhen International FinTech Competition (FinTechathon), International Track — Topic C
(Cross-border & Student Finance Assistant)**.

Built with Python, Streamlit, pytest and the Anthropic Claude API (optional at run time).

## Features
| Task | Tool | Tier |
|---|---|---|
| OTP sign-in (demo) before any wallet feature is reachable | `auth.request_otp`, `auth.verify_otp` | Gate |
| Balance, spending by category, recent transactions | `get_balance`, `spending_summary`, `recent_transactions` | L0 |
| Currency conversion with rate source | `fx_quote` | L0 |
| Savings goal check | `savings_plan` | L0 |
| Tuition bill with +5% / +10% FX stress test | `tuition_plan` | L0 |
| Remittance provider comparison | `compare_remittance` | L0 |
| Prepare a transfer (nothing moves) | `propose_transfer` | L1 |
| Approve or cancel a transfer | `confirm_transfer`, `cancel_transfer` | L2 (UI button only) |
| Rate alert: notify when a rate falls below a threshold (absolute, or % below today) | `set_rate_alert`, `check_rate_alerts` | L0 (advisory) |
| ML scam / fraud alert on every proposed transfer (explainable, can only escalate) | `fraud_model.assess` inside `propose_transfer` | L1 (advisory) |
| Concurrent transactions: thread-safe ledger, no double-confirm, no cap race | `Ledger.lock` | cross-cutting |
| Permissioned, signed, hash-chained audit log with authorised parties | `stakeholders.py`, `Ledger.log` / `verify_integrity` | cross-cutting |
| Optional: anchor the log head on the Sepolia testnet | `anchor_testnet.py` | optional |

## Architecture
```
User -> auth.py (OTP sign-in gate) -> app.py (Streamlit) -> agent.py (Claude tool-calling, offline fallback) -> tools.py -> guardrails.py
```
- **Authentication**: a demo OTP (one-time password) gate must be passed before any wallet feature is reachable.
  The 6-digit code is generated server-side with a cryptographically secure RNG (`secrets`), stored only as a salted SHA-256 hash, compared in constant time, with a 5-minute expiry and a 3-attempt lockout. No real SMS/email
  gateway is wired up in this sandbox — the code is shown on screen labelled "DEMO MODE"; swap in a real
  provider (Twilio, SES, etc.) for production.
- L0 read tools and the L1 proposal tool are exposed to the model. L2 execution is NOT in the tool list — the model
  physically cannot call it.
- **Tamper-evident audit log**: every audit entry is hash-chained (SHA-256 of `previous_hash | timestamp | message`),
  the same core idea used in blockchain block-headers, applied to a local append-only log. `Ledger.verify_integrity()`
  recomputes the chain and returns `False` if any past entry was edited or deleted — covered by
  `test_audit_chain_detects_tampering`. This is **not** an on-chain transaction (Topic C is intentionally off-chain);
  it borrows blockchain's hash-chaining idea for local audit integrity only.
- Guardrails: payee allow-list, 5,000 THB per transfer, 8,000 THB per session, finite-number validation, injection detection,
  redaction of untrusted memo text, and a check that numeric figures in answers appear in tool output.
- State (pending, executed, audit log) is kept per session in a `Ledger` object — two users never see each other's data.
- If the API key is missing or the API call fails, the agent automatically switches to an offline rule-based parser,
  so the product keeps working even without network/API access.

## Setup
Python 3.10 or newer. Run commands from this `04_Source_Code` directory.

### Windows (Command Prompt)
```bat
py -3 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python make_data.py
streamlit run app.py
```
Open `http://localhost:8501`. The app supports offline operation when no provider API key is configured.

### macOS / Linux
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python make_data.py
streamlit run app.py
```

### Optional cloud AI
Set `ANTHROPIC_API_KEY` using your operating system's environment-variable mechanism, or configure the supported provider key through the deployment platform's secrets manager. Do not commit real API keys to source control. Test without a key first to verify the offline fallback.
Example prompts: `Summarise my spending last 30 days`, `5000 baht to taka`, `tuition 1500 usd due in 4 months`,
`cheapest way to send 10000 baht to taka`, `send 3000 to Dorm Landlord`.

## Deployment
This is a single-process Streamlit app with no external database, so it deploys the same way anywhere:
1. Push this repository to GitHub.
2. Deploy on **Streamlit Community Cloud** (free): connect the repo, set `app.py` as the entry point,
   add `ANTHROPIC_API_KEY` under App settings → Secrets (optional — the app works offline without it).
3. Alternatively run in Docker: `pip install -r requirements.txt && streamlit run app.py --server.port 8501 --server.address 0.0.0.0`.
4. This prototype does not use a persistent database. Ledger, pending/executed transfer state, audit entries, and session state are held in memory; they can be lost when the process or session ends or the app restarts. Do not use this deployment as a record-keeping system for real financial activity.

## Tests and evidence
```
python -m pytest -v                 # 64 tests are present in the submitted suite; confirm the count locally
python generate_evidence.py         # writes evidence/sandbox_run_log.txt (sandbox execution evidence)
python demo_run.py                  # scripted transcript
```
Tests cover guardrails, tool input validation, session isolation, the L1->L2 transfer permission flow,
API-failure fallback, offline-parser phrasing, and the data importer.

## Data
Transactions are synthetic (`make_data.py`). `import_data.py` converts a personal bank statement locally and replaces
descriptions with generic category labels. Provider fees in `data/remit_providers.json` are illustrative placeholders
and must be replaced with real quotes before any production use. Exchange rates come from a public API
(open.er-api.com) when online and from `data/fx_cache.json` (sample values) otherwise; every quote states its source.

## Blockchain design (permissioned ledger with authorised parties)
Full write-up: `BLOCKCHAIN_DESIGN.md` (included in this source folder). Summary:
- **Who is authorised** (`stakeholders.py`): `student` (login, confirm, cancel, set alerts), `agent` (AI: PROPOSE only),
  `guardrail` (blocks, ML risk, alert triggers), `bank` (the only party that records EXECUTE), `auditor`
  (university/regulator: read + verify only).
- **How it works**: each audit entry stores `actor`, `action`, the previous entry's SHA-256 hash, its own hash, and an
  HMAC-SHA256 signature by that party's key. Writing an action you are not authorised for raises `PermissionError`;
  editing/deleting entries breaks the chain; even re-computing every hash fails because signatures cannot be forged.
- **Why permissioned, not public**: financial data must not be world-writable; only known parties append (the model
  used by Hyperledger Fabric / consortium chains). Topic C is an off-chain topic, so the ledger runs in-process.
- **Public anchor (optional)**: `anchor_testnet.py` publishes the chain head to Sepolia so truncation of the newest
  entries becomes detectable. Requires a separately configured test wallet and RPC endpoint; consult the script's argument/help text and relevant environment configuration. This optional feature is not required for the Topic C offline demo. Never use a wallet holding real funds or publish a private key.
- **NFC**: needs a hardware reader and native app; not verifiable in an online review, so it is roadmap only.

## Reviewer-driven enhancements
- **Concurrent transactions**: all ledger state changes run under one re-entrant lock; `concurrency_demo.py` races
  12 threads and shows 20/20 runs break the daily cap WITHOUT the lock and 0/20 WITH it. Each user session has its own ledger.
- **Rate alerts**: `alert me if thb to bdt drops 2%` (relative, recommended) or `below 3.5` (absolute). Triggered alerts
  appear in the sidebar, in remittance comparisons and when proposing a transfer to `Mom (Home)`. In-app only (demo).
- **ML fraud / scam alert**: TF-IDF + logistic regression on the message, plus a transfer-feature logistic regression.
  Trained on SYNTHETIC data at start-up, so metrics are demo numbers. High risk requires an explicit tick; the ML layer
  can never relax the allow-list, caps or the human Confirm step.
- **Financial APIs**: live FX integration (open.er-api.com, 60 s cache, offline fallback) and a swappable remittance
  provider adapter (`fin_api.py`); provider fees are sandbox data.

## Lightweight ML choice (speed first)
The scam/fraud model is deliberately small: TF-IDF + logistic regression gives about 0.4 ms per assessment on CPU, about 1 s
one-off start-up, works offline and needs no GPU. Measured honestly:
- synthetic hold-out (shares phrases with training): 96% accuracy, so optimistic and not a real-world performance estimate;
- `eval_paraphrase.py`, 40 hand-written messages with unseen wording: the current project notes report 85% accuracy, 75% scam recall, and 5% false alarms. Re-run the evaluation against the final submitted code before citing these numbers. These are small, manually prepared evaluation results, not evidence of real-world fraud-detection performance.
**Optional Hugging Face backend**: `pip install sentence-transformers` then `STUDYWALLET_TEXT_BACKEND=minilm streamlit run app.py`
swaps the text featuriser for `sentence-transformers/all-MiniLM-L6-v2` (22M parameters, 384-dim, Apache-2.0, ~90 MB one-off
download) with the same logistic-regression head. It falls back to TF-IDF automatically if the package or download is
unavailable. It was NOT run in the build sandbox (no Hugging Face access): run `STUDYWALLET_TEXT_BACKEND=minilm python
eval_paraphrase.py` (for example in Google Colab) to measure it, and use it only if the numbers beat the default.

## Limitations
- Simulated transfers only; no real banking integration, KYC or AML (see Security Self-Assessment Report).
- OTP delivery is simulated (shown on screen) because no SMS/email provider is connected in this sandbox.
- The hash chain detects edits and mid-log deletions, but deleting the *newest* entries is only detectable if the latest chain head was recorded elsewhere (e.g. anchored on a public chain) — a known residual risk; evidence log prints the chain head for this purpose.
- The ML models use synthetic training data; real deployment needs real labelled data, monitoring for false positives and drift.
- Party keys live in process memory in this sandbox; production needs separate nodes with HSM/KMS-held keys.
- Injection detection is pattern-based and can be bypassed by rephrasing; the primary protection is architectural —
  the execution tool is never exposed to the model (see Technical Documentation, "Permission Ladder").
- The figure-hallucination check ignores numbers under 50 and can flag legitimately-derived numbers.
- The session cap resets with a new session; state is in memory and not persistent across restarts.
- Not financial advice.

## Licence
MIT. See `LICENSE` and `THIRD_PARTY_LICENSES.md`.

## Team

**Team name: SPARTA** (as confirmed by the team leader).
The submission package includes a separate team-information PDF and spreadsheet containing the registration details. For a source-code README, the team members and institutions are listed here without personal identification numbers or private contact details:

- **Team leader — MD Towfiq Bin Towhid:** East West University, Computer Science and Engineering.
- **Member — Abdul Kaium:** East West University, Computer Science and Engineering.
- **Member — Md. Hasibur Rahaman Tanjim:** Chittagong University of Engineering and Technology, Electrical and Electronic Engineering.
- **Member — Muhammad Naiymur Rahman:** Jagannath University, Computer Science and Engineering.
- **Member — Ishtiyaq Al Noman:** Noakhali Science and Technology University, Computer Science and Telecommunication Engineering.

Confirm the official team name in the competition registration portal and ensure it matches the team-information documents before submission. Do not publish the team-information PDF or spreadsheet in a public repository if they contain identity numbers, student IDs, phone numbers, or private email addresses; provide those files only through the organizer's authorized submission channel when required.
