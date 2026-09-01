---
name: issue
description: Complete GitHub issue creation workflow with required type, area, and priority labels
---

# Create GitHub Issue

Creates a well-labeled GitHub issue with all required metadata for filtering and triage.

## Step 1 — Gather details

If not provided upfront, collect:
- **Title**: concise, action-oriented ("Fix X", "Add Y", "Refactor Z")
- **Description**: what's broken or needed, where it is in the codebase, severity/impact
- **Discovered during**: which issue or PR surfaced this (if applicable)

## Step 2 — Choose labels

**Every issue requires at minimum: one Type + one Priority.**

### Type (pick one)
| Label | When |
|-------|------|
| `bug` | Something broken |
| `enhancement` | New feature or improvement |
| `technical-debt` | Cleanup, refactoring |
| `security` | Security vulnerability or hardening |
| `performance` | Speed, memory, efficiency |
| `testing` | Missing or broken tests |
| `documentation` | Docs gap |

### Area (pick one or more)
`backend` · `frontend` · `devops` · `database` · `mcp` · `rag` · `deployment`
`monitoring` · `configuration` · `error-handling` · `optimization`

### Priority (pick one)
| Label | When |
|-------|------|
| `priority: critical` | Data loss, security breach, production down |
| `priority: high` | Major feature broken, significant user impact |
| `priority: medium` | Important but workaround exists |
| `priority: low` | Cosmetic, nice-to-have, minor inconvenience |

## Step 3 — Create issue

```bash
gh issue create \
  --title "<title>" \
  --body "$(cat <<'EOF'
## Problem
<what's wrong or needed>

## Location
<file paths, function names, line numbers>

## Impact
<who is affected and how>

## Discovered During
Working on #<original-issue> (if applicable)

## Acceptance Criteria
- [ ] <criterion 1>
- [ ] <criterion 2>
EOF
)" \
  --label "<type>,<area>,<priority>"
```

## Step 4 — Link relationships (native, not prose)

A checklist item and a `Depends on: #N` line are prose — GitHub's hierarchy and dependency
graphs cannot see them. Record the real edges immediately after creating the issue.
`sub_issue_id` / `issue_id` take the issue's `id`, never its number.

```bash
REPO=mrveiss/AutoBot-AI

# Attach to its umbrella
gh api -X POST repos/$REPO/issues/$UMBRELLA/sub_issues \
  -F sub_issue_id=$(gh api repos/$REPO/issues/$NEW -q .id)

# One edge per blocker, recorded on the BLOCKED issue
gh api -X POST repos/$REPO/issues/$NEW/dependencies/blocked_by \
  -F issue_id=$(gh api repos/$REPO/issues/$BLOCKER -q .id)

# Read back
gh api repos/$REPO/issues/$UMBRELLA/sub_issues         -q '.[].number'
gh api repos/$REPO/issues/$NEW/dependencies/blocked_by -q '.[].number'
```

- One parent per child — re-parenting is `DELETE .../sub_issue -F sub_issue_id=…` then POST.
- Backfilling from an existing checklist: a row owns **at most one** issue. Refs in parentheses,
  or after `blocked by` / `depends on` / `unblocks` / `sub-tree` / `PR`, are commentary — linking
  them re-parents another umbrella's child, and one-parent-per-child then blocks the real parent.
- A duplicate POST returns 422; that means already-linked, not a failure.
- Hierarchy and dependency are separate graphs — never encode one as the other.
- Issue *types* are an org-only GitHub feature and 404 here; labels stay the taxonomy.

## Step 5 — Report and ask

```bash
gh issue view <new-number>   # Confirm creation
```

Then report:
```
Created #<number>: <title>
Labels: <type> · <area> · <priority>
Parent: #<umbrella> (native sub-issue) · Blocked by: #<n>, #<n>
Should I: a) Fix now  b) Finish current issue first  c) Leave for later
```

## Examples

```bash
# Bug discovered during implementation
gh issue create \
  --title "Bug: query_cache has no max size limit" \
  --label "bug,backend,rag,priority: medium"

# New feature
gh issue create \
  --title "feat: add BM25 scoring to keyword search" \
  --label "enhancement,backend,rag,performance,priority: medium"

# Security issue
gh issue create \
  --title "Security: python-ecdsa Minerva timing attack" \
  --label "security,backend,priority: high"
```

## Post-task Gap Check (ALWAYS after completing any task)

> "Were there any gaps or issues discovered while implementing? Do all discoveries have a GitHub issue?"

If yes → run this skill immediately for each discovery before closing the original issue.
