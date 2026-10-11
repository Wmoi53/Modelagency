# Crypto EMA breakdown

Three agents in `finance/` work as a pipeline, and `ema30.py` (Python 3.9+ stdlib) does the maths:

1. **Crypto Mover Scout** picks the top gainers and losers (liquid coins only).
2. **Crypto EMA Analyst** runs the 30-day EMA breakdown.
3. **Crypto Risk Reviewer** flags unreliable readings and adds the caveats.

```bash
python ema30.py                              # top 5 gainers + 5 losers, from CoinGecko (no key)
python ema30.py --top 10 --direction gainers
python ema30.py --ids bitcoin,solana,dogecoin --format json
python ema30.py --input prices.json          # offline: {"bitcoin": {"symbol": "btc", "prices": [...]}}
python -m unittest discover -s tests
```

EMA(30) uses alpha = 2/31, seeded with the average of the first 30 daily closes. Output per coin: price, EMA, gap to EMA, 5-day EMA slope, streak above or below, crosses in 30 days, 30-day change, trend label, and an "extended" flag beyond 20% from the EMA.

CoinMarketCap's free API has no daily history, so prices come from CoinGecko. To use CoinMarketCap's gainers/losers page for the mover list, paste the coins into `--ids` (CoinGecko ids). The free CoinGecko API is rate limited, so the script waits 2.5s between calls and retries on HTTP 429.

Not investment advice. An EMA describes the past, not the future.
