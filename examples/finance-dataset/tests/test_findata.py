import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import findata as f  # noqa: E402

POSTS = {"data": {"children": [
    {"data": {"id": "a1", "title": "Should I max my Roth IRA or pay off my student loans?", "selftext": "I earn 60k, email me at jo@x.com or call 555-123-4567. See https://x.com/p?id=1",
              "score": 900, "num_comments": 120, "permalink": "/r/personalfinance/comments/a1/x/", "created_utc": 1.7e9, "author": "realname"}},
    {"data": {"id": "a2", "title": "NSFW post", "selftext": "x" * 60, "over_18": True, "author": "z"}},
    {"data": {"id": "a3", "title": "Pinned", "selftext": "y" * 60, "stickied": True, "author": "z"}},
    {"data": {"id": "a4", "title": "Guaranteed returns of 100x, DM me", "selftext": "send me btc and get rich quick",
              "score": 5, "num_comments": 1, "permalink": "/r/CryptoCurrency/comments/a4/x/", "created_utc": 1.7e9, "author": "scam"}},
    {"data": {"id": "a5", "title": "Gone", "selftext": "[removed]", "author": "z"}},
]}}
COMMENTS = [{}, {"data": {"children": [
    {"kind": "t1", "data": {"body": "Match first, then loans above 7%. u/someone said the same.", "score": 300, "author": "helper"}},
    {"kind": "t1", "data": {"body": "[deleted]", "score": 999, "author": "gone"}},
    {"kind": "t1", "data": {"body": "Low score reply here that is quite long.", "score": 2, "author": "other"}}]}}]


class ScrubTests(unittest.TestCase):
    def test_pii_removed_but_numbers_kept(self):
        out = f.scrub("mail jo@x.com, call (555) 123-4567, ssn 123-45-6789, card 4111 1111 1111 1111, u/bob @amy "
                      "see https://a.b/c. I earn $60,000 at 7.5% for 30 years")
        for leak in ("jo@x.com", "555) 123", "123-45-6789", "4111", "u/bob", "@amy", "https://"):
            self.assertNotIn(leak, out)
        self.assertIn("$60,000 at 7.5% for 30 years", out)

    def test_author_hash_not_reversible_and_stable_in_run(self):
        h = f.hash_author("realname")
        self.assertNotIn("realname", h)
        self.assertEqual(h, f.hash_author("realname"))
        self.assertIsNone(f.hash_author(None))


class ParseTests(unittest.TestCase):
    def test_reddit_skips_nsfw_pinned_removed_and_hashes_author(self):
        recs = f.parse_reddit_listing(POSTS, "personalfinance")
        self.assertEqual([r["id"] for r in recs], ["a1", "a4"])
        self.assertNotIn("realname", json.dumps(recs))

    def test_answers_sorted_and_deleted_dropped(self):
        ans = f.parse_reddit_answers(COMMENTS)
        self.assertEqual([a["score"] for a in ans], [300, 2])

    def test_about_and_github(self):
        self.assertEqual(f.parse_about("x", {"data": {"subscribers": 9, "accounts_active": 3}})["active"], 3)
        recs = f.parse_github({"items": [
            {"id": 1, "full_name": "a/b", "html_url": "u", "description": "d", "topics": ["finance"], "stargazers_count": 5,
             "forks_count": 1, "license": {"spdx_id": "MIT"}},
            {"id": 2, "full_name": "c/d", "html_url": "u", "description": None, "topics": [], "license": None}]})
        self.assertEqual([r["redistributable"] for r in recs], [True, False])

    def test_discord_skips_bots_and_short(self):
        exp = {"messages": [
            {"id": 1, "timestamp": "t", "content": "Is it smarter to put my bonus into an index fund or savings?", "author": {"id": "9", "name": "n"}},
            {"id": 2, "timestamp": "t", "content": "lol", "author": {"id": "9"}},
            {"id": 3, "timestamp": "t", "content": "bot message that is long enough to pass the filter ok", "author": {"id": "8", "isBot": True}}]}
        self.assertEqual(len(f.parse_discord_export(exp, "srv")), 1)


class CurateTests(unittest.TestCase):
    def setUp(self):
        self.recs = f.parse_reddit_listing(POSTS, "personalfinance")
        self.recs[0]["answers"] = f.parse_reddit_answers(COMMENTS)
        self.recs.append(dict(self.recs[0]))  # exact duplicate
        self.kept, self.dropped = f.curate(self.recs)

    def test_dedupe_scrub_tag(self):
        self.assertEqual(self.dropped["duplicate"], 1)
        q = self.kept[0]
        self.assertEqual((q["topic"], q["intent"]), ("retirement", "question"))
        self.assertNotIn("jo@x.com", json.dumps(self.kept))
        self.assertNotIn("u/someone", json.dumps(self.kept))

    def test_risky_advice_flagged(self):
        scam = next(r for r in self.kept if r["id"] == "a4")
        self.assertTrue(scam["needs_review"])
        self.assertFalse(self.kept[0]["needs_review"])

    def test_unlicensed_repo_text_redacted_flag(self):
        kept, _ = f.curate([{"source": "github", "id": "1", "community": "c/d", "kind": "repo", "title": "c/d finance budgeting tool",
                             "body": "A budgeting library for personal finance topics: finance", "score": 1, "num_comments": 0,
                             "answers": [], "redistributable": False}])
        self.assertTrue(kept[0]["body_redacted"])

    def test_report_lists_top_question(self):
        out = f.report(self.kept)
        self.assertIn("retirement", out)
        self.assertIn("Roth IRA", out)
        self.assertIn("flagged for risky advice", out)


class CliTests(unittest.TestCase):
    def test_discord_requires_consent(self):
        with self.assertRaises(SystemExit):
            f.main(["discord", "--export", "x.json", "--community", "c"])

    def test_curate_and_report_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            raw, out = os.path.join(d, "raw.jsonl"), os.path.join(d, "c.jsonl")
            f.write_jsonl(raw, f.parse_reddit_listing(POSTS, "personalfinance"), "w")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(f.main(["curate", raw, "--out", out]), 0)
            buf = io.StringIO()
            with redirect_stdout(buf):
                f.main(["report", out])
            self.assertIn("Customer query and research report", buf.getvalue())

    def test_reddit_requires_credentials(self):
        for k in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT"):
            os.environ.pop(k, None)
        with self.assertRaises(SystemExit):
            f.main(["scout"])


if __name__ == "__main__":
    unittest.main()
