# Session Start and End Procedure

Checklist for starting and ending a session. Rules it points at are not restated here.

## Start

- [ ] If `.notes/INDEX.md` exists in the main checkout, read it and pick up every note whose latest line is not `closed`. No file, or no open line, means nothing is pending.
- [ ] If a legacy `.session/HANDOFF-*.md` exists in the main checkout, read it and carry its open items into `.notes/`. Leave the file for the human; agents never delete it.

## End

### Notes (`.notes/`, gitignored, never committed) — write BEFORE removing any worktree

- [ ] `.notes/` lives at the root of the MAIN checkout, never inside a worktree (removing the worktree would delete it, unrecoverably). Path: `$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")/.notes`.
- [ ] One file per open topic, named `yyyy.mm.dd-topic.md`.
- [ ] `.notes/INDEX.md` is append-only, so concurrent sessions never lose an entry: add each change as one short single-line `>>` append (`date | file | topic | issue | next step | open|closed`), with no `|` inside a field; never edit, rewrite or delete it. Per file, the last line in file order wins, not the `date` field.
- [ ] Write or update a note for every open topic.
- [ ] Delete notes whose work is complete, after moving anything still needed into code, `docs/` or an issue, then append a `closed` line for them.

### Issues

- [ ] Every parked, deferred, proposed-but-not-approved or hardware-blocked item gets an issue in the same turn, after a duplicate search ([Issue Filing](../../CLAUDE.md#issue-filing)).
- [ ] Decisions go as a comment on the matching issue.
- [ ] Close an issue only when the work is verifiably done ([`CLAUDE_CLOSURE.md`](CLAUDE_CLOSURE.md)).

### Memory

- [ ] Save new owner preferences and long-lived facts.

### Git

- [ ] No local test runs: CI and merge trains are the gate ([`CLAUDE_REVIEW.md`](CLAUDE_REVIEW.md#merge-trains)).
- [ ] Everything finished is committed and pushed; no local-only work ([`CLAUDE_GIT.md`](CLAUDE_GIT.md#parallel-work-worktree-isolation-critical)).
- [ ] Before removing each worktree, check it for a legacy `.session/HANDOFF-*.md` (gitignored, so removal will not refuse). If one exists, copy it to `.notes/legacy/<worktree>-<original file name>` and append its open items to `.notes/INDEX.md`. Only then remove the worktree.
- [ ] Remove every worktree you own once its branch is pushed, landed or not, never with `--force`, then `ledger release worktree <name>` ([claims](AGENT_COORDINATION.md#scope-grammar)). The pushed branch is the record and the takeover point; the worktree is disposable. Unlike a restart, an end-of-session release is final.
- [ ] A worktree that refuses removal is dirty: report it, do not force it.
- [ ] Report anything uncommitted.

### Deployed copies (optional)

- [ ] Bring an install to the latest `main` through the builtin updater only ([`CLAUDE_WORKFLOW.md`](CLAUDE_WORKFLOW.md#deployment-architecture)).
- [ ] If it cannot be updated now, file an issue.

### Report

- [ ] What was done and what is open, pointing at `.notes/INDEX.md` and the issues.
