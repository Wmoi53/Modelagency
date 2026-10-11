#!/usr/bin/env python3
"""Collect a finance Q&A / research dataset from Reddit, GitHub and Discord (stdlib only).

Built for two uses: answering customer finance questions (retrieval/FAQ) and
market research. Not for model training: Reddit restricts that.

    python findata.py scout                       # rank big, active finance subreddits
    python findata.py reddit --top 5 --out raw.jsonl
    python findata.py github --out raw.jsonl
    python findata.py discord --export chat.json --community myserver --consent-confirmed --out raw.jsonl
    python findata.py curate raw.jsonl --out curated.jsonl
    python findata.py report curated.jsonl

Reddit needs REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT (official API only).
GitHub optionally uses GITHUB_TOKEN. Discord reads an export from a server you administer.
Authors are hashed at collection time; raw usernames are never written.
"""
import argparse
import base64
import collections
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_SUBS = ["personalfinance", "investing", "stocks", "financialindependence", "Bogleheads",
                "CryptoCurrency", "wallstreetbets", "FinancialPlanning", "CreditCards", "tax",
                "povertyfinance", "realestateinvesting"]
GITHUB_TOPICS = ["personal-finance", "finance", "fintech", "budgeting", "algorithmic-trading", "quant"]
PERMISSIVE = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "Unlicense", "CC0-1.0"}
MIN_CHARS = 40

TOPICS = {
    "retirement": r"\b(401k|403b|ira|roth|retire\w*|pension|social security)\b",
    "taxes": r"\b(tax\w*|irs|deduction|capital gains|w-?2|1099)\b",
    "budgeting": r"\b(budget\w*|spend\w*|expenses?|frugal|paycheck)\b",
    "debt": r"\b(debt|loan\w*|mortgage|student loans?|payoff|interest rate)\b",
    "credit": r"\b(credit (?:score|card|report)|fico|chargeback)\b",
    "investing": r"\b(etf|index fund|stocks?|bonds?|portfolio|dividend\w*|vti|voo|s&p)\b",
    "crypto": r"\b(crypto\w*|bitcoin|btc|ethereum|eth|defi|altcoins?)\b",
    "real-estate": r"\b(real estate|rental|landlord|house|down payment|reit)\b",
    "savings": r"\b(savings?|emergency fund|hysa|cd rates?)\b",
    "insurance": r"\b(insurance|premium|deductible)\b",
}
RISK = [r"guarantee[sd]?\s+(?:returns?|profits?|gains?)", r"can'?t lose", r"risk[- ]free",
        r"\b(?:100|1000|10000)x\b", r"\bpump\b", r"\bdm me\b", r"send (?:me )?(?:btc|eth|money|crypto)",
        r"get rich quick", r"all[- ]in on", r"insider (?:tip|info)", r"free money",
        r"(?:don'?t|do not) (?:have to )?(?:pay|report) (?:any )?tax"]
QUESTION_START = ("how", "what", "should", "can", "is", "are", "does", "do", "why", "which", "where",
                  "when", "will", "would", "am i", "any")


# ---------- text hygiene ----------
def scrub(text):
    """Remove personal identifiers; keep the finance content."""
    text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "[email]", text)
    text = re.sub(r"https?://\S+|www\.\S+", "[url]", text)
    text = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[id]", text)
    text = re.sub(r"\b(?:\d[ -]?){13,16}\b", "[number]", text)
    text = re.sub(r"(?<!\w)(?:\+?\d{1,3}[\s.-])?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d)", "[phone]", text)
    text = re.sub(r"(?<!\w)/?u/[\w-]+", "[user]", text)
    text = re.sub(r"(?<![\w.])@[\w.]+", "[user]", text)
    return text.strip()


_SALT = os.environ.get("FINDATA_SALT") or os.urandom(8).hex()


def hash_author(name):
    return hashlib.sha256(f"{_SALT}:{name}".encode()).hexdigest()[:12] if name else None


