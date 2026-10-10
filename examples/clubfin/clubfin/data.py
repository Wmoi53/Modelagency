"""Sample club ledger generator plus JSON load/save.

Everything is deterministic (seeded) so tests and screenshots are stable.
"""
import json
import os
import random

DEFAULT_PATH = "clubfin-data.json"
CURRENCY = "£"

# category -> (type, group). type is income | expense | savings.
CATEGORIES = {
    "Matchday":            ("income", "Income"),
    "Broadcasting":        ("income", "Income"),
    "Sponsorship":         ("income", "Income"),
    "Merchandise":         ("income", "Income"),
    "Player trading":      ("income", "Income"),
    "Interest":            ("income", "Income"),
    "Player wages":        ("expense", "Squad"),
    "Bonuses & agents":    ("expense", "Squad"),
    "Academy staff":       ("expense", "Academy"),
    "Youth facilities":    ("expense", "Academy"),
    "Stadium upkeep":      ("expense", "Stadium"),
    "Matchday operations": ("expense", "Stadium"),
    "Marketing":           ("expense", "Fan growth"),
    "Digital & app":       ("expense", "Fan growth"),
    "Staff & admin":       ("expense", "Operations"),
    "Travel":              ("expense", "Operations"),
    "Medical":             ("expense", "Operations"),
    "Loan interest":       ("expense", "Debt"),
    "Reinvestment fund":   ("savings", "Savings"),
    "Uncategorized":       ("expense", "Uncategorized"),
}

# category -> (annual amount, merchants, monthly growth, seasonal)
INCOME = {
    "Matchday":       (3_100_000, ["Ticket office", "Hospitality", "Season passes"], 0.012, True),
    "Broadcasting":   (3_900_000, ["League media pool", "Streaming partner"], 0.004, False),
    "Sponsorship":    (2_900_000, ["Shirt sponsor", "Stadium naming", "Kit supplier"], 0.010, False),
    "Merchandise":    (  820_000, ["Club shop", "Online store"], 0.018, True),
    "Player trading": (1_250_000, ["Transfer fee received", "Loan fee received"], 0.0, False),
    "Interest":       (   45_000, ["Treasury deposit"], 0.0, False),
}
EXPENSE = {
    "Player wages":        (5_300_000, ["First-team payroll"], 0.004),
    "Bonuses & agents":    (  640_000, ["Agent fees", "Appearance bonuses"], 0.0),
    "Academy staff":       (  720_000, ["Academy payroll", "Coaching licences"], 0.006),
    "Youth facilities":    (  380_000, ["Training ground", "Youth kit"], 0.004),
    "Stadium upkeep":      (  760_000, ["Groundsmen", "Utilities", "Repairs"], 0.0),
    "Matchday operations": (  520_000, ["Stewarding", "Security", "Catering supplies"], 0.0),
    "Marketing":           (  410_000, ["Social ads", "Community events"], 0.015),
    "Digital & app":       (  330_000, ["Streaming platform", "Fan app dev"], 0.02),
    "Staff & admin":       (  690_000, ["Admin payroll", "Legal", "Audit"], 0.0),
    "Travel":              (  310_000, ["Away travel", "Hotels"], 0.0),
    "Medical":             (  240_000, ["Physio", "Sports science"], 0.0),
    "Loan interest":       (  280_000, ["Stadium loan"], 0.0),
}
# Share of every month's surplus swept into the reinvestment fund.
SWEEP = 0.95
SEASON = {1: 1.15, 2: 1.15, 3: 1.2, 4: 1.2, 5: 1.1, 6: 0.35, 7: 0.35,
          8: 1.0, 9: 1.15, 10: 1.2, 11: 1.15, 12: 1.3}

