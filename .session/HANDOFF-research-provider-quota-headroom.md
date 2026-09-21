# Handoff: research-provider-quota-headroom

status: complete
pr: none — #15033 opened then CLOSED UNMERGED by user decision (superseded #15032, also closed)
base_at_push: see `git merge-base HEAD origin/Dev_new_gui`
gates: n/a — docs-only branch, no code changed, no gate applies
needs_rebase_before_merge: n/a — this branch is NOT intended to merge

## What this branch is

A single docs commit holding the research that produced umbrella #15021. It is
**parked, not pending**. The PR was closed on purpose: the decision-bearing content
was absorbed into #15021 (evidence table, design constraints, deliberately-not-adopted
table) and into the six child issues' scope sections, so merging would have left a
dated comparison snapshot in the repo with no consumer.

This branch is the ONLY surviving copy of the analysis. Do not delete it as part of a
routine sweep — it is not abandoned work, and it is not waiting on anything.

## Session scope

Research only. No code was built, by explicit instruction. `Dev_new_gui` is untouched.

## What was delivered (all in the issue tracker, not here)

- Umbrella #15021 — provider quota headroom + multi-account failover
- Wave 1: #15022 (degradation cause / needs_reauth), #15026 (headroom store — critical path)
- Wave 2: #15027 (/costs/quota-windows values + typed metrics), #15028 (headroom-aware routing)
- Wave 3: #15029 (multi-account credential pool), #15030 (frontend headroom UI)
- Independent: #15031 (ProviderOAuthConnect.vue hardcoded strings, 11 locales)

## Constraint carried into the issues

The external product analysed is deliberately not named in any outward artifact
(issues, PRs, this branch). The intent is selective adoption of capabilities, not a
port — #15021 carries a "Deliberately not adopted" table recording what was rejected
and why, so nobody later "completes" the picture.

## remaining

- HSM/KMS-rooted vault key gap is unfiled. It belongs under secrets umbrella #10088,
  not #15021 — different theme. `grep -rniE "hsm|yubikey|pkcs11"` over autobot_shared
  and autobot-backend returns no hits.

## worktree

`.worktrees/research-quotio-quota-failover` — directory name predates the branch
rename (local only, never published). Locked. Safe to remove ONLY once someone
decides the research doc is no longer wanted; removing it and the branch discards
the analysis permanently.
