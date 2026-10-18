import streamlit as st
import agent, tools, auth, stakeholders, fraud_model

st.set_page_config(page_title="StudyWallet AI")
st.title("StudyWallet AI")
st.caption("AI financial assistant for international students. Demo data is SYNTHETIC; transfers are SIMULATED.")

# ---------------- OTP login gate ----------------
otp = st.session_state.setdefault("otp_session", auth.OTPSession())
if not otp.verified:
    st.subheader("Sign in")
    st.caption("Demo OTP login — no real SMS/email gateway is connected in this sandbox.")
    contact = st.text_input("Email or phone")
    if st.button("Send OTP") and contact:
        msg = auth.request_otp(otp, contact)
        st.session_state["otp_message"] = msg
    if st.session_state.get("otp_message"):
        st.info(st.session_state["otp_message"])
    code = st.text_input("Enter the 6-digit OTP", max_chars=6)
    if st.button("Verify OTP"):
        ok, msg = auth.verify_otp(otp, code)
        (st.success if ok else st.error)(msg)
        if ok: st.rerun()
    st.stop()

# ---------------- Wallet UI (only reachable after OTP verification) ----------------
lg = st.session_state.setdefault("ledger", tools.Ledger())
fraud_model.scam_text_score("warm up")   # train the small ML model once at start-up

with st.sidebar:
    b = tools.get_balance(lg); st.metric(f"Balance ({b['currency']})", f"{b['balance']:,.2f}")
    st.subheader("Pending transfers (human approval)")
    for code, p in list(lg.pending.items()):
        risk = p.get("risk", {}); st.write(f"{p['amount']:,.0f} to {p['payee']} [{code}]")
        ack = True
        if risk.get("level") in ("medium", "high"):
            (st.error if risk["level"] == "high" else st.warning)(f"ML scam/fraud risk: {risk['level'].upper()} ({risk['score']}). " + "; ".join(risk.get("reasons", [])))
            if risk["level"] == "high": ack = st.checkbox("I understand the risk", key="a" + code)
        c1, c2 = st.columns(2)
        if c1.button("Confirm", key="y" + code, disabled=not ack): tools.confirm_transfer(code, lg, acknowledged_risk=ack); st.rerun()
        if c2.button("Cancel", key="n" + code): tools.cancel_transfer(code, lg); st.rerun()
    st.subheader("Rate alerts")
    ra = tools.check_rate_alerts(lg)
    for r in ra["alerts"]:
        (st.error if r["triggered"] else st.success)(f"{r['pair']}: {r['current_rate']} (alert below {r['threshold']})" + (" - BELOW THRESHOLD" if r["triggered"] else ""))
    if not ra["alerts"]: st.caption("None. Try: 'alert me if thb to bdt drops 2%'")
    st.subheader("Audit log (hash-chained, tamper-evident)")
    st.code("\n".join(lg.audit[-12:]) or "empty")
    with st.expander("Authorised parties (permissioned ledger)"):
        for role, desc in stakeholders.ROLE_DESCRIPTIONS.items(): st.markdown(f"**{role}**: {desc}")
    st.caption(f"Chain integrity check: {'OK — chain + party signatures valid' if lg.verify_integrity() else 'FAILED — audit log was modified or forged'}")
    _provider = agent.current_provider()
    _mode_label = {"anthropic": "Claude API (cloud)", "groq": "Groq API — openai/gpt-oss-20b (cloud, free tier)",
                   "offline": "offline rule-based (no cloud key configured)"}[_provider]
    st.caption(f"AI mode: {_mode_label}")
    if _provider == "offline":
        st.caption("Set ANTHROPIC_API_KEY or GROQ_API_KEY (Streamlit secrets or environment) to enable cloud AI.")

st.session_state.setdefault("history", [])
for m in st.session_state.history: st.chat_message(m["role"]).write(m["content"])
if q := st.chat_input("e.g. 'Summarise my spending', '5000 baht to taka', 'send 3000 to Dorm Landlord'"):
    a = agent.run_agent(q, st.session_state.history, lg)
    st.session_state.history += [{"role": "user", "content": q}, {"role": "assistant", "content": a}]
    st.rerun()
