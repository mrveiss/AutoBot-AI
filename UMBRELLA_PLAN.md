<!--
Copyright 2025-2026 mrveiss
SPDX-License-Identifier: Apache-2.0
-->

# AutoBot Open-Tracker Umbrella Plan — 2026-06-11

Triage of the **122 open issues** (was 124; #9914/#9915 closed-with-evidence below)
into **13 umbrella epics**. Triage/organize only — no code was fixed.
0 open PRs at triage time, so umbrellas reflect real remaining work, not in-flight PRs.

| Umbrella | Issue | Theme | Members | +Δ 06-12 | Total |
|---|---|---|---:|---:|---:|
| U1 | **#9919** | deployment-install | 14 | +17 | 31 |
| U2 | **#9920** | data-layer (schema/migrations) | 2 | +4 | 6 |
| U3 | **#9921** | code-intelligence / verify-leg | 7 | +1 | 8 |
| U4 | **#9922** | api-contract | 7 | +9 | 16 |
| U5 | **#9923** | llc-module | 18 | +5 | 23 |
| U6 | **#9924** | test-infra / CI | 11 | +3 | 14 |
| U7 | **#9925** | transcriber | 11 | +1 | 12 |
| U8 | **#9926** | docs-positioning | 10 | — | 10 |
| U9 | **#9927** | governance | 6 | +1 | 7 |
| U10 | **#9928** | integrations-plugins | 10 | — | 10 |
| U11 | **#9929** | product-features | 18 | +6 | 24 |
| U12 | **#9930** | enterprise-auth (SSO) | 7 | — | 7 |
| U13 | **#9931** | codebase-recovery | 3 | — | 3 |

> **2026-06-12 triage delta:** 42 issues filed 2026-06-11 (wave-review follow-ups +
> live-console findings) were placed; member counts above include closed members.
> U4's +9 and U6's +3 include #10025 and #10019/#10022/#10023, which wave sessions
> had already appended; U9's +1 is #10024. The other 37 were appended 2026-06-12
> (`### Triage delta` sections in each umbrella body). #10016 (SLM lifecycle
> completeness) is tracked as a **sub-epic inside U1**, not a 14th umbrella.

> Taxonomy extension: U1–U9 are the dispatch-prompt umbrellas. U10–U13 were added
> because the product-feature / integration / recovery backlog (≈38 issues) fits
> none of U1–U9 — the prompt authorizes extension when an issue "genuinely fits nowhere."

## Umbrella lifecycle

**Umbrella epics close only by explicit human decision** — never by PR closing
keywords, never by an agent on task-list completion, never automatically.

- Reference umbrellas with **"part of #N"** in comments, PR bodies, and commit
  messages — NEVER `fixes`/`closes`/`resolves #N` (a merge would re-close the epic).
- Task-list completion is a signal to *ask the human*, not to close: follow-up
  discoveries routinely land after the last member merges (proven 2026-06-11:
  #9919/#9920 were agent-closed "complete" and accrued 21 new theme issues within
  hours; both reopened 2026-06-12).
- New members are **appended** to the umbrella task list (dated `### Triage delta`
  sections) — existing lists are never rewritten.

---

## Closed with evidence (provably resolved by merged PRs)
- **#9914** + **#9915** → PR **#9916** merged, squash commit `4d6b77495`
  (*fix(ansible): make fresh-VM fleet provisioning work out-of-box*). Backend role now
  deploys its systemd unit before `service: started`; `Set hostname` accepts the
  `node_00_SLM_Manager` underscore variant. Closed with a citing comment each.

_Already closed pre-triage (verified absent from open list), no action:_ #9784, #9710,
#9832, #9788, #9785, #9782, #9767, #9768, #9783 (bug-sweep `dbbd9541f`); #9873, #9896.

## Filed during triage
- **#9917** — governance: enable auto-delete-head-branches + automate merged-branch pruning (→ U9)
- **#9918** — governance: adopt session-lifecycle handoff protocol repo-wide (→ U9)

## Labels created
- `umbrella` (5319e7) — applied to the 13 epics.
- `needs-human-decision` (d93f0b) — applied to **#9863, #9664, #9852, #9766**.

