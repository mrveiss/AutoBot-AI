# ADR-007: Connector OAuth Token and Credential Storage

## Status

**Status**: Accepted

## Date

**Date**: 2026-05-30

## Context

All incoming connector plugins (Google Drive, OneDrive, Nextcloud, GitLab, etc.)
need to store OAuth2 refresh tokens, app passwords, and API keys. No agreed
storage pattern existed before this ADR.

The current connector API (`knowledge_connectors.py`) accepts a `config` dict and
persists it verbatim into Redis under `connector:{connector_id}`. This means:

- **Plaintext credentials in Redis** — refresh tokens and client secrets are
  readable by any process with access to the knowledge Redis database.
- **No audit trail** — nothing records who read or rotated a credential.
- **No revocation lifecycle** — deleting a connector leaves orphan credentials
  with no cleanup hook.
- **No cross-user isolation contract** — nothing prevents a credential lookup
  from crossing user boundaries.

AutoBot already has two encrypted secret stores:

| Store | File | Key derivation | Scope |
|-------|------|---------------|-------|
| `SecretsService` | `autobot-backend/services/secrets_service.py` | Fernet (AUTOBOT_SECRETS_KEY) | user / session / organization |
| `LLCSecret` | `autobot-backend/llc/services/secret.py` | HKDF-SHA256 (LLC_SECRET_MASTER_KEY) | company |

New connectors MUST route sensitive credentials through `SecretsService`.

## Decision

### 1. Config vs. Credential Separation

`ConnectorConfig` is split into two logical parts:

| Layer | Stored in | Contains |
|-------|-----------|---------|
| Non-sensitive config | Redis (`connector:{id}`) | `token_url`, `scopes`, `header_name`, `client_id` |
| Sensitive credentials | SecretsService (Fernet-encrypted SQLite) | `token`, `key`, `password`, `client_secret`, `refresh_token` |

`ConnectorConfig` gains one new field: `secret_id: str | None = None`.
Sensitive credential fields are stripped from `ConnectorConfig.config` at write
time. The `secret_id` is stored in their place and used to reconstruct the full
config at runtime.

### 2. Sensitive Field Registry

Each auth dataclass in `autobot_shared/auth/connector_auth.py` declares which
fields are sensitive via a `__sensitive_fields__` class attribute:

```python
@dataclass
class OAuthRefreshAuth:
    client_id: str               # non-sensitive
    client_secret: str           # SENSITIVE
    refresh_token: str           # SENSITIVE
    token_url: str               # non-sensitive
    scopes: List[str]            # non-sensitive

    __sensitive_fields__: ClassVar[frozenset] = frozenset({"client_secret", "refresh_token"})

@dataclass
class BearerAuth:
    token: str                   # SENSITIVE

    __sensitive_fields__: ClassVar[frozenset] = frozenset({"token"})

@dataclass
class ApiKeyAuth:
    key: str                     # SENSITIVE
    header: str = "X-Api-Key"   # non-sensitive

    __sensitive_fields__: ClassVar[frozenset] = frozenset({"key"})

@dataclass
class BasicAuth:
    username: str                # non-sensitive
    password: str                # SENSITIVE

    __sensitive_fields__: ClassVar[frozenset] = frozenset({"password"})
```

The `ConnectorCredentialStore` uses this set to split incoming config dicts and
to reconstruct them at runtime.

### 3. `ConnectorCredentialStore` — the Integration Shim

A new module `autobot-backend/knowledge/connectors/credential_store.py` provides:

