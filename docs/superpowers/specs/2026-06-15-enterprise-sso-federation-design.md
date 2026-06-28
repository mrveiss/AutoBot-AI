# Enterprise SSO/OIDC Federation — full build-out (#8994)

> Spec / PRD for GitHub issue [#8994](https://github.com/mrveiss/AutoBot-AI/issues/8994),
> member of umbrella [#9930](https://github.com/mrveiss/AutoBot-AI/issues/9930) (enterprise-auth).
> Status: **design — awaiting sign-off.** No code until the task tree is confirmed.
> Date: 2026-06-15.

## 1. Context & problem

The umbrella sized #8994 as an `L` greenfield "SSO/OIDC federation" build. Investigation shows it is
**~90% already implemented** in `autobot-slm-backend`:

- OAuth2/OIDC auth-code flow for **Okta**, **Microsoft Entra ID (Azure AD)**, **Google Workspace**
  (endpoint templates, token exchange, userinfo) — `user_management/services/sso_service.py`.
- LDAP/Active Directory bind+search (RFC-4515 escaped), SAML 2.0 (AuthnRequest/ACS/assertion).
- JIT user provisioning, org scoping, per-IP/per-username rate limiting.
- AES-256-GCM secret encryption in `system_secrets` (`autobot_shared/field_encryption.py`,
  `user_management/services/sso_secrets.py`).
- Callback-URL allowlist (SSRF/CRLF, MVA-3542), replay-safe Redis OAuth state (atomic GETDEL).
- Admin CRUD (`api/sso.py`, `Permission.SECURITY_MANAGE`) + frontend `SSOSettings.vue`,
  `SSOCallbackView.vue`, `useSsoApi.ts`.

So #8994 is **not** a from-scratch build. It is: (a) close the enterprise-grade gaps the current
implementation lacks, (b) sign off the two flagged human-decisions (provider matrix, rotation policy),
and (c) reconcile with the unified-secrets umbrella #10088.

### Gaps the current implementation lacks
1. **group→role enforcement** — `group_mapping` JSONB is stored but never applied during JIT/login.
2. **PKCE** — auth-code flow has no S256 proof-key.
3. **Secret rotation** — encryption-at-rest exists, but no rotation mechanism or policy.
4. **IdP-initiated logout / session revocation** — no RP-initiated logout or SAML SLO.
5. (deferred) SCIM inbound provisioning, token caching, step-up auth, device flow.

## 2. Decisions (locked with owner, 2026-06-15)

| # | Decision | Choice |
|---|---|---|
| D1 | Overall scope | **Full enterprise build-out** — #8994 becomes a sub-umbrella |
| D2 | Where SSO secrets + rotation live | **Build on unified-secrets #10088** (vault + envelope crypto); rotation = envelope `rewrap_dek`. Not a throwaway rotation layer. |
| D3 | IdP group→role mapping authority | **Instance RBAC roles only** (`user_management` roles/`user_roles`). LLC `MembershipRole` out of scope. |
| D4 | v1 vs v2 phasing | **Ship Phase A (standards) first; defer SCIM (Phase B) to v2.** |
| D5 | GitHub recording | **Convert #8994 → sub-umbrella + child issues** under #9930. |

## 3. Supported-provider matrix *(flagged human-decision #1 — D1 resolved)*

| Tier | Providers | Protocol | Action in this umbrella |
|---|---|---|---|
| **Certified** (e2e-tested, documented, PKCE) | Okta · Microsoft Entra ID (Azure AD) · Google Workspace | OIDC auth-code + PKCE | add PKCE (A1) + e2e verification + docs (E) |
| **Supported** | Generic OIDC (any compliant IdP) · SAML 2.0 · LDAP/Active Directory | OIDC / SAML / LDAP | already present; covered by hardening + docs |
| **Social (non-enterprise)** | GitHub · Facebook · Google consumer | OAuth2 | unchanged, not part of the enterprise tier |

## 4. Secret-rotation policy *(flagged human-decision #2 — D2 resolved)*

- SSO client secrets are stored in the unified-secrets **System/SSO vault** (#10088): value sealed under a
  per-secret DEK, the DEK wrapped by the vault KEK.
- **Rotation = two independent operations:**
  - **KEK rotation** — envelope `rewrap_dek` rewraps the DEK under a new KEK; payload is **not** re-encrypted.
  - **Value rotation** — when the operator rotates the secret at the IdP, the new value is re-sealed
    under a fresh DEK.
- **Cadence**: default **90-day advisory**, **warn-on-stale — never hard-expire** (a forced expiry that
  locks out SSO is worse than a stale secret). Admin-initiated rotation always available.
- **Audit**: every rotation (who, which provider/secret, KEK-vs-value, when) is logged.

### 4.1 Cross-backend boundary — **RESOLVED: Option A (X-Internal-API-Key) (#10492)**

The unified store and `UnifiedSecretsService` live in **autobot-backend**
(`services/unified_secrets_service.py`, `autobot_shared/secrets_envelope.py`), while SSO (and LLM
config) live in **autobot-slm-backend** (the control plane). Phase C crosses a backend boundary via
HTTP; the SLM is a client of the unified-secrets API.

**Decision: Option A — shared `X-Internal-API-Key` → synthetic `service_id = "slm-backend"`.**

- `autobot-backend/api/unified_secrets.py` `service_principal` dependency now accepts the existing
  `X-Internal-API-Key` header (validated against `ssot_config.misc.internal_api_key`) in addition to
  the pre-existing HMAC `X-Service-*` path. Either path yields a `service_id` string; the
  `_require_system_vault` double-fence continues to enforce System-vault-only scoping.
- `autobot-slm-backend/user_management/services/unified_vault_client.py` `_auth_headers()` now prefers
  `X-Internal-API-Key` when `AUTOBOT_INTERNAL_API_KEY` is set. `is_configured()` gates on either
  credential. No `SLM_SERVICE_KEY` provisioning is required on standard deployments.
- **Trade-off**: coarser identity than per-service HMAC — all callers with the shared key appear as
  `"slm-backend"`. Acceptable for v1: the key is already a privileged secret; System-vault scoping
  provides the authorization fence. Per-service HMAC keys remain available as an upgrade path.

## 5. Phased task tree (sub-umbrella under #9930)

### Phase A — Standards hardening *(v1; independent of #10088; ships now)*
- **A1 — PKCE (S256)** on the OIDC auth-code flow: generate `code_verifier`/`code_challenge`, persist the
  verifier in Redis alongside the existing OAuth `state`, send `code_challenge` on authorize and
  `code_verifier` on token exchange. `autobot-slm-backend/user_management/services/sso_service.py`,
  `api/sso_auth.py`.
- **A2 — RP-initiated logout + session/token revocation**: OIDC `end_session_endpoint` logout and SAML
  SLO; revoke the local session/token on logout. Frontend logout wires to it.
- **A3 — group→role enforcement**: apply `group_mapping` to **instance roles** during JIT **and**
  re-sync on every login (add/remove roles to match current IdP groups). Reconciliation is idempotent;
  removal of an IdP group removes the mapped role.

### Phase C — Secret rotation *(v1; depends on #10088 SecretsService — landed in #10111/#10134, verify first)*
- **C1 — migrate SSO secrets into the #10088 vault**: move existing `system_secrets` SSO entries into the
  System/SSO vault; settle the cross-backend integration surface (§4.1) first. Backward-compatible read
  path during rollout.
- **C2 — rotation mechanism**: `rewrap_dek` (KEK) + value re-seal, admin UI control, warn-on-stale
  surfacing in `SSOSettings.vue`, audit log.

### Phase E — Docs *(v1)*
- Provider matrix (§3), rotation policy (§4), admin runbook (configure each certified IdP, rotate a
  secret, read the audit). **Absorbs #9687** (SSO secret-migration docs).

### Phase D — Operational polish *(v1, optional / lower priority)*
- **D3 — provider-health dashboard** (failed-auth visibility). D1 token caching and D2 step-up auth are
  **deferred** (YAGNI for v1) → filed as follow-up issues, not built now.

### Phase B — SCIM 2.0 provisioning *(v2 — deferred per D4)*
- B1 SCIM inbound `/scim/v2` Users (create/update/**deactivate**), bearer-token auth.
- B2 SCIM Groups → instance-role mapping + deprovisioning on IdP removal.
- Filed as a v2 follow-up sub-umbrella; not part of v1.

## 6. Reconciliation with existing #9930 members

| #9930 member | Disposition |
|---|---|
| #9500 callback-URL allowlist | **Already implemented** (`_build_callback_url`, MVA-3542) → verify & close, not rebuild |
| #9501 SSO client-secret encryption | **Already implemented** (AES-256-GCM in `system_secrets`) → superseded by Phase C migration; verify & close |
| #9685 encrypted-creds tests | fold into Phase C verification |
| #9611 rate-limit test mock fix | independent `S`; do any time (not gated on this umbrella) |
| #9687 secret-migration docs | fold into Phase E |
| #9651 telegram webhook encryption | unrelated to SSO; remains a standalone `S` in #9930 |

## 7. Dependencies & ordering

```
#10088 SecretsService (LANDED #10111/#10134) ──> Phase C (C1 ─> C2)
Phase A (A1, A2, A3)  ── independent ──> ships in parallel with C
Phase E (docs)        ── after A + C feature-complete
Phase D3              ── optional, after A
Phase B (SCIM)        ── v2, separate follow-up
```

- Critical edge: **C is gated on #10088** (now satisfied — verify the service surface before C1).
- A1/A2/A3 have **no** cross-dependency and can be three parallel PRs.

## 8. Testing strategy

- **A1 PKCE**: unit — verifier/challenge generation + Redis round-trip; integration — token exchange
  rejects a missing/mismatched verifier.
- **A2 logout**: session revoked after RP logout; token no longer authenticates.
- **A3 group→role**: JIT assigns mapped roles; login re-sync adds/removes roles; idempotent; unmapped
  groups grant nothing.
- **C1/C2**: secret round-trips through the vault; `rewrap_dek` rotates KEK without changing plaintext;
  value rotation re-seals; warn-on-stale fires past cadence; audit row written. (Absorbs #9685.)
- Reuse existing `tests/services/test_sso_*.py`, `tests/api/test_sso_auth.py`.
- Gates: wiring audit (frontend↔backend SSO endpoints), duplication guard, smoke-test.

## 9. Out of scope (filed as follow-ups, not built here)
- SCIM (→ v2 sub-umbrella), token caching (D1), step-up auth (D2), OAuth device flow.
- LLC `MembershipRole` mapping from IdP groups (D3 decision — instance-only for v1).

## 10. Open items to confirm during planning
- §4.1 cross-backend integration surface with the #10088 owner (SLM-as-client vs shared primitives).
- Whether #9500/#9501 are closed as "verified-done" or folded as verification subtasks of this umbrella.
