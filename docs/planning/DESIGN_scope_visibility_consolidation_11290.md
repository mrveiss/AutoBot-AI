# Design: Consolidate scope/visibility/grant stacks into one canonical model (#11290)

> Status: **DRAFT for owner review** — no code changes accompany this doc. Security-critical
> (secrets authz + knowledge visibility). Per the #11290 decision, a written migration design is
> required before any consolidation code lands.

## 1. Problem — four parallel scope/visibility stacks

| Concern | Impl A (secrets) | Impl B (knowledge) | Impl C (new, #11277) |
|---|---|---|---|
| Scope enum | `SecretScope` (`models/secret.py:25`) | `VisibilityLevel` (`knowledge/ownership.py:36`) | `ScopeLevel` (`autobot_shared/scoping/scope_level.py:10`) |
| Decision fn | `services/secrets_authz.py:78` `authorize(facts, action, vault)` | `OwnershipManager.check_access()` + `_check_visibility_grants()` + `filter_accessible_facts()` | `autobot_shared/scoping/visibility.py` `is_visible()` + `services/resource_visibility.py` `can_access()` |
| Principal | `PrincipalFacts` (`secrets_authz.py:51`): user_id, is_admin, team_ids, role_names, **company_roles** (multi-company), granted_permissions, active | — (implicit in OwnershipManager) | `Principal` (`scoping/visibility.py`): user_id, **single company_id**, group_ids |
| Grants | `SecretGrant` (crypto-wrapped DEK per grantee) | knowledge grants (`shared_with`, group) | generic `resource_grants` (resource_type-discriminated) |

Four stacks will drift; `SecretScope`'s own docstring already admits it was "aligned with knowledge VisibilityLevel" (#685) and then diverged.

## 2. Enum member reconciliation

Canonical core = `USER · SHARED · GROUP · ORGANIZATION` (present in all three).

| Canonical `ScopeLevel` | `SecretScope` | `VisibilityLevel` | Notes |
|---|---|---|---|
| `USER` | `USER` | `PRIVATE` | VisibilityLevel calls the owner-only tier `PRIVATE`; same semantics as `USER`. **Alias needed.** |
| `SESSION` | `SESSION` | — | Secrets-only. Keep in canonical (already present in ScopeLevel). |
| `SHARED` | `SHARED` | `SHARED` | identical |
| `GROUP` | `GROUP` | `GROUP` | identical |
| `ORGANIZATION` | `ORGANIZATION` | `ORGANIZATION` | identical |
| `WORKFLOW` (**new**) | `WORKFLOW` | — | Secrets-only (#2153). Add to canonical `ScopeLevel` or keep as a secrets-local extension? **Open Q1.** |
| `SYSTEM` (**new**) | — | `SYSTEM` | Knowledge "platform-wide, all users". Overlaps `ORGANIZATION`? Distinct (cross-org). **Open Q2.** |

**Gaps that block a naive merge:** `PRIVATE`↔`USER` rename, plus `WORKFLOW` and `SYSTEM` which only one stack has.

## 3. Canonical target

`autobot_shared.scoping` is the correct home: `autobot_shared` **must not import backend models**
(`models/secret.py`, `knowledge/ownership.py`), so it cannot depend on `SecretScope`/`VisibilityLevel`
— but they can depend on it. So `ScopeLevel`/`Principal`/`is_visible` become the base, and the two
backend enums are migrated to **derive from / alias** it.

## 4. Migration strategy — incremental, alias-then-derive (NO big-bang)

Each step ships independently with tests; secrets/visibility behavior is asserted unchanged at every step.

1. **Extend canonical enum** — add `WORKFLOW` and `SYSTEM` (or decide per Open Qs) to `ScopeLevel` with an explicit alias map `{PRIVATE: USER}`. Add a `ScopeLevel.from_legacy(value)` normaliser. _Pure addition; no caller change._
2. **Principal unification** — widen `scoping.Principal` to carry what `PrincipalFacts` needs (multi-company `company_roles`, `is_admin`, `role_names`, `granted_permissions`) OR make `PrincipalFacts` a subclass/adapter of `Principal`. Keep `PrincipalFacts` as the richer type; `Principal` becomes its structural subset. _No behavior change._
3. **Route `VisibilityLevel` through canonical** — make `VisibilityLevel` members alias `ScopeLevel` values (or a thin `Enum` whose `.value` maps via `from_legacy`); keep the name for back-comaptible imports. `OwnershipManager.check_access` delegates its scope comparison to `scoping.is_visible`. _Golden-test the existing knowledge access matrix before/after._
4. **Route `SecretScope` through canonical** — same treatment; `secrets_authz.authorize` keeps its vault/DEK logic but derives its scope comparison from the canonical `is_visible`. **This is the highest-risk step** — full secrets authz test matrix (owner/admin/group/org/shared/session/workflow × allow/deny) must pass unchanged first. Do this LAST and alone.
5. **Grant tables** — leave `SecretGrant` (crypto DEK-per-grantee) as-is; it is a different concern (key wrapping). Optionally converge knowledge grants onto the generic `resource_grants` shape in a separate follow-up.

## 5. Risk & guardrails

- A scope-mapping mismatch on secrets/visibility = **data leak / over-broad access**. Therefore: (a) each step gated by an exhaustive allow/deny matrix test that runs before AND after; (b) steps 3 and 4 never combined; (c) `from_legacy`/alias map is the single reconciliation point and is unit-tested member-by-member.
- Back-compat: keep `SecretScope`/`VisibilityLevel` importable (as aliases) throughout — do not break external importers in one PR.

## 6. Open questions for owner

- **Q1.** `WORKFLOW` — promote to canonical `ScopeLevel`, or keep as a secrets-local extension the canonical model doesn't know about?
- **Q2.** `SYSTEM` (knowledge) vs `ORGANIZATION` — are these distinct tiers (cross-org platform-wide vs single-org)? If distinct, canonical needs both; if not, fold `SYSTEM`→`ORGANIZATION`.
- **Q3.** Principal: one rich `Principal` (multi-company `company_roles`) as canonical, or keep two types with an adapter? Multi-company support is the key divergence.
- **Q4.** Sequencing: acceptable to land steps 1–3 (additive + knowledge) first and defer step 4 (secrets) to a dedicated hardening PR with its own review?

## 7. Not in scope

`SLM SENSITIVE_PORTS` vs `autobot_shared/network_constants` (noted in #11251) — separate, and blocked by the two-copy `autobot_shared` split.
