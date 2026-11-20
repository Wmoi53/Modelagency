# BroCrew

[BroCrew](https://github.com/brocrew/brocrew) is an open-source desktop app (macOS, Windows beta) that runs a team of
Claude and Codex agents on your computer. You give one agent a project, it hands pieces to other agents, and you follow
the work in one tree and answer requests in one queue.

BroCrew has no agent-file import. Agents are created while it runs, through its `create_agent` tool, with their
standing rules supplied as text (limit: 16,000 characters per agent; every agent here is under 5,000). So this
integration generates a paste-in "crew brief" rather than converted files.

```bash
integrations/brocrew/make-crew-brief.sh forecasting crew-brief.md      # or soccer-business, finance, ...
```

Then in BroCrew: **New conversation**, paste the brief, send. The root agent creates one agent per file, each with that
file's body as its rules, and reports back who is on the crew. Give the crew its first project in a follow-up message.

Not verified: this was written from BroCrew's source and docs. The desktop app was not run, so the paste-in flow has not
been tried end to end. The generator itself is tested (output has one `rules` block per agent; unknown divisions and
over-limit bodies fail).
