---
name: secreview
description: Fast findings-first security review of a diff; emits a findings table within 3 tool calls, then verifies. Use when asked to security-review a diff, branch, uncommitted changes, or "check this for vulnerabilities".
---

# Secreview: findings before exploration

Diff-scoped security review that emits before it explores. Deep PR review is
`/autobot-dev-skills:review review-fleet`; whole-codebase audit is the
`autobot-dev-skills:reviewer` agent with the security-auditor lens.

## Ordering contract (non-negotiable)

1. **One orientation call.** Read the diff. Nothing else.
2. **Findings table within 3 tool calls.** No preamble, no full-file reads, no
   codebase greps before the table is on screen.
3. **Verify after.** Only once the table is printed, read supporting files to
   confirm, downgrade, or drop each finding.
4. **Verdict last.** `BLOCK` / `APPROVE-WITH-NITS` / `APPROVE`.

Table columns: `| Sev | file:line | Issue | Fix |`. Severity `CRITICAL` / `HIGH` /
`MEDIUM` / `LOW` / `NIT`; mark unconfirmed rows `(unverified)`.

## Router: read on demand

| Step | Read |
|---|---|
| Choose the diff command; when not to use this skill; large-diff rule | `references/orientation.md` |
| Table format, threat-model pointer, review checklist (authz, secrets, injection, concurrency, refactor fallout) | `references/findings-and-checklist.md` |
| Verify each finding, verdict rules, follow-up and report location | `references/verify-and-verdict.md` |
