"""Pure functions over the ledger: cash flow, spending, net worth, compounding."""
from collections import defaultdict


def money(value, cur="£", signed=False):
    sign = "-" if value < 0 else ("+" if signed and value > 0 else "")
    return f"{sign}{cur}{abs(value):,.2f}"


def filter_txns(data, month=None, category=None, search=None, account=None):
    out = []
    for t in data["transactions"]:
        if month and not t["date"].startswith(month):
            continue
        if category and t["category"].lower() != category.lower():
            continue
        if account and t["account"] != account:
            continue
        if search and search.lower() not in t["desc"].lower():
            continue
        out.append(t)
    return out


def cashflow(data, month=None):
    """Income by category, expenses by group/category, savings, rate."""
    cats = data["categories"]
    income, exp_group, exp_cat, savings = defaultdict(float), defaultdict(float), defaultdict(float), 0.0
    for t in filter_txns(data, month=month):
        info = cats.get(t["category"], {"type": "expense", "group": "Uncategorized"})
        if info["type"] == "income":
            income[t["category"]] += t["amount"]
        elif info["type"] == "savings":
            savings += -t["amount"]
        else:
            exp_group[info["group"]] += -t["amount"]
            exp_cat[t["category"]] += -t["amount"]
    total_in = sum(income.values())
    total_out = sum(exp_group.values())
    return {"income": dict(income), "expense_groups": dict(exp_group),
            "expense_categories": dict(exp_cat), "savings": savings,
            "total_income": total_in, "total_expenses": total_out,
            "net": total_in - total_out,
            "savings_rate": savings / total_in if total_in else 0.0}


def monthly(data):
    months = sorted({t["date"][:7] for t in data["transactions"]})
    return [(m, cashflow(data, m)) for m in months]


def networth(data):
    assets = [a for a in data["accounts"] if a["balance"] >= 0]
    liabilities = [a for a in data["accounts"] if a["balance"] < 0]
    a, l = sum(x["balance"] for x in assets), sum(x["balance"] for x in liabilities)
    return {"assets": a, "liabilities": l, "net_worth": a + l,
            "history": data.get("networth_history", [])}


def compound(principal, rate, turns):
    """principal * (1 + rate) ** turns, e.g. 10% over 5 turns is 1.61x."""
    return principal * (1 + rate) ** turns


def flywheel(revenue, reinvest_share, roi, turns_per_year, years):
    """One turn: revenue funds reinvestment, reinvestment returns roi as extra revenue.

    growth per turn g = reinvest_share * roi ; revenue_n = revenue * (1 + g) ** n
    """
    g = reinvest_share * roi
    n = turns_per_year * years
    rows, rev = [], revenue
    for turn in range(1, n + 1):
        invested = rev * reinvest_share
        rev = rev * (1 + g)
        rows.append({"turn": turn, "invested": invested, "revenue": rev})
    return {"growth_per_turn": g, "turns": n, "multiple": (1 + g) ** n,
            "end_revenue": rev, "rows": rows}


SCENARIOS = {"bear": 0.5, "base": 1.0, "bull": 1.5}
