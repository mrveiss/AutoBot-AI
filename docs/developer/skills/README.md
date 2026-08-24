# Claude Code Skills (canonical sources)

This directory holds the canonical, version-controlled source for Claude Code
skills used by this project. Skills are workflow definitions Claude reads
before responding — small markdown files that say "when X happens, do Y".

## Why these live in the repo

Claude reads skills from `~/.claude/skills/<name>/SKILL.md` on each developer's
machine. Without this directory:

- Skill changes are user-local — invisible to the rest of the team
- No PR review of changes to workflow rules
- No history of why a rule exists
- A clean home directory loses every refinement

#5094 was the discovery that surfaced this. See that issue for the full
incident.

## Files

| File | Role |
|---|---|
| `batch-implement.md` | Drives `/batch-implement <issues>` — full implement→review→merge→close→discover loop with self-healing retry, Phase 0c verification mandate, and Phase 0d behavioral grep for extraction PRs |
| `implement.md` | Drives `/implement <issue>` — umbrella gate, worktree, design, code, verify, PR, CI, three-gate closure |
| `pr.md` | PR creation with pre-flight branch checks, the four required body headings, targeting `Dev_new_gui` |
| `pre-merge-validate.md` | Pre-merge validation — syntax, imports, call-site impact, tests, types, linting |
| `github-cli.md` | `gh` CLI usage for every GitHub operation — issues, PRs, reviews, merges, local workarounds |
| `debug-autobot.md` | Full-stack debugging — parallel per-layer investigators then a synthesis protocol |
| `api-wiring-audit.md` | Frontend/backend API contract wiring audit — unmounted routers, dead buttons, 404s, drift |
| `dead-code-audit.md` | Unwired-code audit — unregistered routers, uninvoked hooks, orphaned components → wire-in issues |
| `review-fleet.md` | 10-angle parallel PR review fleet — finders + adversarial verifiers, one deduped comment |
| `review.md` | PR review cycle — CI diagnosis, three-angle finder pass, lint-only auto-fix, merge decision |
| `session-lifecycle.md` | Start/end-of-session protocol — worktree setup, stale-branch cleanup, rebase, handoff |
| `drain.md` | Selects backlog issues needing no decision; delegates execution to `batch-implement` |

The 11 AutoBot-specific skills above were mirrored here in #14994. General-purpose
skills were extracted to a separate public collection instead (`process`, `commit`,
`review-lenses`, `gap-audit`, `web-audit`, `ui-design`, `memory-cleanup`,
`canonical-coding`).

`team-implement.md` was consolidated into `batch-implement.md` in #5454 —
the two skills' scopes overlapped (both did parallel-issue implementation),
and the methodology rules (Phase 0c, Phase 0d) were silently living in
the wrong file. Consolidation makes `batch-implement` the single source
of truth for the end-to-end workflow.

## Setup (one-time per developer)

```bash
tools/install_skills.sh
```

That script symlinks each `*.md` here into `~/.claude/skills/<name>/SKILL.md`,
so Claude reads the in-repo version directly. Updates to the file in this
directory are picked up on Claude's next read — no resync needed.

## Updating a skill

1. Edit the file here in the repo
2. Open a PR — workflow rule changes get the same review as code
3. Other developers run `tools/install_skills.sh` once after pulling to
   ensure their `~/.claude/skills/` symlinks point at the up-to-date file
   (only needed if a new skill is added; updates to existing skills flow
   through the symlink)

## Skill-authoring guidelines

- One skill = one responsibility. If `batch-implement.md` grows past ~700
  lines, consider splitting (e.g., extract `pre-merge-validate` into its
  own skill).
- Use clearly-numbered phase headings (`## Phase 0`, `## Phase 1`, …) so
  cross-references stay stable.
- Reference issues in the body when adding rules tied to specific incidents
  (e.g. `(NEW — #5142)`) so future readers can find the rationale.
- Cite concrete failures in "rule of thumb" sections — abstract advice
  doesn't survive contact with real code.
