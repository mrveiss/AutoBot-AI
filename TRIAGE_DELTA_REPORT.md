<!--
Copyright 2025-2026 mrveiss
SPDX-License-Identifier: Apache-2.0
-->

# Triage Delta Report — 2026-06-12

Mission: restore the umbrella structure (#9919–#9931) and file all unorganized
open issues under it. **Triage/organize only — nothing was fixed.**
Predecessor: 2026-06-11 triage (PR #9932, `UMBRELLA_PLAN.md`).

---

## Phase 0 — Umbrella restore

| Umbrella | Found | Closing cause | Action |
|---|---|---|---|
| U1 #9919 | **CLOSED** (state_reason: completed) | **Manual close by agent** 2026-06-11T19:14Z — timeline `closed` event has no commit and no PR source; closed at batch-session end after the last member PR (#9948) merged | **REOPENED** — theme has open issues (#9825 upstream-blocked, #9949/#9950 prose-noted but never task-listed, #10026 new) |
| U2 #9920 | **CLOSED** (state_reason: completed) | **Manual close by agent** 2026-06-11T18:05Z — same pattern, after PRs #9988/#9989 merged | **REOPENED** — theme has 5 open follow-ups (#9980, #10001, #10002, #10026, #10027), four cross-referenced onto the issue *after* it closed |
| U3–U13 #9921–#9931 | open | — | no action needed |

- Neither close came from a PR closing keyword — both were end-of-session agent
  closes on task-list completion. The lifecycle rule (human-only closes) is now
  codified in `UMBRELLA_PLAN.md` § *Umbrella lifecycle*.
- Reopen comment posted on both: *"Reopened: umbrella epics close only by explicit
  human decision, not by PR keywords or task-list completion."*
- **Labels:** all 13 umbrellas still carry `umbrella` — none lost it, none re-added.
- **Prevention sweep:** 3 open PRs (#10004, #10028, #10029) — **zero** closing
  keywords aimed at #9919–#9931; **no PR body edits were needed**.

## Phase 1 — Inventory

- 151 open issues; 13 are the umbrellas themselves.
- Organized set: 124 issues already in umbrella task lists — including 5 post-triage
  issues that wave sessions had already appended (#10019/#10022/#10023 → U6,
  #10024 → U9, #10025 → U4).
- **Work set: 42 issues**, all created 2026-06-11 (wave-review follow-ups and
  live-console findings). No pre-#9942 issue was missed by the first triage pass.

## Phase 2/3 — Disposition

**Closed stale: 0.** Every candidate was checked against the 22 PRs merged since
2026-06-11T12:00Z — all 42 were *produced by* those PRs' reviews (follow-ups),
none is *resolved by* them. **Duplicates merged: 0** (near-pairs #9965/#9999,
#9982/#9996, #10011/#10012 verified as distinct scopes).
**Unfiled / needs-taxonomy-decision: 0** — all 42 placed. **Filed: 42**, appended
to umbrella bodies as dated `### Triage delta` sections (existing lists preserved):

| Umbrella | Filed | Issues |
|---|---:|---|
| U1 #9919 deployment-install | 17 | #9949 #9950 #9956 #9965 #9966 #9967 #9982 #9996 #10000 #10005 #10006 #10007 #10010 #10016 #10020 #10021 #10026 |
| U2 #9920 data-layer | 4 | #9980 #10001 #10002 #10027 |
| U3 #9921 code-intelligence | 1 | #10008 |
| U4 #9922 api-contract | 8 | #9958 #9959 #9983 #9985 #9986 #10011 #10012 #10013 |
| U5 #9923 llc-module | 5 | #9951 #9978 #9987 #9992 #9995 |
| U7 #9925 transcriber | 1 | #9968 |
| U11 #9929 product-features | 6 | #9942 #9943 #9984 #9999 #10017 #10018 |

Boundary calls worth review:
- **#10001 → U2, #10026 → U1** per the dispatch boundary rule; the ordering edge
  (**#10026 must land before #10001**) is noted inline on both entries — #10001's
  fix would start running the repaired chain against never-migrated populated DBs.
- **#9968 → U7** (not U4): the IDOR regression was introduced by U4's PR #9955,
  but the transcriber umbrella owns the broken auth surface (subsystem-owner rule).
- **#9951 → U5** (not U1): #9919's prose listed it as a "new member", but the
  defect lives in `llc/scheduler/heartbeat_scheduler.py` — subsystem owner is U5.
- **#10016 (SLM lifecycle completeness)** is itself an epic; filed as a
  **sub-epic inside U1** rather than inventing a 14th umbrella (taxonomy changes
  are the human's call — promote it if you prefer).
- **#10010 → U1**: LLC API surface, but the defect class is single_user Postgres
  gating policy (#9765/#9913 class), which U1 owns.

Dependency edges recorded inline on both ends: #10026⇄#10001 (ordering),
#9984 blocks #10018 (nav gating before rebuild), #9999⇄#9965 (UX facet vs
deploy-side cause), #10027 prerequisite-for #10026's guard option.

Labels applied: `agents` → #9951/#9978/#9987/#9995; `infrastructure` →
#9966/#9967/#10010/#10021; `needs-human-decision` → #9983 (reimplement-or-retire
is a product call). `bug` was already present on every defect-shaped issue.

## Filed during this session

- **#10035** (→ U9 #9927) — this session's freshly-pushed unmerged remote branch
  was deleted within ~2 minutes of push (before the PR could be created); the
  scheduled `branch-cleanup.yml` is exonerated (last run 06:22 UTC, pre-push).
  Suspect: parallel-session merged-branch remote pruning misclassifying the
  branch. Issue includes the guard spec for #9917's implementation. The session's
  first **local** worktree was also swept by a parallel session's start-protocol
  (commit-less branch == "merged" — by-design; mitigation: anchor-commit
  immediately after worktree creation).

## Regression cluster

**Co-located / deploy-update surface** — 9 of 42 new issues trace to it:
#9965 #9966 #9967 #9982 #9996 #10006 #10007 #10020 #10021. Suspect recently-merged
PRs: **#9991** (one-click update, → #9996 #10021), **#9933/#9952** (co-located
nginx routing, → #9966 #9967), plus latent never-tested paths (#9982 resolve_drift,
#10020 dual autobot_shared). This matches the 2026-06-11 bug-wave finding that the
co-located/deploy surface has **no automated gate** — #10023 (U6, co-located smoke
gate) is the structural fix and should be treated as that cluster's exit criterion.

Secondary cluster: **LLC test-harness trust** (#9987 #9995 + adapter blind spots
#9992 #9951) — suspect area is `llc/tests` full-suite isolation, not any single PR.

## Recommended next-dispatch order (changed from UMBRELLA_PLAN.md waves)

1. **U1 #10026 → U2 #10001** (strict order, release-gating)
2. **U4 live-console contract cluster** (8 issues, user-visible breakage)
3. **U1 deploy-surface cluster** + U6 #10023 gate (the regression cluster above)
4. **U7 #9968** (IDOR, priority-high — jump the queue)
5. **U11 #9984 → #10018/#10017** rebuild track
Full rationale in `UMBRELLA_PLAN.md` § *Dispatch-order delta — 2026-06-12*.

---

*LICENSE/NOTICE/SPDX untouched (read-only per mission). No code changed.*
