# Umbrella #9930 — Enterprise Auth (SSO/OIDC) — Session Report

**Date:** 2026-06-15 → 2026-06-22
**Outcome:** Phase A + D delivered and merged. C (rotation) blocked on unified-secrets prerequisites. #9930 is out of buildable work.

---

## Reframing (the headline)
#8994 was sized as a greenfield `L` SSO build. Investigation found OIDC federation
(Okta/Entra/Google Workspace), LDAP/AD, SAML, JIT, AES-GCM secret encryption, callback
allowlist, admin CRUD, and frontend were **already ~90% built**. #8994 was reframed into a
**sub-umbrella** of gap-completion work (children #10150–#10158), with five locked decisions
(full build-out; secrets ride on unified store #10088; group→role maps instance roles only;
Phase A first / SCIM v2; sub-umbrella structure).

## Delivered (merged to Dev_new_gui)
| Issue | What | PR |
|---|---|---|
| #10150 | A1 — PKCE (S256) on the OIDC auth-code flow | #10254 |
| #10151 | A2 — RP-initiated logout + JWT `jti` Redis-denylist revocation (HTTP + WS), `POST /api/auth/logout`, frontend wiring | #10426 |
| #10152 | A3 — IdP group→instance-role enforcement (JIT + every login; manual roles preserved; best-effort) | #10426 |
| #10155 / #9687 | E — enterprise SSO admin runbook (provider matrix, group→role, logout, secret migration/rotation) | #10426 |
| #10156 | D3 — provider-health dashboard (audit SSO attempts + `/sso-providers/health` + panel) | #10431 |
| — | Design PRD/spec | #10159 |
| #9611 / #10255 | rate-limit throttle tests + callback host-case fix | #10270 |

## Blocked — C1/C2 secret rotation (#10153/#10154)
Owner directive: **one secrets system with vaults, SLM-as-client of #10088**. Grounding proved the
unified store can't yet serve a system caller. Two #10088 prerequisites filed:
- **#10436** — `/api/v2/secrets` is user-auth-only (`principal()`); SLM (system, no user) can't write
  the System vault. *Also blocks #10088's own first-time-setup LLM-key flow.*
- **#10437** — expose `rewrap_dek` KEK-rotation on `UnifiedSecretsService`/API (only `rotate_value` exists).

Once #10436/#10437 land, C1 (migrate SSO secrets → System vault) + C2 (KEK-rotation + warn-on-stale)
are straightforward SLM-client work. **No second store and no blind bridge were built** (respected the
single-store directive).

## Verified already-implemented → now CLOSED (2026-06-23)
#9500 (callback allowlist) · #9501 (client-secret encryption) · #9651 (telegram webhook) · #9685 (enc-cred tests).
Re-verified against current Dev_new_gui before closing. **Every original #9930 member is now closed.**

## Deferred / spun out
SCIM #10157 (v2) · token-caching+step-up #10158 (v2) · SAML SLO #10281 · cross-service RS256 revocation #10278.
Discoveries: #10255 (fixed), #10284 (sync-redis-await latent bug in sso_service OAuth state).

## Engineering notes
- Every change went through spec + quality review subagents, which caught **6 real bugs masked by
  stub-based tests**: invented `_oauth_states` (state is Redis GETDEL), `/health` route shadowed by
  `/{provider_id}`, sync-Redis-`await` misuse, audit-write 500-ing a successful login, system-role
  group-mapping no-op, and TestClient WS-smoke suite-order pollution (replaced with unit tests).
- `get_redis_client()` defaults **sync**; async code MUST `await get_redis_client(async_client=True)`.
- PRs merge to `Dev_new_gui` (not the default branch) → issues do **not** auto-close.

## Left open for human action
Umbrella #9930, sub-umbrella #8994 (per human-only-close convention).
