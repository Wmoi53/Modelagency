#!/usr/bin/env python3
"""30-day EMA breakdown for the top moving coins (stdlib only).

Movers come from CoinGecko's free markets endpoint (24h change, top-N by market
cap, minimum volume). Each mover's daily closes feed a 30-day EMA with a plain
breakdown: price vs EMA, EMA slope, streak, crosses and a trend label.

    python ema30.py                     # top 5 gainers + 5 losers, markdown
    python ema30.py --ids bitcoin,solana --format json
    python ema30.py --input prices.json # offline: {"bitcoin": {"symbol":"btc","prices":[...]}}

Research tooling, not investment advice. Crypto is volatile; an EMA describes
the past and does not predict returns.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.coingecko.com/api/v3"
SPAN = 30
EXTENDED = 0.20  # |price/EMA - 1| beyond this is flagged as stretched


def ema(values, span=SPAN):
    """EMA seeded with the SMA of the first `span` values (None until seeded)."""
    if span < 2 or len(values) < span:
        raise ValueError(f"need at least {span} closes for a {span}-day EMA, got {len(values)}")
    k = 2 / (span + 1)
    e = sum(values[:span]) / span
    out = [None] * (span - 1) + [e]
    for v in values[span:]:
        e = v * k + e * (1 - k)
        out.append(e)
    return out


def breakdown(prices, span=SPAN):
    """Describe where the last close sits against its EMA."""
    e = ema(prices, span)
    pairs = [(p, x) for p, x in zip(prices, e) if x is not None]
    side = [1 if p > x else -1 for p, x in pairs]
    streak = 1
    while streak < len(side) and side[-1 - streak] == side[-1]:
        streak += 1
    window = side[-span:]
    crosses = sum(1 for a, b in zip(window, window[1:]) if a != b)
    since_cross = streak if streak < len(side) else None  # None: no cross in history
    price, ema_now = prices[-1], e[-1]
    gap = price / ema_now - 1
    slope = e[-1] / e[-6] - 1 if len(pairs) >= 6 else 0.0
    above = side[-1] > 0
    if above and slope > 0:
        trend = "Uptrend"
    elif above:
        trend = "Weakening uptrend"
    elif slope < 0:
        trend = "Downtrend"
    else:
        trend = "Recovering"
    return {
        "price": price, "ema": ema_now, "gap_pct": gap * 100,
        "ema_slope_5d_pct": slope * 100,
        "streak_days": streak * side[-1], "days_since_cross": since_cross,
        "crosses_30d": crosses, "trend": trend, "extended": abs(gap) > EXTENDED,
        "change_30d_pct": (price / prices[-1 - min(30, len(prices) - 1)] - 1) * 100,
    }


def select_movers(markets, top=5, direction="both", min_volume=5e7):
    """Pick biggest 24h gainers/losers among liquid coins."""
    liquid = [m for m in markets
              if (m.get("total_volume") or 0) >= min_volume
              and m.get("price_change_percentage_24h_in_currency") is not None]
    liquid.sort(key=lambda m: m["price_change_percentage_24h_in_currency"], reverse=True)
    out = []
    if direction in ("gainers", "both"):
        out += liquid[:top]
    if direction in ("losers", "both"):
        out += [m for m in liquid[::-1][:top] if m not in out]
    return out


def _get(path, params, retries=4):
    url = f"{API}{path}?{urllib.parse.urlencode(params)}"
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ema30/0.1"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as err:
            if err.code == 429 and attempt < retries - 1:
                time.sleep(15 * (attempt + 1))
                continue
            raise


def fetch_markets(universe=100):
    return _get("/coins/markets", {
        "vs_currency": "usd", "order": "market_cap_desc", "per_page": universe,
        "page": 1, "price_change_percentage": "24h,7d,30d"})


def fetch_prices(coin_id, days=90):
    data = _get(f"/coins/{coin_id}/market_chart",
                {"vs_currency": "usd", "days": days, "interval": "daily"})
    return [p[1] for p in data["prices"]]


def collect(args):
    if args.input:
        with open(args.input, encoding="utf-8") as fh:
            raw = json.load(fh)
        return [dict(id=k, symbol=v.get("symbol", k), move24=v.get("change_24h"), **{"prices": v["prices"]})
                for k, v in raw.items()]
    if args.ids:
        movers = [{"id": i, "symbol": i} for i in args.ids.split(",")]
    else:
        movers = select_movers(fetch_markets(args.universe), args.top, args.direction, args.min_volume)
    rows = []
    for m in movers:
        time.sleep(args.delay)  # stay inside the free-tier rate limit
        rows.append({"id": m["id"], "symbol": m.get("symbol", m["id"]),
                     "move24": m.get("price_change_percentage_24h_in_currency"),
                     "prices": fetch_prices(m["id"], args.days)})
    return rows


def analyse(rows, span=SPAN):
    out, skipped = [], []
    for r in rows:
        try:
            b = breakdown(r["prices"], span)
        except ValueError as err:
            skipped.append((r["id"], str(err)))
            continue
        out.append({"id": r["id"], "symbol": r["symbol"].upper(), "change_24h_pct": r.get("move24"), **b})
    return out, skipped


def _p(v):
    return f"{v:,.2f}" if abs(v) >= 1 else f"{v:.4f}"


def to_markdown(results, skipped, span=SPAN):
    lines = [f"# {span}-day EMA breakdown: top moving coins", "",
             "| Coin | 24h | Price | EMA | vs EMA | EMA slope 5d | Streak | Crosses 30d | 30d | Trend |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for r in results:
        c24 = "n/a" if r["change_24h_pct"] is None else f"{r['change_24h_pct']:+.1f}%"
        flag = " ⚠ extended" if r["extended"] else ""
        lines.append(f"| {r['symbol']} | {c24} | ${_p(r['price'])} | ${_p(r['ema'])} | {r['gap_pct']:+.1f}% | "
                     f"{r['ema_slope_5d_pct']:+.2f}% | {r['streak_days']:+d}d | {r['crosses_30d']} | "
                     f"{r['change_30d_pct']:+.1f}% | {r['trend']}{flag} |")
    above = sum(1 for r in results if r["gap_pct"] > 0)
    lines += ["", f"**Breadth:** {above} of {len(results)} movers are above their {span}-day EMA. "
              f"Streak is consecutive days on the current side of the EMA (+ above, - below). "
              f"Crosses counts side changes in the last {span} days; many crosses mean a choppy, "
              f"low-signal EMA."]
    for coin, why in skipped:
        lines.append(f"- skipped {coin}: {why}")
    lines += ["", "_Not investment advice. An EMA describes the past, not the future._"]
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--top", type=int, default=5, help="movers per side")
    p.add_argument("--direction", choices=["gainers", "losers", "both"], default="both")
    p.add_argument("--universe", type=int, default=100, help="top-N by market cap to scan")
    p.add_argument("--min-volume", type=float, default=5e7, dest="min_volume", help="24h USD volume floor")
    p.add_argument("--ids", help="comma-separated CoinGecko ids; skips mover selection")
    p.add_argument("--days", type=int, default=90, help="history to fetch (>= span)")
    p.add_argument("--span", type=int, default=SPAN)
    p.add_argument("--delay", type=float, default=2.5, help="seconds between API calls")
    p.add_argument("--input", help="offline JSON of prices instead of the API")
    p.add_argument("--format", choices=["markdown", "json"], default="markdown")
    args = p.parse_args(argv)
    try:
        rows = collect(args)
    except (urllib.error.URLError, OSError) as err:
        print(f"could not reach CoinGecko ({err}); use --input for offline data", file=sys.stderr)
        return 2
    results, skipped = analyse(rows, args.span)
    print(json.dumps({"results": results, "skipped": skipped}, indent=1) if args.format == "json"
          else to_markdown(results, skipped, args.span))
    return 0


if __name__ == "__main__":
    sys.exit(main())