```python
class ConnectorCredentialStore:
    """Bridges ConnectorConfig ↔ SecretsService for credential isolation.

    All methods are async-safe; the underlying SecretsService calls are
    synchronous but are run in a thread executor to avoid blocking the event loop.
    """

    def __init__(self, secrets_service: SecretsService) -> None: ...

    async def store(
        self,
        connector_id: str,
        owner_id: str,
        auth_cls: type,
        config: dict,
    ) -> tuple[str, dict]:
        """Extract sensitive fields from config, store them encrypted.

        Returns (secret_id, sanitized_config) where sanitized_config has
        sensitive fields removed.  Raises ValueError when auth_cls has no
        __sensitive_fields__.
        """

    async def load(
        self,
        secret_id: str,
        sanitized_config: dict,
        auth_cls: type,
        owner_id: str,
    ) -> dict:
        """Reconstruct full config by merging decrypted credentials back in.

        Raises PermissionError when owner_id does not match the stored secret.
        Raises LookupError when secret_id is not found or has expired.
        """

    async def rotate(
        self,
        secret_id: str,
        new_credentials: dict,
        owner_id: str,
    ) -> None:
        """Replace the stored secret value with new_credentials in-place."""

    async def revoke(self, secret_id: str, owner_id: str) -> None:
        """Delete the secret. Called on connector delete."""
```

### 4. Secret Naming and Typing

```
name:  connector:{connector_id}:auth
type:  connector_oauth_token  (OAuthRefreshAuth)
       connector_api_key      (ApiKeyAuth / BearerAuth)
       connector_password     (BasicAuth)
scope: user
```

`expiry`: `None` by default (long-lived refresh tokens). Connectors that work
with short-lived access tokens set `expires_at` explicitly on each `rotate()`.

### 5. API Layer Changes

**POST /knowledge_base/connectors** (create):
1. Validate config against auth schema (existing).
2. Call `credential_store.store(connector_id, user_id, auth_cls, config)`
   → `(secret_id, sanitized_config)`.
3. Set `cfg.config = sanitized_config` and `cfg.secret_id = secret_id`.
4. Persist `cfg` to Redis (no sensitive fields in Redis).

**GET /knowledge_base/connectors/{id}** (read):
- `_cfg_to_dict()` MUST NOT include `secret_id` in the public response.
- Sensitive fields are never re-serialized into any GET response.

**PUT /knowledge_base/connectors/{id}** (update):
- If the request includes any sensitive field for the declared auth type:
  call `credential_store.rotate(cfg.secret_id, new_creds, user_id)`.
- Otherwise update only non-sensitive config in Redis.

**DELETE /knowledge_base/connectors/{id}**:
- Call `credential_store.revoke(cfg.secret_id, user_id)` before removing
  the Redis key. Log a warning (never raise) on revoke failure to avoid
  blocking the delete.

**Connector invocation** (`test_connection()` / `sync()`):
```python
full_config = await credential_store.load(
    cfg.secret_id, cfg.config, auth_cls, user_id
)
instance = ConnectorRegistry.build(cfg.connector_type, full_config)
await instance.test_connection()
# full_config is never written back to Redis
```

### 6. Cross-User Isolation

`SecretsService.get_secret()` returns `None` when `owner_id` does not match
the stored secret's `created_by`. `ConnectorCredentialStore.load()` converts
that into a `PermissionError`, which surfaces as HTTP 403 at the API layer.

Connectors that belong to an organization-shared config (future work) use
`scope = "organization"` and omit per-user ownership checks — this is an
explicit opt-in, not the default.

### 7. Rotation and Revocation Lifecycle

| Event | Action |
|-------|--------|
| Connector deleted | `revoke()` — secret deleted, Redis key removed |
| OAuth token refresh (background) | `rotate()` — update secret in-place |
| User re-authorizes via OAuth flow | `rotate()` with the new token set |
| User account deleted | `SecretsService` cleanup scoped by `owner_id` |
| Secret expired (`expires_at` reached) | `load()` raises `LookupError` → connector status set to `auth_expired`; UI prompts re-auth |

### 8. Migration for Existing Connectors

A one-time migration script (`scripts/migrate_connector_credentials.py`) will:

1. Read every `connector:*` key from Redis.
2. For each config dict, identify the declared auth type.
3. Extract sensitive fields, call `credential_store.store()`.
4. Write `secret_id` back to the Redis key and clear sensitive fields.
5. Log every migrated connector at INFO; log failures at ERROR without aborting.

