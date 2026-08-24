---
name: github-cli
description: Use when performing any GitHub operation — issues, PRs, comments, labels, reviews, merges, file contents, branch management, or repository queries. Always prefer gh CLI over GitHub MCP tools.
---

# GitHub CLI (gh)

Use `gh` for all GitHub operations. Never use browser automation or GitHub MCP tools when `gh` will do.

## Issues

```bash
# View / list
gh issue view <number>
gh issue list --state open --label "bug,backend"
gh issue list --assignee @me

# Create
gh issue create --title "Bug: <desc>" --body "..." --label "bug,backend,priority: high"

# Update / close
gh issue comment <number> --body "..."
gh issue close <number>
gh issue edit <number> --add-label "priority: high" --title "New title"

# Check state
gh issue view <number> --json state -q '.state'
```

## Pull Requests

```bash
# View / list
gh pr view [number]
gh pr list --state open
gh pr diff [number]

# Create (always target Dev_new_gui)
gh pr create --base Dev_new_gui --title "..." --body "..."

# Review / merge
gh pr review <number> --approve
gh pr merge <number> --squash

# Status checks
gh pr status
gh pr checks <number>
```

## Files & Code

```bash
# Get file from any branch/ref
gh api repos/mrveiss/AutoBot-AI/contents/<path>?ref=<branch> --jq '.content' | base64 -d

# Search code
gh search code "query" --repo mrveiss/AutoBot-AI
```

## Comments & Reviews

```bash
gh pr comment <number> --body "..."
gh issue comment <number> --body "..."
gh pr review <number> --comment --body "..."
```

## Quick Reference

| Task | Command |
|------|---------|
| View issue | `gh issue view <n>` |
| Create issue | `gh issue create --title "..." --label "..."` |
| Close issue | `gh issue close <n>` |
| Create PR | `gh pr create --base Dev_new_gui ...` |
| View PR diff | `gh pr diff <n>` |
| Merge PR | `gh pr merge <n> --squash` |
| List labels | `gh label list` |
| View checks | `gh pr checks <n>` |

## AutoBot Conventions

- **Repo:** `mrveiss/AutoBot-AI`
- **Base branch:** Always `Dev_new_gui` (never `main`) for PRs
- **Required labels:** type (`bug`, `enhancement`, `technical-debt`) + area (`backend`, `frontend`) + priority (`priority: high`, etc.)
- **Commit/PR title format:** `<type>(scope): <description> (#issue-number)`
- **Auto-close limitation:** `Closes #NNN` in a PR body **does not auto-close issues** when merging into `Dev_new_gui` (only works for the default branch). **Always close the GH issue manually after merge:**
  ```bash
  gh pr merge <pr> --squash --delete-branch
  gh issue close <number> --comment "Closed via PR #<pr> merged into Dev_new_gui."
  gh issue view <number> --json state  # confirm state=CLOSED
  ```

## Common Mistakes

- Targeting `main` instead of `Dev_new_gui` for PRs
- Forgetting required labels on new issues
- Assuming `Closes #NNN` in PR body auto-closes the issue (it doesn't for `Dev_new_gui`)
- Merging a PR without immediately closing the linked GH issue — issues stay open forever otherwise
- Using Playwright/browser for GitHub when `gh` handles it in one command