---

## Dependency graph

```
                 U2 #9920 data-layer (Alembic chain #9759)  ── ROOT, highest leverage
                   │  blocks RBAC bootstrap
                   ├──────────────► U12 #9930 enterprise-auth (SSO)   [serial: needs RBAC]
                   └──────────────► U1 #9919 deployment-install (fresh-DB migration paths)
                                      │
   U3 #9921 verify-leg ◄─ gates "done" of every umbrella   U1 #9793 (compose agents)
                   │                                          │ blocks
                   ▼                                          ▼
   U4 #9922 api-contract ──► clean contract gate ──► U5 #9923 llc-module
                   │                                  (adapters need compose-exec via U1)
                   ├──► U10 #9928 integrations (wire-in consumers)
                   └──► U11 #9929 product-features (new FE consumers)

   Fully parallel, no hard inbound edges:
     U6 #9924 test-infra   U7 #9925 transcriber*   U8 #9926 docs   U9 #9927 governance   U13 #9931 recovery
     (*U7 has a soft edge on U4 #9863/#9900 — transcripts router mount/delete decision)
```

**Critical path:** `U2 #9759 → RBAC → U12 SSO`. This is the only deep serial chain;
everything else fans out. U2 is two issues but is the keystone — **dispatch it first, alone.**

