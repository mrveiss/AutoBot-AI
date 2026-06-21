# Enterprise SSO / OIDC — Administrator Runbook

> Operator guide for AutoBot's enterprise identity federation (SLM control plane).
> Covers the supported-provider matrix, per-IdP configuration, group→role mapping,
> logout/revocation behavior, and secret storage/migration/rotation.
> Sub-umbrella [#8994](https://github.com/mrveiss/AutoBot-AI/issues/8994); design spec:
> `docs/superpowers/specs/2026-06-15-enterprise-sso-federation-design.md`.

## 1. Supported-provider matrix

| Tier | Providers | Protocol | Notes |
|---|---|---|---|
| **Certified** (tested end-to-end, documented, PKCE) | Okta · Microsoft Entra ID (Azure AD) · Google Workspace | OIDC authorization-code + **PKCE (S256)** | Recommended for production. |
| **Supported** | Generic OIDC (any spec-compliant IdP) · SAML 2.0 · LDAP / Active Directory | OIDC / SAML / LDAP | Functional; SAML **Single Logout** is tracked separately ([#10281](https://github.com/mrveiss/AutoBot-AI/issues/10281)). |
| **Social (non-enterprise)** | GitHub · Facebook · Google consumer | OAuth2 | Not part of the enterprise tier; unchanged. |

All OIDC logins use **PKCE (S256)** — the authorization-code flow is bound to a
per-login verifier, mitigating code-interception.

## 2. Configuring a provider

Providers are managed by an admin (permission `SECURITY_MANAGE`) via the SSO
admin UI (`Settings → Admin → SSO`) or the API under `/sso-providers`. Use
`GET /sso-providers/provider-templates/{provider_type}?domain=<your-domain>` to
pre-fill the standard endpoints.

### 2.1 Okta (OIDC)
- **client_id / client_secret**: from your Okta app integration (Web / OIDC).
- Endpoints (auto-filled from template): `authorize_url`, `token_url`,
  `userinfo_url`, `end_session_endpoint` (`{domain}/oauth2/v1/logout`).
- **scope**: `openid email profile groups`.
- Redirect/callback URI to register in Okta: `<SLM_EXTERNAL_URL>/api/auth/sso/callback`.

### 2.2 Microsoft Entra ID (Azure AD) (OIDC)
- **client_id / client_secret**: from the App Registration.
- Endpoints use `login.microsoftonline.com/<tenant>/...`;
  `end_session_endpoint` = `.../oauth2/v2.0/logout`.
- Grant the **GroupMember.Read.All** (or emit `groups` claim) so group→role
  mapping receives group IDs/names.

### 2.3 Google Workspace (OIDC)
- **client_id / client_secret**: from a Google Cloud OAuth client.
- Google does **not** implement an OIDC RP `end_session_endpoint`; logout revokes
  the local AutoBot session only (the Google session is not terminated). This is
  expected and noted in the provider template.

### 2.4 Generic OIDC / SAML / LDAP
- **Generic OIDC**: supply all endpoint URLs (including an optional
  `end_session_endpoint`) in the provider config.
- **SAML 2.0**: set `sp_entity_id`, `acs_url`, `idp_metadata_url`. SLO is not yet
  wired ([#10281](https://github.com/mrveiss/AutoBot-AI/issues/10281)).
- **LDAP/AD**: `server_uri`, `bind_dn`, `base_dn`, `user_dn_template`,
  `attribute_mapping`. Group source via `attribute_mapping.groups` (default `memberOf`).

## 3. Group → role mapping

Map IdP groups to **AutoBot instance roles** with the provider's `group_mapping`
(JSONB), shape `{ "<idp_group>": "<autobot_role_name>" }`:

```json
{ "engineering": "developer", "sso-admins": "admin", "finance": "viewer" }
```

Behavior (enforced on **every** login, not just first JIT):
- On login, the user's current IdP groups are reconciled against the mapping.
- Only roles that appear as **values** in `group_mapping` are managed — roles you
  assign manually (outside the mapping) are **never** stripped.
- Adding a user to a mapped IdP group grants the role; removing them revokes it.
- If the IdP does **not** assert a groups claim for a login, no role changes are
  made (avoids accidental mass-revocation when the claim is temporarily absent).
- Role names resolve against org-scoped roles first, falling back to system roles
  (`org_id IS NULL`). Names with no matching role are skipped and logged.
- LLC `MembershipRole` is **out of scope** — group mapping grants instance roles only.

Pre-requisite: request the `groups` scope (OIDC) or configure
`attribute_mapping.groups` (SAML/LDAP) so groups reach AutoBot.

## 4. Logout & session revocation

- **Endpoint**: `POST /api/auth/logout` (authenticated).
- AutoBot SLM issues **stateless HS256 JWTs**. On logout the token's `jti` is
  added to a Redis **denylist** (`slm:jwt:denylist:{jti}`) with a TTL equal to the
  token's remaining lifetime, so the token is rejected server-side on subsequent
  requests (enforced on the async HTTP auth path and WebSocket auth).
- For OIDC providers with an `end_session_endpoint`, the logout response returns a
  `logout_url`; the frontend redirects there for **RP-initiated** IdP logout.
- Logout is resilient: if the revoke call fails, the local session is still cleared.
- **Limitation**: RS256 **authority tokens** minted by autobot-backend cannot be
  revoked by the SLM denylist — cross-service revocation is tracked under
  [#10278](https://github.com/mrveiss/AutoBot-AI/issues/10278) (coordinate with
  auth-unification epic #10193). Keep access-token lifetimes short.

## 5. Secret storage, migration & rotation

### 5.1 Storage (current)
OAuth client secrets and LDAP bind passwords are **encrypted at rest** with
AES-256-GCM and stored in the `system_secrets` table (key scheme
`sso:provider:{id}:{field}`); the provider `config` holds only `{field}_ref`
references — never plaintext. Field encryption uses `AUTOBOT_FIELD_ENCRYPTION_KEY`.

### 5.2 Migrating legacy plaintext secrets (#9687)
If you are upgrading from a build that stored secrets in plaintext config:
1. Ensure `AUTOBOT_FIELD_ENCRYPTION_KEY` is set (the migration fails fast otherwise).
2. Run `autobot-slm-backend/migrations/migrate_sso_secrets_to_system_secret.py`.
   It encrypts each `client_secret`/`bind_password`, writes it to `system_secrets`,
   replaces the config value with a `{field}_ref`, and rolls back on any error.
3. Verify providers still authenticate (`GET /sso-providers/{id}/test` for LDAP).

### 5.3 Rotation policy
- **To rotate a client secret today**: rotate it at the IdP, then update the
  provider via the admin UI / `PATCH /sso-providers/{id}` — the new value is
  re-encrypted into `system_secrets`. No downtime; existing sessions are unaffected.
- **Cadence**: a **90-day advisory** rotation is recommended. AutoBot **warns on
  stale** secrets but does **not** hard-expire them (a forced expiry that locks out
  SSO is worse than a stale secret).
- **Planned**: unified-vault-backed rotation (envelope `rewrap_dek` + value re-seal)
  lands with [#10153](https://github.com/mrveiss/AutoBot-AI/issues/10153) /
  [#10154](https://github.com/mrveiss/AutoBot-AI/issues/10154), building on the
  unified-secrets store ([#10088](https://github.com/mrveiss/AutoBot-AI/issues/10088)).

## 6. Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| Login loops / "invalid state" | Redis unavailable (OAuth state is Redis-backed) | Check Redis; state TTL is 10 min. |
| Roles not applied | `groups` scope/claim missing, or mapped role name not found | Confirm the IdP emits groups; check role names exist (org or system). |
| User keeps access after logout | RS256 authority token (not SLM-issued) | Expected until #10278; shorten token TTL. |
| Google session persists after logout | Google has no OIDC end_session endpoint | Expected; only the AutoBot session is revoked. |
| Secret decryption errors | `AUTOBOT_FIELD_ENCRYPTION_KEY` changed/missing | Restore the key; re-enter secrets if lost. |