def classify_topic(text):
    hits = [t for t, rx in TOPICS.items() if re.search(rx, text, re.I)]
    return hits[0] if hits else "general"


def is_question(title):
    t = title.strip().lower()
    return "?" in t or t.startswith(QUESTION_START)


def risk_flags(text):
    return sorted({rx for rx in RISK if re.search(rx, text, re.I)})


# ---------- HTTP ----------
def http(url, headers=None, data=None, retries=4):
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as err:
            if err.code in (429, 503) and attempt < retries - 1:
                time.sleep(int(err.headers.get("Retry-After", 10 * (attempt + 1))))
                continue
            raise


def reddit_token():
    cid, secret = os.environ.get("REDDIT_CLIENT_ID"), os.environ.get("REDDIT_CLIENT_SECRET")
    if not (cid and secret and os.environ.get("REDDIT_USER_AGENT")):
        raise SystemExit("set REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET and REDDIT_USER_AGENT (official API only)")
    auth = base64.b64encode(f"{cid}:{secret}".encode()).decode()
    resp = http("https://www.reddit.com/api/v1/access_token",
                {"Authorization": f"Basic {auth}", "User-Agent": os.environ["REDDIT_USER_AGENT"]},
                urllib.parse.urlencode({"grant_type": "client_credentials"}).encode())
    return resp["access_token"]


def reddit_get(token, path, **params):
    qs = urllib.parse.urlencode(params)
    time.sleep(1.0)  # stay well under the 100 requests/minute limit
    return http(f"https://oauth.reddit.com{path}?{qs}",
                {"Authorization": f"bearer {token}", "User-Agent": os.environ["REDDIT_USER_AGENT"]})


# ---------- parsers (pure, tested on fixtures) ----------
def parse_about(sub, payload):
    d = payload["data"]
    return {"subreddit": sub, "subscribers": d.get("subscribers") or 0,
            "active": d.get("accounts_active") or d.get("active_user_count") or 0}


def parse_reddit_listing(listing, community):
    out = []
    for child in listing["data"]["children"]:
        d = child["data"]
        if d.get("over_18") or d.get("stickied") or d.get("removed_by_category"):
            continue
        body = d.get("selftext") or ""
        if body in ("[removed]", "[deleted]"):
            continue
        out.append({"source": "reddit", "id": d["id"], "community": community, "kind": "post",
                    "url": "https://www.reddit.com" + d.get("permalink", ""),
                    "created": int(d.get("created_utc", 0)), "author_hash": hash_author(d.get("author")),
                    "title": d.get("title", ""), "body": body, "score": d.get("score", 0),
                    "num_comments": d.get("num_comments", 0), "answers": []})
    return out


def parse_reddit_answers(comments_payload, limit=3):
    kids = comments_payload[1]["data"]["children"]
    ans = [{"text": k["data"]["body"], "score": k["data"].get("score", 0),
            "author_hash": hash_author(k["data"].get("author"))}
           for k in kids if k.get("kind") == "t1" and k["data"].get("body") not in (None, "[removed]", "[deleted]")]
    return sorted(ans, key=lambda a: -a["score"])[:limit]


def parse_github(payload):
    out = []
    for r in payload.get("items", []):
        spdx = (r.get("license") or {}).get("spdx_id")
        out.append({"source": "github", "id": str(r["id"]), "community": r["full_name"], "kind": "repo",
                    "url": r["html_url"], "created": r.get("created_at", ""), "author_hash": None,
                    "title": r["full_name"], "body": (r.get("description") or "") + " topics: " + ", ".join(r.get("topics", [])),
                    "score": r.get("stargazers_count", 0), "num_comments": r.get("forks_count", 0),
                    "license": spdx, "redistributable": spdx in PERMISSIVE, "answers": []})
    return out


