When to use: Fast findings-first security review of a diff — emits a findings table within 3 tool calls, then verifies. Use when asked to security-review a diff, branch, uncommitted changes, or "check this for vulnerabilities". For deep multi-agent PR review use `/autobot-dev-skills:review review-fleet` instead; for whole-codebase audits use the `autobot-dev-skills:reviewer` agent with the security-auditor lens.

# Secreview — Findings Before Exploration

A diff-scoped security review that **emits before it explores**. Partial value
delivered in seconds beats total value delivered in minutes — a review that is
abandoned mid-exploration delivers nothing at all.

## The Ordering Contract (non-negotiable)

1. **One orientation call.** Read the diff. Nothing else.
2. **Findings table within 3 tool calls.** No preamble, no full-file reads, no
   codebase greps before the table is on screen.
3. **Verify after.** Only once the table is printed, read supporting files to
   confirm, downgrade, or drop each finding.
4. **Verdict last.** `BLOCK` / `APPROVE-WITH-NITS` / `APPROVE`.

Never reorder these. A finding stated with `CONFIDENCE: unverified` and corrected
in step 3 is useful; a perfectly-verified finding that never gets printed is not.

## When NOT to use this skill

| Situation | Use instead |
|---|---|
| Unbounded review of the branch, thoroughness over speed | built-in `/security-review` |
| Deep, recall-biased review of an open PR | `/autobot-dev-skills:review review-fleet` (10 parallel finder + verifier agents) |
| Whole-codebase security audit | `autobot-dev-skills:reviewer` agent, security-auditor lens (`/autobot-dev-skills:review security-auditor`) |
| Syntax, imports, types, lint before merge | `/autobot-dev-skills:review pre-merge-validate` |
| CI triage / PR merge cycle | `/autobot-dev-skills:review review` |

This skill is the **fast path**. Reach for it when the answer is wanted now.

## Step 1 — Orientation (ONE call)

```bash
# Pick whichever matches the ask; run exactly one.
git diff                                  # uncommitted changes
git diff --staged                         # staged changes
git diff origin/main...HEAD        # whole branch vs base
gh pr diff <number>                       # a specific PR
```

If the diff exceeds ~1500 lines, add `--stat` first and review the highest-risk
files by name (auth, config, secrets, migrations, routers, middleware) — but
still emit the table within the 3-call ceiling. Say explicitly which files were
deferred; never let truncation read as "everything was covered".
