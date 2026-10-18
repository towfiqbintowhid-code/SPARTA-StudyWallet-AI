"""Demo OTP authentication gate.
No real SMS/email gateway is wired up here (that needs a paid provider + phone/email verification infra),
so in this sandbox the OTP is generated server-side and shown on screen, clearly labelled DEMO MODE.
Swap `_deliver_otp()` for a real SMS/email API call to go to production.
"""
import hashlib, hmac, secrets, time

OTP_TTL_SECONDS = 300      # 5 minutes
MAX_ATTEMPTS = 3

class OTPSession:
    def __init__(self):
        self.contact = None
        self.code = None
        self.code_hash = None
        self.salt = ""
        self.issued_at = 0.0
        self.attempts = 0
        self.verified = False

def _deliver_otp(contact: str, code: str):
    """Sandbox stand-in for an SMS/email gateway. Replace with a real provider call in production."""
    return f"[DEMO MODE] OTP for {contact}: {code} (demo only — in production this is sent by SMS/email and never shown on screen)"

def _digest(code: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}|{code}".encode()).hexdigest()

def request_otp(session: OTPSession, contact: str) -> str:
    session.contact = contact
    code = f"{secrets.randbelow(1_000_000):06d}"      # cryptographically secure RNG (not `random`)
    session.salt = secrets.token_hex(8)
    session.code_hash = _digest(code, session.salt)   # only a salted hash is kept server-side
    session.code = code                               # kept only so the DEMO can display it; drop in production
    session.issued_at = time.time()
    session.attempts = 0
    session.verified = False
    return _deliver_otp(contact, code)

def verify_otp(session: OTPSession, entered_code: str):
    if session.code_hash is None:
        return False, "No OTP was requested yet."
    if time.time() - session.issued_at > OTP_TTL_SECONDS:
        return False, "OTP expired. Please request a new one."
    if session.attempts >= MAX_ATTEMPTS:
        return False, "Too many incorrect attempts. Please request a new OTP."
    session.attempts += 1
    if hmac.compare_digest(_digest(entered_code.strip(), session.salt), session.code_hash):   # constant-time compare
        session.verified = True
        return True, "OTP verified."
    remaining = MAX_ATTEMPTS - session.attempts
    return False, f"Incorrect OTP. {remaining} attempt(s) left."
