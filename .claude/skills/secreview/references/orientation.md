# Secreview — orientation (step 1)

The ordering contract, and why the table comes before exploration, live in `SKILL.md`; this file covers when not to use the skill, choosing the diff command, and the large-diff rule.

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