### Edge summary
| Umbrella | Blocked by | Blocks |
|---|---|---|
| U1 | U2 (fresh-DB paths) | U5 (#9793 compose-exec), smoke-test stability |
| U2 | — (root) | RBAC → U12; U1 migration paths |
| U3 | — | trust in every umbrella's "done"; #9489 owned by worktree `pr-9630` |
| U4 | U3 (audit accuracy) | U10/U11 FE consumers; U7 (transcripts decision) |
| U5 | U1 #9793, U2 #9899 | LLC Beta→stable |
| U6 | — | masks regressions for all (clear early) |
| U7 | U4 #9863/#9900 (soft) | transcriber stable |
| U8 | — | public positioning |
| U9 | — | sustainable throughput for all |
| U10 | #9019 (OAuth→secrets, internal gate) | — |
| U11 | U4 (contract) | — |
| U12 | **U2 #9759 (RBAC)** | enterprise tier |
| U13 | — | feeds U5/U10/U11 on recovered finds |

---

## Recommended dispatch queue

**Wave 0 — unblock the keystone (serial, dispatch alone, highest priority):**
- **U2 #9920** — repair the Alembic chain (#9759). Nothing in the enterprise/RBAC line moves until this lands.

**Wave 1 — parallelize the independents (dispatch concurrently with Wave 0):**
- **U6 #9924** — green the CI baseline (a red baseline hides regressions for every other wave).
- **U3 #9921** — verify-leg repair (#9489 already owned by `pr-9630` — link, don't reassign).
- **U9 #9927** — governance automation (cheap, compounding throughput wins).
- **U8 #9926** — docs/licensing authoring (no code coupling).
- **U13 #9931** — recovery archaeology (investigative; surfaces feeds for later waves).

**Wave 2 — platform, after their gates clear:**
- **U1 #9919** — deployment-install (after U2 fresh-DB paths; #9793 unblocks U5).
- **U4 #9922** — api-contract (after U3 audit accuracy; unblocks U7/U10/U11 consumers).

**Wave 3 — features & adapters, after platform gates:**
- **U5 #9923** — llc-module (needs U1 #9793 + U2 #9899).
- **U7 #9925** — transcriber (needs U4 #9863/#9900 decision).
- **U10 #9928** — integrations (gate on internal #9019 first).
- **U11 #9929** — product-features (needs U4 contract).

**Wave 4 — enterprise tier (serial tail of the critical path):**
- **U12 #9930** — SSO/OIDC (needs U2 → RBAC).

> Parallelism budget: Waves 0+1 run **six umbrellas concurrently**. Honor the repo
> PR-queue limit (≥5 open PRs → defer) and the single self-hosted runner — stagger
> PR opens so smoke-test doesn't starve.

### Dispatch-order delta — 2026-06-12

Waves 0–3 largely executed 2026-06-11 (U1/U2 original members closed; U5 11/19
landed). The follow-up queue reorders as:

1. **U1 #10026 → U2 #10001** (strict order): the legacy-DB upgrade-path gate must
   land **before** the ansible alembic-invocation fix and before any tagged
   release — #10001's fix would start running the repaired chain against
   never-migrated populated DBs. #10027 (U2, shared guard helpers) is a
   prerequisite if #10026 chooses guards over stamp-baseline, and is the natural
   home for #9980's enum registry.
2. **U4 live-console contract cluster** (#10011/#10012/#10013 + #9958/#9959/#9983
   /#9985/#9986) — high-visibility user-facing breakage, mostly `S`/`M`, plus the
   already-listed #10025 lint guard.
3. **U1 deploy-surface cluster** (#9956/#9965/#9982/#9996/#10020 + co-located
   #9966/#9967) — the surface that produced all three June-10 regressions; pairs
   with U6's #10023 co-located smoke gate.
4. **U11 rebuild track**: #9984 (nav gating) is the prerequisite gate → then PRDs
   #10017/#10018 (human-approved, see issue bodies).
5. U5 delta (#9951/#9978/#9987/#9992/#9995) folds into the remaining U5 feature
   queue; U3 #10008 and U7 #9968 (security, `priority: high`) dispatch standalone —
   #9968 should jump the queue (IDOR).

---

## Per-umbrella mission statements (paste-ready for dispatch)

**U1 #9919 — deployment-install.** Make AutoBot install and upgrade cleanly out-of-the-box: `docker compose up` and fresh-VM Ansible provisioning must reach a healthy single-user-default stack with no tracebacks, no warn-floods, and correct service-to-service auth. Covers compose/secrets wiring, SLM↔backend auth, single_user Postgres gating, and ChromaDB reindex-on-upgrade. Backend is canonical; gate optional services rather than crash. 14 members; #9852/#9766 are needs-human-decision; depends on U2 for fresh-DB paths; #9793 unblocks U5.

**U2 #9920 — data-layer.** Repair the broken Alembic chain (#9759 — divergent heads, id mismatch, env.py) so fresh-DB upgrades work, then sync out-of-date ORM models to their migration columns (#9899). This is the graph root: it gates RBAC bootstrap, which gates the enterprise tier (U12). 2 members, but the single highest-leverage serial dependency — dispatch first, alone.

**U3 #9921 — code-intelligence / verify-leg.** Restore the security/code-intelligence verify-leg and the structural-quality cleanups it guards: repair the broken-and-unwired `security/` package (#9856), resolve Semgrep SAST (#9489, owned by worktree `pr-9630` — link only), tune scan gates (#9668/#9709), sanitize error responses codebase-wide (#9312), and collapse duplicate packages (#9794/#9859). This engine proves the rest of the codebase correct — it must itself be wired, tested, trustworthy. 7 members.

**U4 #9922 — api-contract.** Close the frontend↔backend contract: make the wiring audit blocking + accurate (#9864), mount-or-retire orphaned routers (#9900/#9863), and give backend-only features a reachable UI consumer (#9890/#9891/#9892). Most of the original #9851 drift already landed via the LLC ship — **rescope #9851 to the listed remainder**. #9863 is needs-human-decision. 7 members; gated on U3.

**U5 #9923 — llc-module.** Take LLC from "wired + e2e-proven" (shipped in #9902) to feature-complete: the flagged-off backends (backlog-reorder, suggest-AC, per-agent budget #9901), the frontend spine (#9627/#9628/#9020), new adapters (#9008/#9033/#9034/#9625), token-budget mode (#8997), and the LLC-internal dedup refactors (#9839–#9844, #9909). **Verify #9861 against LLC_SHIP_REPORT and rescope** — context plumbing + org-chart endpoint already shipped; remainder is backlog-reorder/suggest-AC/org-chart enrichment. 18 members; depends on U1 #9793 + U2 #9899.

**U6 #9924 — test-infra.** Green the CI baseline and make the harness trustworthy: clear the flake8/autoflake/vue-tsc red classes (#9524/#9484/#8737/#9724), the frontend-test + FontAwesome + hardened-smoke failures (#9693/#9697/#9663), the namespace fragility (#9907 — already captures the sweep's report-prose), and the missing unit coverage. A red baseline masks regressions for every other umbrella — clear early. 11 members, fully parallelizable.

**U7 #9925 — transcriber.** Land the transcriber cleanly: first resolve the parallel-dev merge conflicts + feature-matrix decision (#9664, needs-human-decision) and the 23-commit branch (#9612), then the security trio (#9214/#9215/#9216) and code-quality follow-ups (#9202/#9205/#9207/#9462/#9466/#9513). 11 members; soft edge on U4's transcripts-router decision (#9863/#9900).

**U8 #9926 — docs-positioning.** Finish docs & licensing positioning: complete the Apache-2.0 relicense epic (#9826, linked not absorbed — third-party notices #9791, header enforcement #9840, dedup'd funding copy #9846), re-apply lost orphan-wiring (#9711), refresh the stale CHANGELOG (#9870), and document canonical composables/fixtures/helpers (#9866–#9869). **LICENSE/NOTICE/SPDX are READ-ONLY in triage** — owner does the license text under the epic. 10 members, parallelizable.

**U9 #9927 — governance.** Make process automatic: PR↔issue linking (#9464), branch auto-delete + pruning (#9917 durable / #9911 one-time backfill), session-lifecycle adoption (#9918), and supply-chain security (#9857 shell-quote, #9284 vega — verify, may already be fixed). The rails that keep every umbrella from drifting. 6 members (2 filed by triage), parallelizable.

**U10 #9928 — integrations-plugins.** Grow the integration surface via plugins: connectors (Drive/OneDrive/GitLab #9003/#9004/#9011), channels (Telegram/WhatsApp #9006/#9007), provider (Bedrock #9010), search (SearXNG/Brave #9022/#9023), media (#9016). **Land #9019 first** (connector OAuth → secrets-management) — it's the architecture gate for the OAuth connectors. 10 members, otherwise independent/parallel.

**U11 #9929 — product-features.** Ship the feature backlog that isn't a platform subsystem: reasoning-effort family (#9017/#9460/#9471/#9531/#9468), chat UX (#8987/#8996/#8999/#9018/#9463), workflow builder (#9036/#9037), analytics (#9024), voice (#9025/#8977), theme (#8988), retention (#8995), entity anchors (#9479). 18 members; gated on U4 contract; group by sub-cluster for dispatch.

**U12 #9930 — enterprise-auth.** Deliver SSO/OIDC federation (#8994 — Okta/Azure AD/Google) + its hardening: callback allowlist (#9500), client-secret encryption (#9501), encrypted-credential tests (#9685), rate-limit test fix (#9611), migration docs (#9687), Telegram webhook-secret encryption (#9651). **Serial tail of the critical path — blocked on U2 #9759 → RBAC.** Surface the SSO provider-matrix + rotation-policy design to the owner before build. 7 members.

**U13 #9931 — codebase-recovery.** Recover work lost to the closed-unmerged PR episodes: audit the May-17 preserve() batch of 141 PRs (#9655) and Jun 1–5 features missed in the first pass (#9656), and correctly recreate PR #9538/issue-9035 (#9545). Each recovered feature that proves valuable becomes its own issue routed to the right umbrella (keep/discard is a per-find human decision). 3 members, investigative/parallel.

---

## Method notes
- Source: `gh issue list --state open` (124 → 122 after closes) + `gh pr list` (0 open) + the four prior reports
  (BUG_SWEEP / WIRING_AUDIT / LLC_SHIP / DEDUP), all cross-referenced.
- Every open issue is placed in exactly one umbrella (122/122). Member task-lists in the
  umbrella issues create GitHub tracking links automatically.
- Active-worktree issues (#9489 `pr-9630`) are **linked, not reassigned**.
- Close-with-evidence used **only** for #9914/#9915 (cited commit `4d6b77495`).
