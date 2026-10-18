"""ML fraud / scam alert (advisory layer). Two small, explainable logistic-regression models:
  1) TEXT model  - TF-IDF + LogisticRegression: does the note/message read like a scam (urgency, gift cards,
                   'don't tell anyone', advance-fee, crypto 'guaranteed returns', ...)?
  2) TRANSFER model - LogisticRegression on [amount vs. cap, unfamiliar payee, night-time, burst of proposals, text score].
The ML score can only ESCALATE (warn / demand an explicit acknowledgement). It can never relax a guardrail:
the allow-list, caps and the human-confirmation step stay authoritative.
HONESTY: both models are trained at start-up on SYNTHETIC data generated here (no real customer data exists in this
sandbox), so reported metrics are optimistic demo numbers, not real-world accuracy. Fallback: keyword heuristic if
scikit-learn is not installed."""
import os, random, re, threading, time
import guardrails as g

try:
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score
    SK = True
except ImportError:
    SK = False

SCAM = ["urgent", "act now immediately", "gift card", "do not tell anyone", "keep this secret", "guaranteed returns",
        "double your money", "crypto investment", "bitcoin", "processing fee", "verification fee", "customs fee", "you won a prize",
        "lottery winner", "your account will be suspended", "police warrant", "wire transfer today", "send otp", "share your pin",
        "i am stuck abroad send money", "advance fee", "limited time offer", "claim your reward", "pay in gift cards"]
LEGIT = ["rent for october", "tuition fee semester", "monthly phone plan", "allowance for mom", "groceries and books", "dorm deposit",
         "library fine", "thank you for lunch", "internet bill", "bus pass", "lab fee", "textbook purchase", "flight ticket home",
         "health insurance premium", "shared taxi cost", "birthday gift for mom", "urgent: tuition due friday", "please pay my share of rent"]
FILL = ["please", "for", "the", "my", "payment", "now", "to", "send", "thanks", "this", "week", "ok", "hello", "hi", "regarding"]

def _text(rng, scam):
    parts = rng.sample(SCAM if scam else LEGIT, rng.choice([1, 1, 2]))
    if rng.random() < 0.12: parts.append(rng.choice(LEGIT if scam else SCAM))     # label noise / hard cases
    words = " ".join(parts).split() + rng.sample(FILL, rng.randint(1, 4)); rng.shuffle(words)
    return " ".join(words)

def _corpus(seed, n):
    rng = random.Random(seed); y = [rng.random() < 0.4 for _ in range(n)]
    return [_text(rng, s) for s in y], [int(s) for s in y]

_FEATS = ["amount_vs_cap", "unfamiliar_payee", "night_time", "burst_of_proposals", "scam_wording"]
_LABELS = {"amount_vs_cap": "large amount relative to your limit", "unfamiliar_payee": "unfamiliar payee",
           "night_time": "unusual time of day", "burst_of_proposals": "many proposals in a short time", "scam_wording": "scam-like wording"}

def _transfers(seed, n, text_p):
    rng = random.Random(seed); X, y = [], []
    for _ in range(n):
        fraud = rng.random() < 0.12
        if fraud:
            amt = min(1.0, rng.betavariate(5, 2)); unf = int(rng.random() < 0.55); night = int(rng.random() < 0.45)
            burst = min(1.0, rng.randint(1, 6) / 5); sw = text_p(_text(rng, rng.random() < 0.7))
        else:
            amt = rng.betavariate(2, 5); unf = int(rng.random() < 0.03); night = int(rng.random() < 0.07)
            burst = min(1.0, rng.randint(0, 2) / 5); sw = text_p(_text(rng, rng.random() < 0.04))
        X.append([amt, unf, night, burst, sw]); y.append(int(fraud))
    return X, y

