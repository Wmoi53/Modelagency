import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import ema30  # noqa: E402


def series(n, start=100.0, step=1.0):
    return [start + i * step for i in range(n)]


class EmaTests(unittest.TestCase):
    def test_constant_series_is_flat(self):
        e = ema30.ema([50.0] * 40)
        self.assertEqual(e[:29], [None] * 29)
        self.assertTrue(all(abs(x - 50.0) < 1e-9 for x in e[29:]))

    def test_seed_is_sma_and_next_value_uses_alpha(self):
        vals = list(range(1, 32))  # 1..31
        e = ema30.ema(vals)
        self.assertAlmostEqual(e[29], 15.5)  # mean of 1..30
        self.assertAlmostEqual(e[30], 31 * (2 / 31) + 15.5 * (29 / 31))

    def test_too_short_raises(self):
        with self.assertRaises(ValueError):
            ema30.ema([1.0] * 10)

    def test_uptrend_label_and_streak(self):
        b = ema30.breakdown(series(90))
        self.assertEqual(b["trend"], "Uptrend")
        self.assertGreater(b["gap_pct"], 0)
        self.assertGreater(b["ema_slope_5d_pct"], 0)
        self.assertEqual(b["crosses_30d"], 0)
        self.assertGreater(b["streak_days"], 30)

    def test_downtrend_and_extended_flag(self):
        prices = series(60, 100, 0) + [100 - 4 * i for i in range(1, 25)]  # sharp drop
        b = ema30.breakdown(prices)
        self.assertEqual(b["trend"], "Downtrend")
        self.assertTrue(b["extended"])
        self.assertLess(b["streak_days"], 0)

    def test_chop_counts_crosses(self):
        prices = [100 + (3 if i % 2 else -3) for i in range(90)]
        self.assertGreater(ema30.breakdown(prices)["crosses_30d"], 10)

    def test_select_movers_filters_liquidity_and_sides(self):
        mk = [{"id": c, "total_volume": v, "price_change_percentage_24h_in_currency": ch}
              for c, v, ch in [("a", 9e8, 12), ("b", 9e8, 5), ("c", 1e3, 99), ("d", 9e8, -7), ("e", 9e8, -15)]]
        ids = [m["id"] for m in ema30.select_movers(mk, top=1)]
        self.assertEqual(ids, ["a", "e"])  # c is illiquid
        self.assertEqual([m["id"] for m in ema30.select_movers(mk, top=2, direction="losers")], ["e", "d"])

    def test_cli_offline_input_markdown_and_json(self):
        data = {"up": {"symbol": "up", "prices": series(90), "change_24h": 8.0},
                "short": {"symbol": "sht", "prices": series(10)}}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(data, fh)
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(ema30.main(["--input", fh.name]), 0)
            out = buf.getvalue()
            self.assertIn("| UP |", out)
            self.assertIn("skipped short", out)
            buf = io.StringIO()
            with redirect_stdout(buf):
                ema30.main(["--input", fh.name, "--format", "json"])
            self.assertEqual(json.loads(buf.getvalue())["results"][0]["symbol"], "UP")
        finally:
            os.unlink(fh.name)


if __name__ == "__main__":
    unittest.main()