The migration is idempotent: connectors whose `secret_id` is already set are skipped.

## Alternatives Considered

1. **Encrypt sensitive fields in Redis** — simpler but still keeps credentials in
   Redis, complicates key rotation, offers no audit trail, and duplicates SecretsService.

2. **Per-user vault (HashiCorp Vault / AWS Secrets Manager)** — stronger
   guarantees but introduces an external dependency that conflicts with the
   self-hosted deployment model.

3. **Extend LLCSecret for connector credentials** — company-scoped secrets are
   the right layer for LLC-owned connectors (future), but user-owned connectors
   should use user-scoped SecretsService entries. Mixing the two into LLCSecret
   would conflate user and company ownership.

## Consequences

### Positive

- Credentials are encrypted at rest; never appear in Redis or any API response.
- Full audit log on every read, write, rotate, and revoke via SecretsService.
- Revocation is atomic: delete the secret, connector immediately deactivates on
  the next invocation.
- Cross-user isolation is guaranteed at the storage layer, not just the API layer.
- Pattern is reusable for every future connector auth type — just add
  `__sensitive_fields__` to the dataclass.

### Negative

- Two reads per connector invocation (Redis config + SecretsService decrypt).
  Acceptable at current scale; a caching layer can be added later if needed.
- SQLite write serialization under high concurrency — tracked separately
  in the PostgreSQL migration backlog.
- Migration script required for connectors created before this ADR is deployed.

### Neutral

- `ConnectorConfig.secret_id` is an optional field; connectors without auth
  (`tier = 0`) leave it `None` and incur zero overhead.

## Implementation Notes

### Key Files

- `autobot-backend/services/secrets_service.py` — SecretsService (storage layer)
- `autobot_shared/auth/connector_auth.py` — add `__sensitive_fields__` to each dataclass
- `autobot-backend/knowledge/connectors/models.py` — add `secret_id: str | None = None` to `ConnectorConfig`
- `autobot-backend/knowledge/connectors/credential_store.py` — **new**: `ConnectorCredentialStore`
- `autobot-backend/api/knowledge_connectors.py` — wire `ConnectorCredentialStore` into CRUD handlers
- `scripts/migrate_connector_credentials.py` — **new**: one-time migration

### Code Examples

```python
# Creating a connector with OAuth credentials
from knowledge.connectors.credential_store import get_credential_store

store = get_credential_store()  # singleton backed by SecretsService

secret_id, safe_config = await store.store(
    connector_id=str(cfg.connector_id),
    owner_id=current_user_id,
    auth_cls=OAuthRefreshAuth,
    config={
        "client_id": "abc",
        "client_secret": "supersecret",   # extracted + encrypted
        "refresh_token": "tok_xyz",        # extracted + encrypted
        "token_url": "https://oauth2.googleapis.com/token",
        "scopes": ["https://www.googleapis.com/auth/drive.readonly"],
    },
)
# safe_config == {"client_id": "abc", "token_url": "...", "scopes": [...]}
# secret_id   == "a7b3c9d1-..."

cfg.config = safe_config
cfg.secret_id = secret_id


# Using the connector at runtime
full_config = await store.load(cfg.secret_id, cfg.config, OAuthRefreshAuth, user_id)
instance = GoogleDriveConnector(ConnectorConfig(..., config=full_config))
await instance.sync()


# Rotating after a background token refresh
await store.rotate(cfg.secret_id, {"refresh_token": "tok_new"}, user_id)


# Deleting a connector
await store.revoke(cfg.secret_id, user_id)
```

## OAuth Authorization-Code Flow and Auto-Refresh (GH#9019 extension)

The original ADR covered credential *storage*. The connector group also needs a
generic way to *obtain* OAuth tokens (so users click "Connect", not paste a
token) and to *keep them valid* (refresh short-lived access tokens). These are
provider-agnostic and live at the gate, not in each connector.

### 9. Authorization-code + PKCE flow

