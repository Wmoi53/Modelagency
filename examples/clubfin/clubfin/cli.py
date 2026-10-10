"""ClubFin command line. Run `python -m clubfin commands` to list every command."""
import argparse
import json
import os
import sys

from . import analytics as an
from . import data as dt

BAR = 28


def _bar(share):
    return "█" * max(0, round(min(1.0, share) * BAR))


def _cur(d):
    return d.get("currency", dt.CURRENCY)


def _load(args):
    return dt.load(args.data)


def cmd_init(args):
    path = args.data or dt.DEFAULT_PATH
    if os.path.exists(path) and not args.force:
        print(f"{path} exists (use --force to overwrite)")
        return 1
    dt.save(dt.generate(seed=args.seed), path)
    print(f"wrote sample ledger to {path}")
    return 0


def cmd_summary(args):
    d = _load(args)
    cur = _cur(d)
    cf, nw = an.cashflow(d, args.month), an.networth(d)
    print(f"{d['club']}  ·  {args.month or 'all periods'}")
    print(f"  Income        {an.money(cf['total_income'], cur):>18}")
    print(f"  Expenses      {an.money(-cf['total_expenses'], cur):>18}")
    print(f"  Reinvested    {an.money(cf['savings'], cur):>18}  ({cf['savings_rate']:.1%} of income)")
    print(f"  Net worth     {an.money(nw['net_worth'], cur):>18}")
    return 0


def cmd_cashflow(args):
    d = _load(args)
    cur = _cur(d)
    cf = an.cashflow(d, args.month)
    total = cf["total_income"] or 1
    print("Where the money came from")
    for k, v in sorted(cf["income"].items(), key=lambda kv: -kv[1]):
        print(f"  {k:<22}{an.money(v, cur):>18} {v / total:>6.1%}  {_bar(v / total)}")
    print(f"\nWhere the money went ({args.view})")
    rows = cf["expense_categories" if args.view == "categories" else "expense_groups"]
    items = sorted(rows.items(), key=lambda kv: -kv[1])
    items.append(("Reinvestment fund", cf["savings"]))
    for k, v in sorted(items, key=lambda kv: -kv[1]):
        print(f"  {k:<22}{an.money(v, cur):>18} {v / total:>6.1%}  {_bar(v / total)}")
    return 0


def cmd_spending(args):
    d = _load(args)
    cur = _cur(d)
    print(f"{'Month':<9}{'Income':>16}{'Expenses':>16}{'Reinvested':>16}{'Rate':>8}")
    for m, cf in an.monthly(d):
        print(f"{m:<9}{an.money(cf['total_income'], cur):>16}{an.money(cf['total_expenses'], cur):>16}"
              f"{an.money(cf['savings'], cur):>16}{cf['savings_rate']:>8.1%}")
    return 0


def cmd_networth(args):
    d = _load(args)
    cur = _cur(d)
    nw = an.networth(d)
    print(f"Assets       {an.money(nw['assets'], cur):>18}")
    print(f"Liabilities  {an.money(nw['liabilities'], cur):>18}")
    print(f"Net worth    {an.money(nw['net_worth'], cur):>18}\n")
    hist = nw["history"]
    top = max((h["value"] for h in hist), default=1)
    for h in hist:
        print(f"  {h['month']}  {an.money(h['value'], cur):>16}  {_bar(h['value'] / top)}")
    return 0


def cmd_accounts(args):
    d = _load(args)
    cur = _cur(d)
    for a in d["accounts"]:
        print(f"  {a['id']:<6}{a['name']:<26}{a['kind']:<12}{an.money(a['balance'], cur):>18}")
    return 0


def _print_txns(d, rows, limit):
    cur = _cur(d)
    for t in rows[-limit:] if limit else rows:
        print(f"  {t['id']:>4}  {t['date']}  {t['desc']:<28}{t['category']:<22}{an.money(t['amount'], cur, True):>18}")
    print(f"({len(rows)} matching)")


def cmd_transactions(args):
    d = _load(args)
    _print_txns(d, an.filter_txns(d, args.month, args.category, args.search), args.limit)
    return 0


def cmd_uncategorized(args):
    d = _load(args)
    _print_txns(d, an.filter_txns(d, category="Uncategorized"), 0)
    return 0


def cmd_categorize(args):
    d = _load(args)
    if args.category not in d["categories"]:
        print(f"unknown category {args.category!r}; run `categories`", file=sys.stderr)
        return 2
    for t in d["transactions"]:
        if t["id"] == args.id:
            t["category"] = args.category
            print(f"saved to {dt.save(d, args.data)}")
            return 0
    print(f"no transaction {args.id}", file=sys.stderr)
    return 2


def cmd_categories(args):
    d = _load(args)
    for name, info in d["categories"].items():
        print(f"  {name:<22}{info['type']:<9}{info['group']}")
    return 0


def cmd_add(args):
    d = _load(args)
    if args.category not in d["categories"]:
        print(f"unknown category {args.category!r}; run `categories`", file=sys.stderr)
        return 2
    amount = abs(args.amount)
    if d["categories"][args.category]["type"] != "income":
        amount = -amount
    nid = max((t["id"] for t in d["transactions"]), default=0) + 1
    d["transactions"].append({"id": nid, "date": args.date, "desc": args.desc,
                              "amount": amount, "category": args.category, "account": "op"})
    print(f"added #{nid}; saved to {dt.save(d, args.data)}")
    return 0


