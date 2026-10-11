# Finance dataset collector

Five agents in `finance/` and `findata.py` (Python 3.9+ stdlib) build a finance Q&A and research dataset from Reddit, GitHub and Discord, for **answering customer queries and market research** (retrieval, FAQ drafting, insight), **not model training**.

Pipeline: Source Scout → Forum Collector → Dataset Curator → Advice Quality Reviewer → Customer Query Analyst.

```bash
export REDDIT_CLIENT_ID=... REDDIT_CLIENT_SECRET=... REDDIT_USER_AGENT="finance-research/0.1 by your_reddit_name"
python findata.py scout                         # rank big, active subreddits (subscribers, active now)
python findata.py reddit --top 5 --out raw.jsonl   # top posts + best answers to questions
python findata.py github --out raw.jsonl        # finance repo metadata + licences (GITHUB_TOKEN optional)
python findata.py discord --export chat.json --community myserver --consent-confirmed --out raw.jsonl
python findata.py curate raw.jsonl --out curated.jsonl
python findata.py report curated.jsonl          # topics, share, most-asked questions
python -m unittest discover -s tests
```

## Rules built in

- **Official APIs only.** Reddit OAuth (about 1 request per second), GitHub REST. No scraping, no user tokens.
- **Reddit:** internal support and research use only. Don't republish posts or train models on them; check Reddit's current terms for your use.
- **Discord:** only servers you administer, with member consent. `--consent-confirmed` is required; bot messages and short messages are skipped.
- **GitHub:** each repo keeps its SPDX licence; repos without a permissive licence are marked `body_redacted` and kept as metadata only.
- **Privacy:** authors are hashed at collection (random salt per run, or `FINDATA_SALT`); emails, phones, ids, card numbers, URLs and usernames are scrubbed. NSFW, pinned, removed and deleted posts are skipped.
- **Not advice:** records with risky patterns (guaranteed returns, pump, DM me, skip tax) get `needs_review`. Forum answers are unverified, and the Reviewer must clear them before they reach a customer.

Output record fields: `source, id, community, kind, url, created, author_hash, title, body, score, num_comments, answers, topic, intent, risk_flags, needs_review, quality`.