_lock, _M = threading.Lock(), {}
_MINILM = "sentence-transformers/all-MiniLM-L6-v2"      # 22M parameters, 384-dim embeddings, Apache-2.0
def _train():
    """Default backend: TF-IDF + logistic regression (tiny, offline, ~1 s start-up, <1 ms per message).
    Optional backend: set STUDYWALLET_TEXT_BACKEND=minilm to use a small Hugging Face encoder (all-MiniLM-L6-v2)
    as the text featuriser with the same logistic-regression head. It needs `pip install sentence-transformers`
    and a one-time ~90 MB download; if anything fails it silently falls back to the default backend."""
    with _lock:
        if _M: return _M
        txt, y = _corpus(7, 1500)
        backend, note = "tfidf", ""
        if os.environ.get("STUDYWALLET_TEXT_BACKEND", "").lower() == "minilm":
            try:
                from sentence_transformers import SentenceTransformer
                enc = SentenceTransformer(_MINILM)
                tm = LogisticRegression(max_iter=1000).fit(enc.encode(txt, batch_size=64), y)
                tp = lambda s: float(tm.predict_proba(enc.encode([s]))[0][1])
                backend = "minilm"; vec = None
            except Exception as e:
                note = f"minilm unavailable ({type(e).__name__}); fell back to tfidf"
        if backend == "tfidf":
            vec = TfidfVectorizer(ngram_range=(1, 2), min_df=2); tm = LogisticRegression(max_iter=500).fit(vec.fit_transform(txt), y)
            tp = lambda s: float(tm.predict_proba(vec.transform([s]))[0][1])
        X, yy = _transfers(11, 3000, tp)
        fm = LogisticRegression(max_iter=500, class_weight="balanced").fit(np.array(X), yy)
        _M.update(vec=vec, tm=tm, fm=fm, tp=tp, backend=backend, note=note)
        return _M

def backend_info():
    m = _train(); return {"text_backend": m["backend"], "note": m["note"]}

def scam_text_score(note: str) -> float:
    if not note or not note.strip(): return 0.0
    if not SK: return min(1.0, sum(k in note.lower() for k in SCAM) / 2)
    return _train()["tp"](note.lower())

def _scam_terms(note, m, k=3):
    if m["vec"] is None: return []                    # embedding backend has no per-word weights
    v, c = m["vec"], m["tm"].coef_[0]; names = v.get_feature_names_out(); row = v.transform([note.lower()]).tocoo()
    hits = sorted(((c[j] * val, names[j]) for j, val in zip(row.col, row.data) if c[j] > 0.3 and len(names[j]) > 3), reverse=True)
    return [n for _, n in hits[:k]]

def assess(amount, payee, note="", recent_proposals=0, hour=None):
    """Returns {'score': 0..1, 'level': 'low'|'medium'|'high', 'reasons': [...], 'model': str}."""
    hour = time.localtime().tm_hour if hour is None else hour
    unf = int(payee not in g.ALLOWED_PAYEES); night = int(hour < 5)
    if not SK:
        s = scam_text_score(note); score = min(1.0, 0.5 * s + 0.3 * (amount / g.MAX_SINGLE) + 0.2 * night + 0.2 * unf)
        reasons = ["scam-like wording"] if s > 0.4 else []; model = "keyword heuristic (scikit-learn not installed)"
    else:
        m = _train(); sw = scam_text_score(note)
        x = [min(1.0, amount / g.MAX_SINGLE), unf, night, min(1.0, recent_proposals / 5), sw]
        score = float(m["fm"].predict_proba(np.array([x]))[0][1])
        contrib = sorted(((c * v, f) for c, v, f in zip(m["fm"].coef_[0], x, _FEATS)), reverse=True)
        reasons = [_LABELS[f] for cv, f in contrib if cv > 0.8 and f != "scam_wording"][:3]
        if sw > 0.5:
            terms = _scam_terms(note, m); reasons.insert(0, "scam-like wording" + (f" ({', '.join(terms)})" if terms else ""))
        model = f"logistic regression ({m['backend']} text features), trained on synthetic data"
    level = "high" if score >= 0.7 else "medium" if score >= 0.4 else "low"
    if level == "low": reasons = []
    return {"score": round(score, 3), "level": level, "reasons": reasons, "model": model}

def evaluate():
    """Hold-out metrics on freshly generated SYNTHETIC data (different seeds from training). Optimistic by construction."""
    if not SK: return {"error": "scikit-learn not installed"}
    m = _train(); txt, y = _corpus(99, 800)
    p = np.array([m["tp"](t) for t in txt]); yp = (p >= 0.5).astype(int)
    X, yy = _transfers(123, 2000, m["tp"]); q = m["fm"].predict_proba(np.array(X))[:, 1]; yq = (q >= 0.4).astype(int)
    r = lambda v: round(float(v), 3)
    return {"text_model": {"n": len(y), "accuracy": r(accuracy_score(y, yp)), "precision": r(precision_score(y, yp)), "recall": r(recall_score(y, yp)), "auc": r(roc_auc_score(y, p))},
            "transfer_model": {"n": len(yy), "fraud_rate": r(sum(yy) / len(yy)), "precision": r(precision_score(yy, yq)), "recall": r(recall_score(yy, yq)), "auc": r(roc_auc_score(yy, q))},
            "caveat": "Synthetic data generated by this project; not real-world performance."}
