---
name: review
description: Run a PR review cycle — CI diagnosis, a three-angle finder pass, lint-only auto-fix, and the merge decision. Use when reviewing open PRs, working the review queue, or when a heartbeat tick has no assigned issue.
---

# Review Skill

Use this skill when running a PR review cycle — either from a heartbeat or manually.

## Pre-Flight

1. List the open PRs: `gh pr list --state open --json number -q 'length'` — for scope, not for gating.
   - **There is no open-PR limit.** Dispatch gates on review capacity, not PR count. PRs
     accumulating means review is the bottleneck — do that, don't defer new work.
2. Check model availability and remaining usage. If low, switch to Haiku for status-only tasks.
3. Filter task queue: skip anything blocked on human action (OAuth, branch-protection admin). Log why each was skipped — do not retry.

## CI Diagnosis (Before Any Action)

For each PR, classify CI status as **passing**, **failing**, or **queued/running**:
```bash
gh pr checks <number> --json name,state,conclusion
```
- **Do not cancel or retrigger queued checks** — they are running normally on self-hosted runners
- Only act on checks in state `failure` or `error`
- Treat `code-quality` as a required blocking check

## Review Each PR (3-Angle Protocol)

For each PR with green or actionable CI:

1. Get exact file list: `gh pr diff $PR --name-only`
2. Dispatch 3 parallel finder agents with scoped prompts:
   - Security/auth/tenancy angle
   - Correctness/logic angle
   - Data-layer/edge-cases angle
3. Each agent: read only the listed files, return JSON `{file, line, severity, evidence}`
4. Verification pass: re-read each cited location, reject findings not grounded in real code

## Auto-Fix (Lint/Format Only)

For PRs blocked only on Black/isort/flake8/mypy:
1. Check out on a feature branch (if branch-protected, never push direct)
2. Run: `black . && isort . && ruff check --fix .`
3. Commit and push to the PR branch

## Merge Decision

Merge when:
- All required checks pass (not just code-quality)
- No blocking findings from the review pass
- The branch is not behind base — a green run describes a merge base that may have moved

Do NOT merge when:
- CI checks are queued (wait for them)
- Blocking security or correctness findings exist
- CI is red — root-cause it; a tracking issue is not a substitute

## PR Description Format

When creating or editing PR bodies, use these exact headings:
```
## Thinking Path
## What Changed
## Verification
## Model Used
```
Never use standard GitHub template sections (Summary, Test Plan, etc.).

## Checkpoint

After each PR cycle, write a brief status comment on the review's source issue:
- PRs reviewed: list with outcome
- PRs merged: list
- PRs still blocked: list with reason
- Next action: what the next heartbeat should do

This ensures the next heartbeat resumes cleanly instead of re-doing the same work.
