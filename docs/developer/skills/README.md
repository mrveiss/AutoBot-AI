# Claude Code Skills

Claude Code skills are workflow definitions Claude reads before responding — small markdown
files that say "when X happens, do Y". AutoBot's skills install from two plugin marketplaces
(below); this directory holds the docs and history, not the skill files themselves.


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

## No skills live in this repo anymore

Every Claude dev skill now installs from one of the two marketplaces above. This directory is kept
for its history and the notes below; it no longer holds a skill file. `tools/install_skills.sh`
is dormant (it symlinks whatever `*.md` skills are here — currently none).

### Why these were version-controlled (history)

Claude reads skills from `~/.claude/skills/<name>/SKILL.md` on each developer's
machine. Without this directory:

- Skill changes are user-local — invisible to the rest of the team
- No PR review of changes to workflow rules
- No history of why a rule exists
- A clean home directory loses every refinement

#5094 was the discovery that surfaced this. See that issue for the full
incident.

## Where the skills are

`batch-implement` moved to the AutoBot marketplace with the other AutoBot skills (see **Installing
the skill sets** above). `autobot-llc` is not a Claude skill at all — it is an AutoBot runtime
module loaded by `autobot-backend/llc/`, and stays in the codebase.

The `team-implement` skill was consolidated into `batch-implement` in #5454 —
the two skills' scopes overlapped (both did parallel-issue implementation),
and the methodology rules (Phase 0c, Phase 0d) were silently living in
the wrong file. Consolidation made `batch-implement` the single source of truth for the end-to-end workflow;
it now ships from the marketplace.

## Setup (one-time per developer)

Install the two marketplaces (above) — that is the whole skill set. `tools/install_skills.sh`
remains only to symlink any future in-repo skill and currently does nothing:

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

- One skill = one responsibility. If a skill's `SKILL.md` grows past ~700
  lines, consider splitting it.
- Use clearly-numbered phase headings (`## Phase 0`, `## Phase 1`, …) so
  cross-references stay stable.
- Reference issues in the body when adding rules tied to specific incidents
  (e.g. `(NEW — #5142)`) so future readers can find the rationale.
- Cite concrete failures in "rule of thumb" sections — abstract advice
  doesn't survive contact with real code.
