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

## Step 4 — Report and ask

```bash
gh issue view <new-number>   # Confirm creation
```

Then report:
```
Created #<number>: <title>
Labels: <type> · <area> · <priority>
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