def parse_discord_export(export, community):
    out = []
    for m in export.get("messages", []):
        a = m.get("author", {})
        text = (m.get("content") or "").strip()
        if a.get("isBot") or len(text) < MIN_CHARS:
            continue
        out.append({"source": "discord", "id": str(m["id"]), "community": community, "kind": "message",
                    "url": None, "created": m.get("timestamp", ""), "author_hash": hash_author(a.get("id") or a.get("name")),
                    "title": text[:80], "body": text, "score": len(m.get("reactions", [])),
                    "num_comments": 0, "answers": []})
    return out


# ---------- curate / report ----------
def curate(records):
    seen, kept, dropped = set(), [], collections.Counter()
    for r in records:
        r = dict(r)
        r["title"], r["body"] = scrub(r["title"]), scrub(r["body"])
        r["answers"] = [dict(a, text=scrub(a["text"])) for a in r.get("answers", [])]
        text = f"{r['title']} {r['body']}".strip()
        if len(text) < MIN_CHARS:
            dropped["too_short"] += 1
            continue
        if r.get("source") == "github" and not r.get("redistributable"):
            r["body_redacted"] = True  # keep metadata for research, never redistribute text
        key = hashlib.sha1(re.sub(r"\W+", " ", text.lower()).encode()).hexdigest()
        if key in seen:
            dropped["duplicate"] += 1
            continue
        seen.add(key)
        alltext = text + " " + " ".join(a["text"] for a in r["answers"])
        r["topic"] = classify_topic(alltext)
        r["intent"] = "question" if r["kind"] != "repo" and is_question(r["title"]) else "discussion"
        r["risk_flags"] = risk_flags(alltext)
        r["needs_review"] = bool(r["risk_flags"])
        r["quality"] = round(min(1.0, (r.get("score", 0) + 2 * r.get("num_comments", 0)) / 200), 2)
        kept.append(r)
    return kept, dropped


def report(records, top=3):
    topics, intents = collections.Counter(), collections.Counter()
    by_topic = collections.defaultdict(list)
    for r in records:
        topics[r["topic"]] += 1
        intents[r["intent"]] += 1
        if r["intent"] == "question":
            by_topic[r["topic"]].append(r)
    flagged = sum(1 for r in records if r["needs_review"])
    lines = ["# Customer query and research report", "",
             f"{len(records)} records; {intents['question']} questions; "
             f"{flagged} flagged for risky advice ({flagged / max(len(records), 1):.0%}).", "",
             "| Topic | Records | Share |", "|---|---:|---:|"]
    for t, n in topics.most_common():
        lines.append(f"| {t} | {n} | {n / len(records):.0%} |")
    lines += ["", "## Most-asked questions by topic (by engagement)"]
    for t, _ in topics.most_common():
        qs = sorted(by_topic[t], key=lambda r: -(r.get("score", 0) + 2 * r.get("num_comments", 0)))[:top]
        if qs:
            lines += ["", f"**{t}**"] + [f"- {q['title']} ({q['community']}, {q['score']} pts, {q['num_comments']} comments)" for q in qs]
    lines += ["", "_Research only. Forum answers are not verified financial advice._"]
    return "\n".join(lines)


