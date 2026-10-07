#!/bin/bash
set -euo pipefail

# Only run in Claude Code cloud sessions.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# This repo is markdown agents plus bash/python scripts with no package
# manifests, so there is nothing to install. Verify the tools the linters and
# tests rely on are present so a missing one fails loudly at session start.
for tool in bash git python3 awk perl; do
  command -v "$tool" >/dev/null 2>&1 || { echo "session-start: missing required tool: $tool" >&2; exit 1; }
done

echo "session-start: ready (lint: ./scripts/lint-agents.sh, divisions: ./scripts/check-divisions.sh)"
