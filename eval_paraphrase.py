"""Tests the scam-TEXT model on 40 hand-written messages that do NOT reuse the training phrases (unseen wording),
which is the honest test of generalisation (the synthetic hold-out set shares phrases with training, so it is optimistic).
Also measures latency per assessment.
  python eval_paraphrase.py                                    # default TF-IDF backend (runs offline)
  STUDYWALLET_TEXT_BACKEND=minilm python eval_paraphrase.py    # small Hugging Face encoder (22M params); needs sentence-transformers
"""
import time, fraud_model as f
SCAM = ["Hurry, your parcel is stuck, send a small clearance charge to release it", "Congratulations, you were picked for a reward, pay the handling cost to receive it",
 "Transfer now or your bank access will be frozen today", "Invest with us and get triple profit in a week, no risk", "Don't mention this to your family, just send the money quickly",
 "I'm your cousin and lost my wallet overseas, please wire me cash right now", "Buy vouchers from the store and read me the codes", "Tell me the code that just arrived on your phone to verify you",
 "Officer here: pay the fine immediately or you will be arrested", "Secret deal, whoever sends first doubles their deposit", "Pay a small release fee and your inheritance will be unlocked",
 "Your account shows suspicious activity, move your savings to this safe account", "Last chance to claim your prize, transfer the tax amount now", "Make it quick and keep it between us",
 "Crypto giveaway: send coins and get double back", "Pay the courier tax to receive your package, offer ends tonight", "Confirm your password and PIN to avoid account closure",
 "Easy income guaranteed, just put in a startup deposit", "Don't tell the bank, pay in prepaid cards", "Immediate payment required to avoid legal action"]
LEGIT = ["October accommodation payment", "Semester tuition installment", "Sharing the electricity bill for this month", "Monthly pocket money for my mother", "Paying back my friend for dinner",
 "Cost of the course textbooks", "Student bus pass top-up", "Deposit for the shared flat", "Mobile data package", "Doctor visit co-pay reimbursement", "Lab equipment fee", "Flight to visit family in December",
 "Library membership renewal", "Gift for my sister's birthday", "Groceries split with roommates", "Gym membership", "Registration fee for the exam", "Laundry card top-up", "Printing and stationery", "Rent for next month"]
def run():
    t = [(m, 1) for m in SCAM] + [(m, 0) for m in LEGIT]; f.scam_text_score("warm up")
    pred = [(f.scam_text_score(m) >= 0.5, y) for m, y in t]
    tp = sum(p and y for p, y in pred); fp = sum(p and not y for p, y in pred); fn = sum((not p) and y for p, y in pred); tn = sum((not p) and (not y) for p, y in pred)
    t0 = time.perf_counter(); N = 200
    for _ in range(N): f.assess(3000, "Dorm Landlord", "rent for october", 0, hour=14)
    ms = (time.perf_counter() - t0) / N * 1000
    return {"backend": f.backend_info(), "n": len(t), "accuracy": round((tp + tn) / len(t), 3), "scam_recall": round(tp / (tp + fn), 3),
            "false_alarm_rate": round(fp / (fp + tn), 3), "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn}, "avg_ms_per_assessment": round(ms, 2)}
if __name__ == "__main__": print(run())
