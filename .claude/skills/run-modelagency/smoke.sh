#!/usr/bin/env bash
# Drives Modelagency end to end: lint, division consistency, a real install of
# one division into a temp dir, and execution of every ```python block embedded
# in that division's agents (with numeric assertions).
# Usage (from repo root): .claude/skills/run-modelagency/smoke.sh [division]   (default: forecasting)
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
DIV="${1:-forecasting}"
OUT="$(mktemp -d)"
trap 'rm -rf "$OUT"' EXIT

echo "== 1/4 lint $DIV"
./scripts/lint-agents.sh "$DIV"/*.md | tail -2

echo "== 2/4 division consistency (needs the division's files to be git-tracked)"
./scripts/check-divisions.sh | tail -1

echo "== 3/4 install $DIV -> $OUT"
./scripts/install.sh --tool claude-code --division "$DIV" --path "$OUT" --no-interactive | grep -E '^\[(OK|FAIL|ERR)'
want=$(ls "$DIV"/*.md | wc -l); got=$(ls "$OUT"/*.md | wc -l)
[ "$want" = "$got" ] || { echo "FAIL: expected $want installed agents, got $got"; exit 1; }
echo "installed $got/$want agents"

echo "== 4/4 execute embedded python snippets"
python3 -I - "$DIV" <<'PY'
import glob, math, re, sys
ns_all = {}
for f in sorted(glob.glob(f"{sys.argv[1]}/*.md")):
    for b in re.findall(r"```python\n(.*?)```", open(f).read(), re.S):
        exec(b, ns_all)
        print("ran snippet from", f)
if sys.argv[1] == "forecasting":
    n = ns_all
    assert abs(n["beta_prior"](14, 40) - 15/42) < 1e-9
    h, d, a = n["match_probs"](1.6, 1.1); assert abs(h + d + a - 1) < 1e-3 and h > a
    q = [10.0, 0.0]; ps = [n["lmsr_price"](q, 50.0, i) for i in range(2)]; assert abs(sum(ps) - 1) < 1e-9
    assert abs(n["lmsr_cost"]([0, 0], 50.0) - 50 * math.log(2)) < 1e-9   # maker worst-case-loss anchor
    assert abs(sum(n["decimal_odds_to_probs"]([2.1, 3.4, 3.6])) - 1) < 1e-9
    assert abs(n["aggregate"]([0.6, 0.6], [1, 1]) - 0.6) < 1e-9
    assert n["kelly_fraction"](0.5, 2.0) == 0.0
    assert n["brier"](0.8, 1) < n["brier"](0.5, 1)
    print("numeric assertions passed")
PY
echo "SMOKE OK"
