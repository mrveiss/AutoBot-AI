# Threat Model — Trust Boundaries by Subsystem

Read this **before** the `secreview` checklist when a diff touches one of these four
subsystems. It exists so a review states the invariant a change breaks instead of
re-deriving the trust model from the implementation.

Scope: what a review checks from a diff alone. Every anchor below is real code — cite it.

## 1. Path validation

**Boundary:** any path string that reached the process from an HTTP body, query
param, filename, or plugin manifest. Everything downstream of the validator is
trusted to be inside a root.

**Canonical enforcement:** [`autobot_shared/security/path_validator.py`](../../autobot_shared/security/path_validator.py)
— `validate_path` (:84) absolute paths · `validate_relative_path` (:145) a segment under a
known base · `resolve_within_sandbox` (:241) the file-management sandbox ·
`require_path_string` (:193) type gate before `Path()` / `os.makedirs`.

**Invariants**

- `validate_path` is never called without an explicit `allowed_roots`. The default
  `_DEFAULT_ALLOWED_ROOTS` (:26) includes `/tmp` — fine for tests, a hole in a request path.
- Decode before resolve: `_canonicalize` (:53) runs `_MAX_DECODE_ROUNDS` unquote passes plus
  NFKC. `realpath` decodes nothing, so a denylist on the raw string is always wrong.
- The containment check is the **sole** authority — `resolved.relative_to(root_resolved)`,
  both sides realpath'd. A new string-level `..` check added "as well" is a smell, not defence.
- The validated string is the string used. Validating `user_path` then opening something
  rebuilt from the original input is a finding.
