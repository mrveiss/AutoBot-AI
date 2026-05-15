# Memory Hygiene Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent context rot in MEMORY.md by adding a cleanup skill, a session-start warning hook, and a durable policy in CLAUDE.md.

**Architecture:** Three layers — (1) a `/memory-cleanup` skill that walks through the cleanup ritual, (2) a `SessionStart` hook that warns when MEMORY.md exceeds the line limit, (3) a `## Memory Hygiene` section in CLAUDE.md making this a mandatory workflow step. MEMORY.md also gets a small self-referential rules header.

**Tech Stack:** Claude Code skills (SKILL.md), settings.json hooks (bash), Markdown.

---

### Task 1: Create the `/memory-cleanup` skill

**Files:**
- Create: `~/.claude/skills/memory-cleanup/SKILL.md`

**Step 1: Create the skill directory and file**

```bash
mkdir -p ~/.claude/skills/memory-cleanup
```

Content for `~/.claude/skills/memory-cleanup/SKILL.md`:

```markdown
---
name: memory-cleanup
description: End-of-session memory hygiene ritual. Run this at the end of every session to prevent context rot in MEMORY.md.
---

# /memory-cleanup — Session-End Memory Hygiene

Run this at the end of every work session. Takes ~2 minutes.

## Step 1: Check size

```bash
wc -l ~/.claude/projects/-home-kali-Desktop-AutoBot/memory/MEMORY.md
```

If under 150 lines, steps 2-4 are optional but still good practice.

## Step 2: Verify Open Work list

For each issue listed under `## Open Work` in MEMORY.md, run:

```bash
gh issue view <number> --json state,title -q '"\(.state) \(.title)"'
```

- If **CLOSED**: move it from Open Work → Recent Completed (one line), or drop it if trivial.
- If **OPEN**: leave it. Update the description if it changed.

## Step 3: Archive old completed work

If `## Recent Completed Work` has more than 30 items, or items older than 30 days:

1. Cut the oldest batch from MEMORY.md
2. Paste into `~/.claude/projects/-home-kali-Desktop-AutoBot/memory/completed-history.md`
3. Keep entries as single lines: `- **#NNN**: one-phrase summary. Commit abc1234.`

## Step 4: Prune stale gotchas

Scan `## Ansible Gotchas`, `## Key Operational Notes`, and `## SLM Architecture Notes` for:
- Notes referencing issues that are now closed/resolved (e.g. "fixed in #954")
- Notes about OS versions/paths that have since changed
- Duplicate info already covered by CLAUDE.md

Delete stale entries. CLAUDE.md is the source of truth for stable patterns — MEMORY.md is only for things CLAUDE.md doesn't cover.

## Step 5: Enforce line limit

```bash
wc -l ~/.claude/projects/-home-kali-Desktop-AutoBot/memory/MEMORY.md
```

Target: under 150 lines. Hard limit: 200 lines (truncation point).
If still over 150, repeat steps 3-4 more aggressively.

## Step 6: Save

The memory files are plain markdown — no commit needed (they live outside the git repo).
Announce: "Memory cleanup complete. MEMORY.md is now X lines."
```

**Step 2: Verify the file exists and is readable**

```bash
cat ~/.claude/skills/memory-cleanup/SKILL.md | head -5
```

Expected: frontmatter `name: memory-cleanup` visible.

---

### Task 2: Add `SessionStart` hook to settings.json

**Files:**
- Modify: `~/.claude/settings.json`

**Step 1: Read the current hooks section to find the insertion point**

The current hooks object has `PreToolUse` and `PostToolUse`. We add `SessionStart` as a sibling key.

**Step 2: Add the SessionStart hook**

Add the following inside the `"hooks"` object in `~/.claude/settings.json`:

```json
"SessionStart": [
  {
    "hooks": [
      {
        "type": "command",
        "command": "MEMORY_FILE=\"/home/kali/.claude/projects/-home-kali-Desktop-AutoBot/memory/MEMORY.md\"; if [ -f \"$MEMORY_FILE\" ]; then LINES=$(wc -l < \"$MEMORY_FILE\"); if [ \"$LINES\" -gt 150 ]; then echo \"WARNING: MEMORY.md is ${LINES} lines (limit 150). Run /memory-cleanup to reduce context rot.\"; fi; OPEN_COUNT=$(grep -c '^\- \*\*#' \"$MEMORY_FILE\" 2>/dev/null || echo 0); echo \"Memory: ${LINES} lines, approx ${OPEN_COUNT} tracked items.\"; fi",
        "statusMessage": "Checking memory health..."
      }
    ]
  }
]
```

**Step 3: Verify settings.json is valid JSON**

```bash
python3 -m json.tool ~/.claude/settings.json > /dev/null && echo "Valid JSON"
```

Expected: `Valid JSON`

---

### Task 3: Add memory hygiene rules to MEMORY.md header

**Files:**
- Modify: `~/.claude/projects/-home-kali-Desktop-AutoBot/memory/MEMORY.md`

**Step 1: Add a rules block at the top of MEMORY.md** (after the title, before Open Work)

Insert this after line 1 (`# AutoBot Project Memory`):