ACCOUNTS = [
    {"id": "op", "name": "Operating account", "kind": "cash", "balance": 1_840_000},
    {"id": "res", "name": "Reinvestment fund", "kind": "investment", "balance": 4_210_000},
    {"id": "stad", "name": "Stadium & grounds", "kind": "asset", "balance": 14_500_000},
    {"id": "reg", "name": "Player registrations", "kind": "asset", "balance": 6_300_000},
    {"id": "acad", "name": "Academy facilities", "kind": "asset", "balance": 2_100_000},
    {"id": "loan", "name": "Stadium loan", "kind": "liability", "balance": -7_800_000},
]
PROPERTIES = ["Stadium", "Training ground", "Academy"]


def _split(rng, total, n):
    cuts = sorted(rng.random() for _ in range(n - 1))
    parts, prev = [], 0.0
    for c in cuts + [1.0]:
        parts.append(round(total * (c - prev), 2))
        prev = c
    parts[-1] = round(total - sum(parts[:-1]), 2)
    return parts


def generate(seed=7, start=(2025, 10), months=12):
    rng = random.Random(seed)
    txns, nid = [], 1
    year, month = start
    for i in range(months):
        ym = f"{year}-{month:02d}"
        month_income = month_expense = 0.0
        rows = []
        for cat, (annual, merchants, growth, seasonal) in INCOME.items():
            base = annual / 12 * (1 + growth) ** i
            if seasonal:
                base *= SEASON[month]
            if cat == "Player trading" and month not in (1, 6, 7, 8):
                continue
            if cat == "Player trading":
                base = annual / 4
            for amt in _split(rng, base, min(len(merchants), 3)):
                rows.append((cat, rng.choice(merchants), amt))
        for cat, (annual, merchants, growth) in EXPENSE.items():
            base = annual / 12 * (1 + growth) ** i
            for amt in _split(rng, base, min(len(merchants), 3)):
                rows.append((cat, rng.choice(merchants), -amt))
        for cat, merchant, amt in rows:
            if amt > 0:
                month_income += amt
            else:
                month_expense += -amt
            day = rng.randint(1, 28)
            txns.append({"id": nid, "date": f"{ym}-{day:02d}", "desc": merchant,
                         "amount": round(amt, 2), "category": cat,
                         "account": "op"})
            nid += 1
        surplus = month_income - month_expense
        if surplus > 0:
            txns.append({"id": nid, "date": f"{ym}-28", "desc": "Sweep to reinvestment fund",
                         "amount": round(-surplus * SWEEP, 2), "category": "Reinvestment fund",
                         "account": "op"})
            nid += 1
        month += 1
        if month == 13:
            year, month = year + 1, 1
    # A handful of unreviewed items, like the "Uncategorized" inbox.
    for desc, amt in [("Card payment 4471", -61_480.0), ("Wire ref 90213", -83_900.0),
                      ("POS refund", -12_360.0), ("Unknown debit", -78_960.0)]:
        txns.append({"id": nid, "date": f"{year}-{month - 1 if month > 1 else 12:02d}-{rng.randint(1, 27):02d}",
                     "desc": desc, "amount": amt, "category": "Uncategorized",
                     "account": "op"})
        nid += 1
    txns.sort(key=lambda t: (t["date"], t["id"]))
    return {"club": "Riverside FC", "currency": CURRENCY, "categories": {
        k: {"type": v[0], "group": v[1]} for k, v in CATEGORIES.items()},
        "accounts": ACCOUNTS, "properties": PROPERTIES, "transactions": txns,
        "networth_history": _networth_history(rng, months, start)}


def _networth_history(rng, months, start):
    year, month = start
    nw = 17_000_000.0
    out = []
    for _ in range(months):
        nw *= 1 + 0.014 + rng.uniform(-0.002, 0.004)
        out.append({"month": f"{year}-{month:02d}", "value": round(nw)})
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return out


def load(path=None):
    path = path or DEFAULT_PATH
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return generate()


def save(data, path=None):
    path = path or DEFAULT_PATH
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
    return path
