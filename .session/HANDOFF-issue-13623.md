# Handoff: issue-13623

status: complete
pr: (see PR body link)
base_at_push: e1431137d
gates: n/a — docs-only change, no code touched
needs_rebase_before_merge: no
remaining:
- No code was written this session. All findings are filed as issues; none are implemented.
- Start with #13626 (live bug: OAuth refresh without `expires_in` permanently disables refresh).
worktree: .worktrees/issue-13623  (safe to remove after merge)

## Context

Research/audit session. Reviewed an external connector-gateway implementation against our
connector, credential and egress layer. Produced `docs/research/connector-credential-egress-audit.md`
and filed umbrella #13623 with children #13624-#13632, plus #13643 under #10088 Task 5.

Two live bugs found (#13626, #13627) — both in `knowledge/connectors/credential_store.py`, both
silent in production.

## Notes for the next session

- The doc deliberately does not name the external source product (owner rule: no external
  product/author names in repo docs *or* GitHub issues).
- #13632 is an owner decision (two connector families) and blocks nothing.
- Policy-audit-trail idea was folded into #13588/#13592 rather than filed — do not re-file.
- Progressive tool discovery was evaluated and **rejected** at our scale; the revisit trigger is
  recorded in the doc. Do not re-propose without that trigger being met.
