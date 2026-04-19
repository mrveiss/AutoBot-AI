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
| `team-implement.md` | Drives `/team-implement <issues>` — parallel multi-issue PR workflow with self-healing retry + Phase 0c verification mandate + Phase 6 amendment safety |

Other skills (e.g. `commit`, `pr`, `issue`) are not yet mirrored here. Add
them as they need updates worth reviewing.

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

- One skill = one responsibility. If `team-implement.md` grows past ~700
  lines, consider splitting (e.g., extract `pre-merge-validate` into its
  own skill).
- Use clearly-numbered phase headings (`## Phase 0`, `## Phase 1`, …) so
  cross-references stay stable.
- Reference issues in the body when adding rules tied to specific incidents
  (e.g. `(NEW — #5142)`) so future readers can find the rationale.
- Cite concrete failures in "rule of thumb" sections — abstract advice
  doesn't survive contact with real code.
