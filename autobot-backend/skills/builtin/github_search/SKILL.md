---
name: github-search
version: 1.0.0
description: Search GitHub repositories, issues, code, and PRs using the gh CLI
author: mrveiss
category: internet
tools:
  - search_repos
  - search_issues
  - search_code
  - search_prs
  - view_issue
  - view_pr
triggers:
  - search GitHub
  - find GitHub repo
  - look up issue
  - gh search
  - GitHub PR
  - GitHub issue
  - find code on GitHub
  - repository search
  - open source library
tags:
  - github
  - search
  - gh
  - cli
  - repositories
  - issues
  - pull-requests
  - code-search
---

## Capability Tiers

```
┌─────────────────────────────────────────────────────────────┐
│ github-search                                                 │
├─────────────────────────────────────────────────────────────┤
│ STANDALONE   (always works, zero config)                     │
│   • Search public repos / issues / PRs via unauthenticated   │
│     GitHub REST API (curl fallback)                          │
├─────────────────────────────────────────────────────────────┤
│ SUPERCHARGED (unlocks when you connect a tool)               │
│   • gh auth login / GITHUB_TOKEN → gh CLI subcommands,       │
│     higher rate limits, private-repo access, JSON/jq output  │
└─────────────────────────────────────────────────────────────┘
```

**STANDALONE — always works, zero config**

- Search public repositories, issues, and pull requests through the
  unauthenticated GitHub REST API (`curl 'https://api.github.com/search/...'`).
- Subject to GitHub's low anonymous rate limit; public results only.

**SUPERCHARGED — unlocks per connected tool**

| Connect this | Unlocks |
|--------------|---------|
| `gh auth login` **or** `GITHUB_TOKEN` | Native `gh search` / `gh view` subcommands, `--json` / `--jq` / `--template` output, higher authenticated rate limits, and access to private repos the token can see. |

The skill prefers the authenticated `gh` path when available and degrades to the
anonymous REST tier otherwise — no configuration change is required to fall back.

## Output Contract

Search results are returned in this fixed shape:

```
## GitHub Search: <query>

**Tier used:** gh-cli (authenticated) | rest-api (anonymous)
**Results:** <n>

| # | Name / Ref | Stars/State | Description |
|---|-----------|-------------|-------------|
| 1 | owner/repo | ★ 1.2k     | ...         |
```

Detail lookups (`view_issue` / `view_pr`) return:

```
## <owner>/<repo>#<number> — <title>

**State:** open | closed   **Author:** <login>   **Labels:** ...

<body excerpt>
```

## When to Use

Use this skill when an agent needs to search or retrieve data from GitHub —
finding repositories, reading issues, searching code, or listing pull requests.
The `gh` CLI is the preferred tool because it handles authentication, pagination,
and JSON output natively without requiring manual API key management.

## Workflow

### Search repositories

```bash
# Find repositories matching a query
gh search repos '{query}' --limit {n}

# Filter by language or topic
gh search repos '{query}' --language python --limit 10
gh search repos '{query}' --topic 'machine-learning' --limit 10

# Sort by stars
gh search repos '{query}' --sort stars --order desc --limit 10
```

### Search issues and pull requests

```bash
# Search issues across GitHub
gh search issues '{query}' --limit 10

# Search issues in a specific repo
gh search issues '{query}' --repo {owner}/{repo} --state open

# Search pull requests
gh search prs '{query}' --repo {owner}/{repo} --state open
```

### Search code

```bash
# Full-text code search across GitHub
gh search code '{query}'

# Restrict to a single repository
gh search code '{query}' --repo {owner}/{repo}
```

### View a specific issue or PR

```bash
gh issue view {number} --repo {owner}/{repo}
gh pr view {number} --repo {owner}/{repo}
```

### Get JSON output for scripting

```bash
gh search repos '{query}' --json name,url,stargazerCount,description --limit 10
gh issue view {number} --repo {owner}/{repo} --json number,title,body,labels
```

### Direct API access (for operations not covered by subcommands)

```bash
gh api repos/{owner}/{repo}/issues/{number}
gh api --paginate repos/{owner}/{repo}/issues --jq '.[].number'
```

## Output Format

- **Default:** Human-readable table (repo name, description, stars) or detail view.
- **--json:** Machine-readable JSON; pipe through `jq` for field extraction.
- **--jq:** Inline JQ filter applied to JSON output in a single command.
- **--template:** Go template for custom formatting.

## Parameters

| Parameter | Type   | Required | Description                                     |
|-----------|--------|----------|-------------------------------------------------|
| query     | string | yes      | Search query (supports GitHub search qualifiers) |
| owner     | string | no       | Repository owner for scoped searches            |
| repo      | string | no       | Repository name for scoped searches             |
| limit     | int    | no       | Max results to return (default 30, max 100)     |
| state     | string | no       | `open`, `closed`, or `all` for issues/PRs       |

## Limitations

- Requires `gh auth login` or `GITHUB_TOKEN` environment variable to be set.
- Code search API has a rate limit of 10 requests/minute for authenticated users.
- Search results are limited to public repositories unless authenticated with
  access to private repos.
- `gh search code` returns file-level results, not line-level matches without
  additional API calls.

## Fallback Instructions

If `gh` is not authenticated or returns a 401 error:
1. Check `gh auth status` to confirm login state.
2. If not logged in, run `gh auth login` (requires interactive session) or set
   the `GITHUB_TOKEN` environment variable.
3. If rate limited (403 with rate_limit message), check `gh api rate_limit` and
   wait until the reset timestamp.
4. For unauthenticated fallback, use the GitHub REST API via curl:
   ```bash
   curl -s 'https://api.github.com/search/repositories?q={query}&per_page=10'
   ```
