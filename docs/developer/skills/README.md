# Claude Code Skills (canonical sources)

This directory holds the canonical, version-controlled source for Claude Code
skills used by this project. Skills are workflow definitions Claude reads
before responding — small markdown files that say "when X happens, do Y".


## Installing the skill sets

Most AutoBot skills ship as two Claude Code **plugin marketplaces**, so every developer gets the
same setup with a few commands — no manual copying, and each set updates independently.

**General, reuse-anywhere skills** — [Claude-Dev-Skills](https://github.com/mrveiss/Claude-Dev-Skills)
(`process`, `commit`, `canonical-coding`, `review-lenses`, `gap-audit`, `web-audit`, `ui-design`,
`memory-cleanup`):

```
/plugin marketplace add mrveiss/Claude-Dev-Skills
/plugin install claude-dev-skills@claude-dev-skills
```

**AutoBot-specific skills** — [AutoBot-AI-Claude-dev-skills](https://github.com/mrveiss/AutoBot-AI-Claude-dev-skills)
(`implement`, `pr`, `pre-merge-validate`, `github-cli`, `debug-autobot`, `api-wiring-audit`,
`dead-code-audit`, `review-fleet`, `review`, `session-lifecycle`, `drain`):

```
/plugin marketplace add mrveiss/AutoBot-AI-Claude-dev-skills
/plugin install autobot-dev-skills@autobot-ai-claude-dev-skills
```

The split is deliberate: a general skill improves for every project at once, while an
AutoBot-specific one stays where its conventions (`Dev_new_gui`, `autobot_shared`, the deploy path,
the PR-body headings) apply. `debug-autobot` reads service hosts from `$REDIS_HOST` / `$NPU_HOST` /
`$BROWSER_HOST` / `$AISTACK_HOST` — export them from your deployment before use.

## Skills that still live in this repo

A few skills are canonically version-controlled here rather than in a marketplace, because they are
tightly bound to code in this tree:

### Why a skill stays in-repo

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

The general and AutoBot-specific skills now live in the two marketplaces above. What remains
in this directory is `batch-implement.md` (below); the `autobot-llc` skill lives in
`autobot-backend/llc/skills/` beside the LLC code it drives.

`team-implement.md` was consolidated into `batch-implement.md` in #5454 —
the two skills' scopes overlapped (both did parallel-issue implementation),
and the methodology rules (Phase 0c, Phase 0d) were silently living in
the wrong file. Consolidation makes `batch-implement` the single source
of truth for the end-to-end workflow.

## Setup (one-time per developer)

Install the two marketplaces (above) for most skills. For the in-repo skills in this directory:

```bash
tools/install_skills.sh
```

That script symlinks each `*.md` here into `~/.claude/skills/<name>/SKILL.md`, so Claude reads the
in-repo version directly. Updates to the file are picked up on Claude's next read — no resync
needed.

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
