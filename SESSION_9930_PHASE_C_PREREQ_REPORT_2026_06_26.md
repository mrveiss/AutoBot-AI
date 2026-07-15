# Umbrella #9930 — Phase C (SSO secrets → unified vault + rotation) — session report

Span: 2026-06-25 → 2026-06-27. Mission: work umbrella #9930 (enterprise-auth: SSO/OIDC + secret/credential hardening).

## Outcome — Phase C complete; all enterprise-auth members merged to Dev_new_gui

| PR | Scope | State |
|----|-------|-------|
| #10498 | C1 (#10153) + C2 (#10154): SSO client secrets → unified-secrets **System vault** + rotation. Option B per-service HMAC; backward-compatible default-off via `is_configured()` (legacy `SystemSecret` fallback until `SLM_SERVICE_KEY` provisioned); idempotent migration; `slm-backend` added to key-provisioning `SERVICES`. | MERGED |
| #10507 | **Critical** code-review fix: service-auth `POST /api/v2/secrets/system/{id}/rewrap` + `SecretsCoordinator.service_rotate_kek` (KEK rotation was hitting a **user-auth-only** route → 401 under service HMAC). Plus M1–M3 hardenings (migration orphan-dup guard; vault-read logging + missing-`value` guard). | MERGED |
| #10520 | Bandit **B105** false-positive on `_SECRET_TYPE = "sso-credential"` (var name contains "secret"). Unblocked the required `code-quality` check. | MERGED |
| #10529 | CodeQL **clear-text-logging** false-positive in `vault_create` (logged the secret's *name* identifier). | MERGED |

All four verified present on `origin/Dev_new_gui`.

## How the work proceeded

1. Arrived to find the Phase-C unblockers (#10436/#10437 service-vault + KEK rotation; #10458 RBAC vocab) freshly merged. Cleared 3 high-sev CodeQL secret-logging alerts they carried into base (**#10490**, merged) and closed the merged prerequisite issues.
2. Filed **#10492** documenting the §4.1 cross-backend integration surface and recommending **Option B** (per-service HMAC) — the unified store is the crown-jewels secrets vault, so a scoped/revocable/replay-protected SLM identity beats reusing the broad `X-Internal-API-Key`. Found the HMAC infra already shared/tested (`autobot_shared.http_client.sign_request` ↔ `ServiceAuthManager.validate_signature`).
3. Continued the owner's own end-of-day WIP for C1/C2 (snapshot-committed to preserve it first), then verified + completed it. **Verify-don't-trust caught three bugs the stubbed unit tests masked:** audit wrote non-existent `AuditLog` columns (→ reuse `create_audit_log`); store/delete hard-failed when the vault key was unprovisioned (→ legacy fallback); `slm-backend` missing from provisioning lists.
4. A code-reviewer pass on the merged feature caught the **Critical** KEK-rewrap auth-scheme mismatch → fixed in #10507.
5. Cleared two static-analysis false positives (B105, CodeQL) blocking/­degrading the gates → #10520, #10529.

## Remaining open under #9930 — human-gated, intentionally not started

- **#10088** secrets-unification umbrella · **#10157** SCIM 2.0 (v2-deferred) · **#10193** AutoBot+SLM identity unification (+ children #10199–10203).
- Each carries an explicit *PRD-required / no-code-until-sign-off* gate. They are not part of the SSO/secret-hardening deliverable and await owner prioritization.

## Lessons (also in memory)

- Stubbed-client unit tests hide auth-dependency bugs — cross-check client path ↔ backend route `Depends`.
- PRs merged faster than follow-ups landed; squash-merge blinds git to the already-applied diff → recover by branching fresh off merged base and applying only the missing delta.
- PR-link validator (#9464) is branch-name-driven (`issue-<N>` → body must `Closes #<N>`) — name branches after a real issue; file a discovery issue if none exists.
- Bandit B105 / CodeQL clear-text-logging fire on identifier names containing "secret"/on functions that also receive a value — suppress with `# nosec B105 <reason>` or drop the tainted arg from the log.

## Model

Claude Opus 4.8 (1M context).
