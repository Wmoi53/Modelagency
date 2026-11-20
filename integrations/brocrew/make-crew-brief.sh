#!/usr/bin/env bash
# Build a BroCrew "crew brief" for one division: a single markdown message you
# paste into a BroCrew "New conversation". It asks the root agent to create one
# agent per file in the division, using that file's body as its standing rules.
#
# BroCrew has no agent-file import (agents are made at runtime with the
# create_agent tool, rules capped at 16,000 characters each), so this emits text.
#
# Usage: integrations/brocrew/make-crew-brief.sh <division> [output-file]
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

DIV="${1:-}"
OUT="${2:-/dev/stdout}"
LIMIT=16000
[[ -n "$DIV" && -d "$DIV" ]] || { echo "usage: $0 <division> [output-file]  (a top-level agent directory, e.g. forecasting)" >&2; exit 2; }

shopt -s nullglob
files=("$DIV"/*.md)
[[ ${#files[@]} -gt 0 ]] || { echo "no agent files in $DIV" >&2; exit 2; }

fm() { awk -v k="$2" 'NR==1{next} /^---$/{exit} index($0,k":")==1{sub(/^[^:]*: */,""); gsub(/^"|"$/,""); print; exit}' "$1"; }
body() { awk 'NR==1&&/^---$/{f=1;next} f&&/^---$/{f=0;next} !f' "$1"; }

{
  echo "# Crew brief: ${DIV}"
  echo
  echo "Create a crew of ${#files[@]} agents. For each section below, call create_agent with the section's"
  echo "title as the agent's name and the text inside its rules code fence as its standing rules, exactly as"
  echo "written. Then tell me who is on the crew and what each one is for. Do not start any work yet."
  for f in "${files[@]}"; do
    n=$(body "$f" | wc -c)
    if (( n > LIMIT )); then echo "error: $f body is $n chars, over BroCrew's $LIMIT limit" >&2; exit 1; fi
    echo
    echo "## $(fm "$f" name)"
    echo "Purpose: $(fm "$f" description)"
    echo
    echo '````rules'
    body "$f"
    echo '````'
  done
} > "$OUT"