- `resolve_within_sandbox` forbids **any** `..`, `~`, leading `/`, or
  `SANDBOX_INVALID_PATH_CHARACTERS` (:34) — in-bounds or not. `''`, `'/'`, `'//'` legitimately
  address the sandbox root and return it unchanged (#11823); a diff that makes them raise
  again breaks root listing.

**Known bypass shapes:** double percent-encoding (`%252e%252e`), Unicode confusables
(`﹒﹒`, `‥`), null byte via encoding, symlink pointing out of the root, a `MagicMock`
or arbitrary object stringifying into a creatable tree (#14217).

## 2. Session / chat ownership

**Boundary:** an authenticated user vs. *another* authenticated user's session. This is
not an auth boundary — the caller is logged in — so a missing check reads as a working
endpoint.

**Canonical enforcement:** [`autobot-backend/security/session_ownership.py`](../../autobot-backend/security/session_ownership.py)
— `build_owner_metadata` (:31) the one owner stamper · `validate_session_ownership` (:800)
the one read-side gate · `validate_ownership` (:638).

**Invariants**

- Redis keys are `chat:session:{session_id}` — **not** namespaced by user. Key
  construction is never an ownership check; the metadata comparison is.
- Owner identity is `metadata.owner` = **username**, never a user id. A diff comparing
  against `user_id` is comparing the wrong field.
- Redis is a TTL cache; the session file's `metadata.owner` is the record of truth. An absent
  Redis record means "not cached", never "unowned" — `_owner_when_cache_is_empty` (:565) asks
  disk first and rehydrates **for the real owner, never for the caller** (#14018).
- Undetermined enforcement policy degrades to `DEGRADED_ENFORCEMENT_MODE` (:65) — not to `disabled`,
  not to `disabled`: checks still run and violations are still recorded (#14010). A new
  `except` that returns `"disabled"` is a fail-open.
- Only two legitimate fast-path bypasses exist — `_resolve_fast_paths` (:506): global auth
  disabled, and enforcement explicitly `disabled`. A third one added in a diff is a finding.
- Creating over an existing session id is a 409, identical for "owned by someone else" and
  "no recorded owner" — a 403 on the first would confirm who owns it (#14012).

## 3. Plugin loading

**Boundary:** the install endpoint. Loading executes arbitrary Python by design
([`loader.py`](../../autobot_shared/plugin_sdk/loader.py) — `import_module` (:541), then the
`spec_from_file_location` (:610) fallback). No load-time sandbox exists or is intended.

**Canonical enforcement:** every route in
[`autobot-backend/plugin_manager.py`](../../autobot-backend/plugin_manager.py) carries a
`Depends` on [`auth_middleware.py`](../../autobot-backend/auth_middleware.py)
`check_admin_permission` (:972).
Archive safety lives in [`autobot-backend/archive_safety.py`](../../autobot-backend/archive_safety.py)
— `validate_zip_metadata` (:27), `safe_extract` (:58), `MAX_UPLOAD_BYTES` (:19).

**Invariants**

- A plugin route without `Depends(check_admin_permission)` is remote code execution.
  This is the single highest-severity shape in this subsystem — check it first.
- Extraction goes through `archive_safety`; [`plugin_install.py`](../../autobot-backend/plugin_install.py)
  only re-exports `_validate_zip_metadata` (:125) and `_safe_extract` (:126).
  A local `zf.extractall` reintroduces zip-slip and symlink escape.
- Names match `_NAME_PATTERN` (:35) before any filesystem touch; the target is claimed by
  `_claim_install_target` (:106) via `mkdir(exist_ok=False)`, which — with the per-name
  `_install_locks` — is what makes the collision check TOCTOU-free.
- Git installs: scheme restricted to http(s), `--` before the URL, `protocol.file.allow=never`,
  no submodule recursion, ref matched against `_GIT_REF_PATTERN` (:38), which rejects a leading `-` and any `..`.
  Dropping any one of these is a finding on its own.
- `PluginRegistry._plugins` and `HookRegistry` are process-wide singletons that do not dedupe —
  a load path re-initialising a live plugin double-registers its callbacks (#14000).

## 4. Secrets & credentials

**Boundary:** plaintext lives only inside the store's own methods. Anything crossing out — a
response, a log line, an issue, a PR comment — is already redacted.

**Canonical enforcement:** [`encryption_service.py`](../../autobot-backend/encryption_service.py)
AES-GCM + PBKDF2 for data at rest · [`autobot_shared/field_encryption.py`](../../autobot_shared/field_encryption.py)
`encrypt_field`/`decrypt_field` for single columns ·
[`credential_store.py`](../../autobot-backend/knowledge/connectors/credential_store.py)
`ConnectorCredentialStore` (:178) for connector/OAuth creds, ownership via `_require_owner` (:604) ·
[`auth_middleware.py`](../../autobot-backend/auth_middleware.py) `verify_internal_api_key` (:959)
for service-to-service.

**Invariants**

- No parallel crypto path. A diff introducing its own `Fernet(...)` or `AESGCM(...)` instead
  of calling the store is a finding regardless of whether the primitive is used correctly.
- Secrets compare with `secrets.compare_digest`, never `==`. A missing/`None` credential can
  never match — `verify_internal_api_key` returns `False` when either side is unset.
- Every `ConnectorCredentialStore` read takes `owner_id` and passes `_require_owner`; a new
  method that skips it grants cross-tenant credential read.
- Nothing reaches a log, HTTP error body, or outward artifact without
  [`redaction.py`](../../autobot_shared/security/redaction.py) (`redact_text` (:63) /
  `redact_mapping` (:75)). Exception text counts — `detail=f"...{exc}"` on a credential path leaks.
- Keys come from SSOT config, never a literal. A default value for an encryption key is a
  finding even when production overrides it via env var.

## Cross-cutting

- **Egress:** any new outbound HTTP goes through the guarded fetch —
  [`autobot_shared/security/ssrf_guard.py`](../../autobot_shared/security/ssrf_guard.py)
  `fetch_safe_url` (:305) / `pinned_request_with_redirects` (:230). A bare `aiohttp`/`requests`
  call on a user-influenced URL is SSRF (core rule 8).
- **Refactor fallout** historically outranks new code here: a renamed validator or store with
  call sites left on the old name silently removes the check. Grep the **old** identifier.
