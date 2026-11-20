---
name: run-modelagency
description: Run, build, test, lint and smoke-test Modelagency, the markdown agent roster with bash install/convert tooling. Use to run or start the install script, validate a new agent or division, or confirm a change works end to end. There is no GUI or server.
---

# Run Modelagency

Modelagency is a roster of AI agent definitions (markdown with YAML frontmatter, one directory per division) plus bash tooling (`scripts/`) that lints, converts and installs them into tools such as Claude Code. It has no server, GUI or dependency manifest, and the "app" is `scripts/install.sh`. The driver is `smoke.sh` in this directory. Paths below are relative to the repo root.

## Prerequisites

`bash git python3 awk perl` (all present in this container; nothing to install).

## Run (agent path)

```bash
.claude/skills/run-modelagency/smoke.sh              # forecasting division
.claude/skills/run-modelagency/smoke.sh soccer-business
```

It takes about 10 seconds and runs four steps:
1. Lints the division's agents.
2. Checks that `divisions.json`, the directories and the scripts agree.
3. Installs the division into a temp dir with the real `install.sh`, then asserts that the number of files in that dir matches the number in the division.
4. Executes every ```` ```python ```` block inside the division's agent files, with numeric assertions for `forecasting`.

It ends with `SMOKE OK` and exits non-zero on any failure. The temp dir is deleted on exit.

Useful single commands:

```bash
./scripts/lint-agents.sh forecasting/*.md          # lint chosen files (no args = whole roster, ~45s)
./scripts/check-divisions.sh                       # division registry consistency
./scripts/install.sh --list teams                  # divisions and agent counts
./scripts/install.sh --dry-run --tool claude-code --division forecasting --no-interactive
./scripts/install.sh --tool claude-code --division forecasting --path /some/dir --no-interactive
```

## Add a division or agent

Create `<division>/<division>-<name>.md` with frontmatter `name`, `description`, `color` (use a `#RRGGBB` hex), `emoji`, `vibe`. For a new division also edit:
- `divisions.json`
- `AGENT_DIRS` in `scripts/convert.sh` (single line of names)
- `AGENT_DIRS` in `scripts/lint-agents.sh`
- both the `paths:` filter and the `':(glob)<dir>/**/*.md'` list in `.github/workflows/lint-agents.yml`

Then run `smoke.sh <division>`.

## Test

```bash
bash scripts/test-convert-frontmatter.sh       # ~30s, PASS line
bash scripts/test-convert-outputs.sh --drift=advisory   # ~3 min, run in background; prints "Results: N passed, M failed"
```

## Gotchas

- `check-divisions.sh` only counts git-tracked files. A new division directory fails with "missing division(s) present in divisions.json" until its files are `git add`ed (committed or staged is enough).
- Unquoted colons in frontmatter values break conversion: `FAIL source <file>: mapping values are not allowed here` (CI job "tools.json is the single source of truth" goes red). Wrap `description:` and `vibe:` values in double quotes whenever they contain `: `. This hit two existing soccer-business agents.
- `test-convert-outputs.sh` reports `FAIL manifest drift` whenever agents are added or edited. CI runs it with `--drift=advisory`, where it is only advisory, so don't edit `scripts/convert-outputs.sha256`. Locally always pass `--drift=advisory`, or the run exits non-zero.
- Don't `chmod +x scripts/*.sh` in hooks or setup. Git tracks the mode bit, and doing it showed up as mode changes on about 10 test scripts.
- `install.sh` without `--path` writes to `~/.claude/agents` for real. Use `--path <tmpdir>` for experiments.
- `install.sh --division` takes the directory name (`soccer-business`), while agent ids use the file-name slug (`forecast-market-maker`).

## Troubleshooting

- `Unknown division 'x'. Valid: ...` from install.sh means the name is not in `scripts/convert.sh` `AGENT_DIRS`.
- `ERROR <file>: not a file or does not exist` from lint means a bad path or glob.
- `smoke.sh` step 4 raising `NameError` means a python snippet in an agent is not self-contained; each block must define everything it uses.