# ---------- commands ----------
def write_jsonl(path, records, mode="a"):
    with open(path, mode, encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def read_jsonl(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def cmd_scout(a):
    token = reddit_token()
    rows = [parse_about(s, reddit_get(token, f"/r/{s}/about")) for s in a.subs.split(",")]
    rows.sort(key=lambda r: (-r["active"], -r["subscribers"]))
    print(f"{'subreddit':<24}{'subscribers':>14}{'active now':>12}")
    for r in rows:
        print(f"{r['subreddit']:<24}{r['subscribers']:>14,}{r['active']:>12,}")


def cmd_reddit(a):
    token = reddit_token()
    subs = [s for s in a.subs.split(",")] if a.subs else DEFAULT_SUBS[:a.top]
    total = 0
    for s in subs:
        recs = parse_reddit_listing(reddit_get(token, f"/r/{s}/top", t=a.period, limit=a.limit), s)
        for r in recs:
            if is_question(r["title"]) and r["num_comments"] and a.answers:
                r["answers"] = parse_reddit_answers(reddit_get(token, f"/comments/{r['id']}", limit=20, depth=1, sort="top"), a.answers)
        write_jsonl(a.out, recs)
        total += len(recs)
        print(f"r/{s}: {len(recs)} posts", file=sys.stderr)
    print(f"wrote {total} records to {a.out}")


def cmd_github(a):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "findata/0.1"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    total = 0
    for topic in a.topics.split(","):
        q = urllib.parse.urlencode({"q": f"topic:{topic} stars:>={a.min_stars}", "sort": "stars", "per_page": a.limit})
        recs = parse_github(http(f"https://api.github.com/search/repositories?{q}", headers))
        write_jsonl(a.out, recs)
        total += len(recs)
        time.sleep(2)
    print(f"wrote {total} records to {a.out}")


def cmd_discord(a):
    if not a.consent_confirmed:
        raise SystemExit("refusing: pass --consent-confirmed only for a server you administer, "
                         "where members know messages are used for research")
    with open(a.export, encoding="utf-8") as fh:
        recs = parse_discord_export(json.load(fh), a.community)
    write_jsonl(a.out, recs)
    print(f"wrote {len(recs)} records to {a.out}")


def cmd_curate(a):
    kept, dropped = curate(read_jsonl(a.input))
    write_jsonl(a.out, kept, "w")
    print(f"kept {len(kept)}; dropped {dict(dropped)}; flagged {sum(r['needs_review'] for r in kept)}")


def cmd_report(a):
    print(report(read_jsonl(a.input), a.top))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    s = p.add_subparsers(dest="cmd", required=True)
    x = s.add_parser("scout", help="rank big, active finance subreddits")
    x.add_argument("--subs", default=",".join(DEFAULT_SUBS))
    x.set_defaults(fn=cmd_scout)
    x = s.add_parser("reddit", help="collect top posts and best answers")
    x.add_argument("--subs", help="comma list (default: built-in big subs)")
    x.add_argument("--top", type=int, default=5, help="how many default subs")
    x.add_argument("--period", default="month", choices=["day", "week", "month", "year"])
    x.add_argument("--limit", type=int, default=100)
    x.add_argument("--answers", type=int, default=3, help="top answers per question (0 = skip)")
    x.add_argument("--out", default="raw.jsonl")
    x.set_defaults(fn=cmd_reddit)
    x = s.add_parser("github", help="collect finance repo metadata and licences")
    x.add_argument("--topics", default=",".join(GITHUB_TOPICS))
    x.add_argument("--min-stars", type=int, default=100, dest="min_stars")
    x.add_argument("--limit", type=int, default=30)
    x.add_argument("--out", default="raw.jsonl")
    x.set_defaults(fn=cmd_github)
    x = s.add_parser("discord", help="read an export from a server you administer")
    x.add_argument("--export", required=True)
    x.add_argument("--community", required=True)
    x.add_argument("--consent-confirmed", action="store_true", dest="consent_confirmed")
    x.add_argument("--out", default="raw.jsonl")
    x.set_defaults(fn=cmd_discord)
    x = s.add_parser("curate", help="scrub, dedupe, tag topic/intent, flag risky advice")
    x.add_argument("input")
    x.add_argument("--out", default="curated.jsonl")
    x.set_defaults(fn=cmd_curate)
    x = s.add_parser("report", help="topics and most-asked customer questions")
    x.add_argument("input")
    x.add_argument("--top", type=int, default=3)
    x.set_defaults(fn=cmd_report)
    a = p.parse_args(argv)
    try:
        a.fn(a)
    except (urllib.error.URLError, OSError) as err:
        print(f"network error: {err}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
