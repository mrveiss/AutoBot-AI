# Session Start and End Procedure

Checklist for starting and ending a session. Rules it points at are not restated here.

## Start

- [ ] If `.notes/INDEX.md` exists, read it and pick up the listed topics. No file means nothing is pending.

## End

### Notes (`.notes/`, repo root, gitignored, never committed)

- [ ] One file per open topic, named `yyyy.mm.dd-topic.md`.
- [ ] `.notes/INDEX.md` lists every open note: file, topic, issue, next step.
- [ ] Write or update a note for every open topic.
- [ ] Delete notes whose work is complete, after moving anything still needed into code, `docs/` or an issue.
- [ ] When the last note goes, delete `INDEX.md`. An empty `.notes/` means nothing is pending.

### Issues

- [ ] Every parked, deferred, proposed-but-not-approved or hardware-blocked item gets an issue in the same turn, after a duplicate search ([Issue Filing](../../CLAUDE.md#issue-filing)).
- [ ] Decisions go as a comment on the matching issue.
- [ ] Close an issue only when the work is verifiably done ([`CLAUDE_CLOSURE.md`](CLAUDE_CLOSURE.md)).

### Memory

- [ ] Save new owner preferences and long-lived facts.

### Git

- [ ] No local test runs: CI and merge trains are the gate ([`CLAUDE_REVIEW.md`](CLAUDE_REVIEW.md#merge-trains)).
- [ ] Everything finished is committed and pushed; no local-only work ([`CLAUDE_GIT.md`](CLAUDE_GIT.md#parallel-work-worktree-isolation-critical)).
- [ ] Remove every worktree you own without `--force`, then `~/.claude/scripts/ledger release worktree <name>` ([`AGENT_COORDINATION.md`](AGENT_COORDINATION.md#restart-and-resume)).
- [ ] A worktree that refuses removal is dirty: report it, do not force it.
- [ ] Report anything uncommitted.

### Deployed copies (optional)

- [ ] Bring an install to the latest `main` through the builtin updater only ([`CLAUDE_WORKFLOW.md`](CLAUDE_WORKFLOW.md#deployment-architecture)).
- [ ] If it cannot be updated now, file an issue.

### Report

- [ ] What was done and what is open, pointing at `.notes/INDEX.md` and the issues.
