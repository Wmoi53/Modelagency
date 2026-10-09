import io
import json
import unittest
from contextlib import redirect_stdout

from clubfin import analytics as an
from clubfin import cli, data as dt, server


def run(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli.main(list(argv))
    return code, buf.getvalue()


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.d = dt.generate()

    def test_deterministic(self):
        self.assertEqual(self.d, dt.generate())

    def test_cashflow_balances(self):
        cf = an.cashflow(self.d)
        self.assertAlmostEqual(cf["total_income"] - cf["total_expenses"] - cf["savings"],
                               cf["net"] - cf["savings"], places=2)
        self.assertGreater(cf["savings"], 0)
        self.assertEqual(len(an.monthly(self.d)), 12)

    def test_networth(self):
        nw = an.networth(self.d)
        self.assertEqual(nw["net_worth"], nw["assets"] + nw["liabilities"])

    def test_compound_matches_agent_example(self):
        self.assertAlmostEqual(an.compound(1, 0.10, 5), 1.61051)

    def test_flywheel_multiple(self):
        r = an.flywheel(100, 0.25, 0.40, 1, 5)
        self.assertAlmostEqual(r["growth_per_turn"], 0.10)
        self.assertAlmostEqual(r["multiple"], 1.61051)


class CliTests(unittest.TestCase):
    def test_commands_lists_every_subcommand(self):
        code, out = run("commands")
        self.assertEqual(code, 0)
        names = json.loads(run("commands", "--json")[1]).keys()
        self.assertIn("flywheel", names)
        for n in names:
            self.assertIn(f" {n} ", out)

    def test_every_command_has_help(self):
        for n in json.loads(run("commands", "--json")[1]):
            with self.assertRaises(SystemExit) as cm, redirect_stdout(io.StringIO()):
                cli.main([n, "--help"])
            self.assertEqual(cm.exception.code, 0)

    def test_read_only_commands_run(self):
        for argv in (["summary"], ["cashflow"], ["cashflow", "--view", "categories"],
                     ["spending"], ["networth"], ["accounts"], ["transactions", "--limit", "3"],
                     ["uncategorized"], ["categories"], ["flywheel"], ["compound", "100", "0.1", "5"]):
            self.assertEqual(run(*argv)[0], 0, argv)

    def test_write_commands_use_given_file(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "l.json")
            self.assertEqual(run("--data", path, "init")[0], 0)
            self.assertEqual(run("--data", path, "init")[0], 1)
            uid = dt.load(path)["transactions"][-1]["id"]
            self.assertEqual(run("--data", path, "add", "Ticket test", "500", "Matchday")[0], 0)
            self.assertEqual(dt.load(path)["transactions"][-1]["amount"], 500.0)
            self.assertEqual(run("--data", path, "categorize", str(uid), "Travel")[0], 0)

    def test_page_embeds_data(self):
        html = server.render(dt.generate())
        self.assertNotIn("__DATA__", html)
        self.assertIn("Riverside FC", html)


if __name__ == "__main__":
    unittest.main()
