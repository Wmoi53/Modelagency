# ClubFin

A SharkFin-style personal-finance app for a soccer club. It shows where the money comes from and where it goes (Sankey and profit & loss), and models the flywheel that turns surplus into compounding growth:

```
results → fans → revenue → investment → better squad → results
```

Zero dependencies (Python 3.9+ stdlib). The ledger is a seeded sample ("Riverside FC") until you run `init`.

```bash
cd examples/clubfin
python -m clubfin serve          # dashboard at http://127.0.0.1:8000
python -m clubfin cashflow       # text Sankey in the terminal
python -m unittest discover -s tests
```

## Clickable elements

- Sankey nodes, income and expense rows: drill down to that group or category's transactions
- Profit & loss: click an expense group to expand its categories, click a category to drill down
- KPI cards: Reinvested opens the Flywheel, Net worth opens Net worth
- Month chips, Groups/Categories and Sankey/P&L toggles, sidebar and bottom-bar tabs
- Uncategorized: per-row category picker that updates cash flow and the badge instantly (view only; use `categorize` to save)
- Flywheel sliders

## All CLI commands

`python -m clubfin commands -v` prints this list from the parser itself (`--json` for tooling), so it never drifts.

| Command | What it does |
|---|---|
| `init [--seed N] [--force]` | write a sample ledger file (`clubfin-data.json`) to edit |
| `summary [--month YYYY-MM]` | income, expenses, reinvestment, net worth |
| `cashflow [--month] [--view groups\|categories]` | where the money came from and went |
| `spending` | month-by-month income, expenses, reinvestment rate |
| `networth` | assets, liabilities and net worth history |
| `accounts` | cash, reinvestment fund, assets and loan balances |
| `transactions [--month] [--category] [--search] [--limit]` | list and filter transactions |
| `uncategorized` | transactions that need a category |
| `categorize ID CATEGORY` | assign a category to a transaction |
| `categories` | list categories with type and group |
| `add DESC AMOUNT CATEGORY [--date]` | add a transaction (sign set from category type) |
| `compound PRINCIPAL RATE TURNS` | `principal × (1 + rate)^turns` |
| `flywheel [--revenue] [--reinvest] [--roi] [--turns-per-year]` | bear/base/bull at 1, 3, 5 years |
| `serve [--host] [--port]` | run the dashboard |
| `export [--out clubfin.html]` | write a standalone dashboard file |
| `commands [-v] [--json]` | list every CLI command |

Global option: `--data FILE` (default `./clubfin-data.json`, else the built-in sample).

## The compounding model

Growth per turn is `g = reinvest share × ROI`; revenue after `n` turns is `revenue × (1 + g)^n`. Bear and bull scale ROI by 0.5x and 1.5x. All rates are assumptions, not forecasts or promised returns; 10% per turn over 5 turns is 1.61x, not 1.5x.