def cmd_compound(args):
    end = an.compound(args.principal, args.rate, args.turns)
    print(f"{args.principal:,.2f} at {args.rate:.1%} per turn for {args.turns} turns "
          f"= {end:,.2f}  ({end / args.principal:.2f}x)")
    return 0


def cmd_flywheel(args):
    d = _load(args)
    cur = _cur(d)
    revenue = args.revenue or an.cashflow(d)["total_income"]
    print(f"Flywheel on {an.money(revenue, cur)} revenue, reinvest {args.reinvest:.0%}, "
          f"{args.turns_per_year} turn(s)/year")
    print("results → fans → revenue → investment → better squad → results\n")
    print(f"  {'case':<6}{'ROI/turn':>10}{'g/turn':>9}" + "".join(f"{y}y".rjust(16) for y in (1, 3, 5)))
    for name, mult in an.SCENARIOS.items():
        roi = args.roi * mult
        cells = []
        for y in (1, 3, 5):
            r = an.flywheel(revenue, args.reinvest, roi, args.turns_per_year, y)
            cells.append(f"{r['multiple']:.2f}x".rjust(16))
        print(f"  {name:<6}{roi:>10.1%}{args.reinvest * roi:>9.1%}" + "".join(cells))
    print("\nBear/base/bull scale the base ROI by 0.5x/1x/1.5x. Assumed rates, not forecasts or promised returns.")
    return 0


def _page(args):
    from . import server
    return server.render(_load(args))


def cmd_serve(args):
    from . import server
    server.serve(_load(args), args.host, args.port)
    return 0


def cmd_export(args):
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(_page(args))
    print(f"wrote {args.out}")
    return 0


def cmd_commands(args):
    parser = build_parser()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    helps = {c.dest: c.help for c in sub._choices_actions}
    if args.json:
        print(json.dumps({n: {"help": helps.get(n), "usage": p.format_usage().strip()}
                          for n, p in sub.choices.items()}, indent=1))
        return 0
    prog = parser.prog
    for name, p in sub.choices.items():
        opts = " ".join(o for a in p._actions for o in a.option_strings if o.startswith("--") and o != "--help")
        print(f"  {prog} {name:<14} {helps.get(name, '')}")
        if opts and args.verbose:
            print(f"  {'':>{len(prog) + 1}}{'':<14} options: {opts}")
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog="python -m clubfin",
                                description="ClubFin: where the club's money comes from and goes, "
                                            "and how reinvestment compounds.")
    p.add_argument("--data", help=f"ledger file (default ./{dt.DEFAULT_PATH}, else built-in sample)")
    s = p.add_subparsers(dest="command", required=True, metavar="command")

    def add(name, fn, help_, **kw):
        sp = s.add_parser(name, help=help_, **kw)
        sp.set_defaults(fn=fn)
        return sp

    sp = add("init", cmd_init, "write a sample ledger file to edit")
    sp.add_argument("--seed", type=int, default=7)
    sp.add_argument("--force", action="store_true")
    sp = add("summary", cmd_summary, "income, expenses, reinvestment, net worth")
    sp.add_argument("--month", help="YYYY-MM")
    sp = add("cashflow", cmd_cashflow, "where the money came from and went (text Sankey)")
    sp.add_argument("--month", help="YYYY-MM")
    sp.add_argument("--view", choices=["groups", "categories"], default="groups")
    add("spending", cmd_spending, "month-by-month income, expenses, reinvestment rate")
    add("networth", cmd_networth, "assets, liabilities and net worth history")
    add("accounts", cmd_accounts, "cash, fund, asset and loan balances")
    sp = add("transactions", cmd_transactions, "list and filter transactions")
    sp.add_argument("--month")
    sp.add_argument("--category")
    sp.add_argument("--search")
    sp.add_argument("--limit", type=int, default=25)
    add("uncategorized", cmd_uncategorized, "transactions that need a category")
    sp = add("categorize", cmd_categorize, "assign a category to a transaction")
    sp.add_argument("id", type=int)
    sp.add_argument("category")
    add("categories", cmd_categories, "list categories with type and group")
    sp = add("add", cmd_add, "add a transaction (sign set from the category type)")
    sp.add_argument("desc")
    sp.add_argument("amount", type=float)
    sp.add_argument("category")
    sp.add_argument("--date", default="2026-09-30")
    sp = add("compound", cmd_compound, "principal * (1 + rate) ** turns")
    sp.add_argument("principal", type=float)
    sp.add_argument("rate", type=float, help="per-turn rate, e.g. 0.10")
    sp.add_argument("turns", type=int)
    sp = add("flywheel", cmd_flywheel, "model the reinvestment loop: bear/base/bull at 1, 3, 5 years")
    sp.add_argument("--revenue", type=float, help="default: ledger income")
    sp.add_argument("--reinvest", type=float, default=0.25, help="share of revenue reinvested per turn")
    sp.add_argument("--roi", type=float, default=0.30, help="base revenue return on reinvested money per turn")
    sp.add_argument("--turns-per-year", type=int, default=1, dest="turns_per_year")
    sp = add("serve", cmd_serve, "open the dashboard in a browser (http://localhost:8000)")
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--port", type=int, default=8000)
    sp = add("export", cmd_export, "write a standalone dashboard HTML file")
    sp.add_argument("--out", default="clubfin.html")
    sp = add("commands", cmd_commands, "list every CLI command")
    sp.add_argument("--verbose", "-v", action="store_true", help="also show each command's options")
    sp.add_argument("--json", action="store_true")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.fn(args)