```markdown

> **Rules:** Target <150 lines. Hard limit 200 (truncated after). Run `/memory-cleanup` at session end.
> Archive completed work >30 days old to `completed-history.md`. One line per closed issue.
> Delete gotchas that reference resolved issues. CLAUDE.md owns stable patterns — this file owns recent state.
>
> Pre-Feb-17 issue history: [completed-history.md](completed-history.md)
```

(This replaces the existing bare link to completed-history.md.)

**Step 2: Verify MEMORY.md still reads cleanly**

```bash
head -8 ~/.claude/projects/-home-kali-Desktop-AutoBot/memory/MEMORY.md
```

Expected: title + rules blockquote + blank line before `## Open Work`.

---

### Task 4: Add Memory Hygiene section to CLAUDE.md

**Files:**
- Modify: `/home/kali/Desktop/AutoBot/CLAUDE.md`

**Step 1: Add section after `## SESSION BOUNDARIES` section**

Add the following new section:

```markdown
## MEMORY HYGIENE (MANDATORY)

**Rules for `~/.claude/projects/.../memory/MEMORY.md`:**

- **Line limit:** Target <150 lines. Hard limit 200 (file is truncated after line 200).
- **One line per issue:** Each closed issue gets exactly one line: `#NNN: phrase. Commit abc1234.`
- **Archive threshold:** When Recent Completed exceeds 30 items or 30 days old → move to `completed-history.md`
- **Prune gotchas:** Delete notes that reference resolved issues or duplicate CLAUDE.md content
- **Source of truth split:** CLAUDE.md owns stable patterns/standards. MEMORY.md owns recent state only.

**End-of-session ritual (60 seconds):**

1. Did I close any issues? → Move from Open Work to Recent Completed (1 line each)
2. Did any gotcha get resolved? → Delete it
3. Is Recent Completed >30 items? → Archive oldest batch to `completed-history.md`
4. Is MEMORY.md >150 lines? → Trim now using `/memory-cleanup` skill

**Run `/memory-cleanup`** for a guided walkthrough of this ritual.
```

**Step 2: Verify CLAUDE.md still looks correct around the insertion**

```bash
grep -n "MEMORY HYGIENE\|SESSION BOUNDARIES\|MULTI-AGENT" /home/kali/Desktop/AutoBot/CLAUDE.md | head -10
```

Expected: all three headings visible, MEMORY HYGIENE appearing after SESSION BOUNDARIES.

**Step 3: Commit the CLAUDE.md change**

```bash
cd /home/kali/Desktop/AutoBot
git add CLAUDE.md
git commit -m "docs(workflow): add memory hygiene policy to CLAUDE.md"
```

---

## Verification Checklist

After all 4 tasks:

- [ ] `~/.claude/skills/memory-cleanup/SKILL.md` exists
- [ ] `Skill` tool can invoke `memory-cleanup`
- [ ] `~/.claude/settings.json` is valid JSON with `SessionStart` hook
- [ ] `MEMORY.md` starts with rules blockquote
- [ ] `CLAUDE.md` has `## MEMORY HYGIENE` section
- [ ] CLAUDE.md committed to git
