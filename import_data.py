"""Turn YOUR bank-statement CSV into data/transactions.csv. Runs locally; nothing is uploaded anywhere.
Descriptions are replaced by generic category labels (anonymised, and no free text can carry an injection).
Usage:
  python import_data.py statement.csv --date Date --desc Description --amount Amount --datefmt %d/%m/%Y
  python import_data.py statement.csv --date Date --desc Narration --debit Debit --credit Credit
Then edit data/profile.json (opening_balance, account_ccy) to match your account."""
import argparse, csv
from datetime import datetime
from pathlib import Path

KEYWORDS = {"Food": ["food", "cafe", "coffee", "restaurant", "7-eleven", "7eleven", "canteen", "grab food", "lunch", "market"],
            "Transport": ["grab", "bus", "taxi", "songthaew", "bolt", "train", "mrt", "bts", "fuel"],
            "Rent": ["rent", "dorm", "landlord", "apartment"], "Subscriptions": ["netflix", "spotify", "subscription", "youtube"],
            "Shopping": ["shop", "mall", "lazada", "shopee", "amazon", "store"],
            "Education": ["tuition", "university", "book", "course"]}

def categorize(desc: str, amount: float) -> str:
    d = desc.lower()
    for cat, words in KEYWORDS.items():
        if any(w in d for w in words): return cat
    return "Allowance" if amount > 0 else "Other"

def _amt(x) -> float:
    x = (x or "").replace(",", "").strip()
    return float(x) if x else 0.0

def convert(src, out, date_col, desc_col, amount_col=None, debit_col=None, credit_col=None, datefmt="%Y-%m-%d"):
    rows = []
    with open(src, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            amount = _amt(r[amount_col]) if amount_col else _amt(r.get(credit_col)) - _amt(r.get(debit_col))
            if amount == 0: continue
            cat = categorize(r[desc_col], amount)
            rows.append((datetime.strptime(r[date_col].strip(), datefmt).date().isoformat(), f"{cat} (imported)", cat, amount))
    if not rows: raise ValueError("No usable rows found. Check column names and --datefmt.")
    rows.sort()
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["date", "description", "category", "amount"]); w.writerows(rows)
    return len(rows)

if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("src"); a.add_argument("--date", required=True); a.add_argument("--desc", required=True)
    a.add_argument("--amount"); a.add_argument("--debit"); a.add_argument("--credit"); a.add_argument("--datefmt", default="%Y-%m-%d")
    a.add_argument("--out", default=str(Path(__file__).parent / "data" / "transactions.csv"))
    x = a.parse_args()
    if not x.amount and not (x.debit and x.credit): a.error("give --amount, or both --debit and --credit")
    print("imported rows:", convert(x.src, x.out, x.date, x.desc, x.amount, x.debit, x.credit, x.datefmt))
