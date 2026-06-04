---
name: canonical-audit
description: Run a full-codebase canonical-pattern audit and write a markdown report to .canonical-audit/. Use when the user asks for a canonical-style scan, a #7458 progress check, or a periodic audit between cron runs.
---

# /canonical-audit

Runs the canonical-check Python and infra runners in `--all` mode and writes both markdown and JSON sidecars to `.canonical-audit/` (gitignored). Then summarizes the report inline.

## Steps

1. Verify the runners exist:
   ```bash
   test -f tools/lint/canonical_check.py && test -f tools/lint/canonical_check_infra.py || echo "ERROR: canonical-check not installed"
   ```

2. Run the audit via the Make target (also creates `.canonical-audit/` if missing):
   ```bash
   make canonical-audit
   ```

3. Read the most recent markdown reports:
   ```bash
   ls -1t .canonical-audit/*.md | head -3
   ```
   Open each and surface the Summary table to the user.

4. If any rule has BLOCK-severity violations, also surface the top 5 offending files for that rule.

5. Do NOT auto-file GitHub issues. Report findings inline. Filing is a separate user-driven step.

## Notes

- Frontend audit (`canonical-check-fe`) does not yet support `--all` mode (deferred to Wave 3). It is skipped here.
- Reports go to `.canonical-audit/` locally and to GitHub Actions artifacts on the weekly cron run. Neither is committed.