`knowledge/connectors/oauth_flow.py` holds a small provider registry
(`google`, `microsoft`, `gitlab`) plus pure helpers: PKCE (S256) generation,
authorize-URL construction, code→token exchange, and refresh-token→access-token
refresh. OAuth *application* credentials (`client_id`/`client_secret`) are
operator-registered via `config.auth.{provider}_oauth_client_*`; a provider's
flow is disabled until its credentials are set.

Two endpoints (`api/knowledge_connector_oauth.py`):

| Endpoint | Auth | Behaviour |
|----------|------|-----------|
| `POST /knowledge_base/connectors/oauth/{provider}/authorize` | user session | Mints CSRF `state` + PKCE verifier, stores them in the knowledge Redis (`connector:oauth:state:{state}`, 600 s TTL), returns the provider authorization URL. |
| `GET /knowledge_base/connectors/oauth/callback` | single-use `state` | Reached by the provider's browser redirect. Validates+consumes `state` (GETDEL), exchanges the code for tokens, stores them via `store_oauth()`, returns an HTML page that `postMessage`s the `secret_id` back to the opener and self-closes. |

`redirect_uri` hosts are validated against the existing
`AUTOBOT_SSO_CALLBACK_HOSTS` allowlist (HTTPS enforced when
`AUTOBOT_ENFORCE_HTTPS_CALLBACKS`).

Security properties of the callback:

- **CSRF / token-attachment defense** — `authorize` sets an HttpOnly,
  SameSite=Lax, path-scoped cookie holding the `state`; the callback requires
  that cookie to match the `state` query param *before* consuming it. This
  binds the browser that completes the flow to the one that started it, so an
  attacker cannot graft their own authorization onto a victim's session.
- **Single-use** — the state is consumed with Redis `GETDEL`; the cookie is
  cleared on every result.
- **XSS-safe result page** — the only attacker-influenced value (`error` from
  the provider) is HTML-escaped, and the embedded JSON is JS-escaped
  (`<`, `>`, `&`, U+2028/U+2029) so nothing can break out of the `<script>`.
- The callback is authorized by the cookie-bound `state`, not a bearer session
  — correct for a top-level provider redirect that carries no `Authorization`
  header.

### 10. Auto-refresh resolver

`ConnectorCredentialStore` gains two methods:

- `store_oauth(...)` — persist a self-contained bundle (access + refresh token,
  client app creds, token endpoint, `access_token_expires_at`) as a
  `connector_oauth_token` secret. The **secret's** `expires_at` stays `None`
  (long-lived refresh token); access-token expiry lives inside the bundle so an
  expired access token never makes the secret vanish.
- `get_access_token(secret_id, owner_id)` — return a valid access token,
  refreshing + rotating the secret in place when it is within
  `ACCESS_TOKEN_REFRESH_SKEW_SECONDS` of expiry. Honors refresh-token rotation
  (e.g. GitLab). Raises `LookupError` when re-auth is required (no refresh
  token), `PermissionError` on owner mismatch.

Connectors call `get_access_token()` to obtain a bearer token at sync time;
none of them handle refresh themselves.

### 11. Frontend "Connect" building block

`autobot-frontend/.../ConnectorOAuthButton.vue` is a reusable launcher:
`KnowledgeRepository.startConnectorOAuth()` → open the authorize URL in a popup
→ receive the callback's `postMessage` (origin-checked) → emit `connected` with
the `secret_id`. Each connector issue (#9003/#9004/#9011) drops this button into
its provider-specific config step; the gate does not surface connector types in
the create wizard.

## Related ADRs

- [ADR-002](002-redis-database-separation.md) — Redis database separation
  (knowledge DB is distinct from main DB; connector configs live in knowledge DB)

## Implementation Issues

- **GH#9019 / MVA-1717** — This ADR (prerequisite)
- Scaffolding implementation: `ConnectorCredentialStore` + API wiring (child of MVA-1717)
- Prerequisite for: GH#9003 (Google Drive), GH#9004 (OneDrive), GH#9011 (GitLab)

---

**Author**: mrveiss
**Copyright**: © 2026 mrveiss
