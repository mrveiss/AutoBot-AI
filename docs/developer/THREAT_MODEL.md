# Threat Model — Trust Boundaries by Subsystem

Read this **before** the `secreview` checklist when a diff touches one of these six
subsystems. It exists so a review states the invariant a change breaks instead of
re-deriving the trust model from the implementation.

Scope: what a review checks from a diff alone. Every anchor below is real code — cite it.

## 1. Path validation

**Boundary:** any path string that reached the process from an HTTP body, query
param, filename, or plugin manifest. Everything downstream of the validator is
trusted to be inside a root.

**Canonical enforcement:** [`autobot_shared/security/path_validator.py`](../../autobot_shared/security/path_validator.py)
— `validate_path` (:96) absolute paths · `validate_relative_path` (:157) a segment under a
known base · `resolve_within_sandbox` (:289) the file-management sandbox ·
`require_path_string` (:241) type gate before `Path()` / `os.makedirs`.

**Invariants**
- `validate_path` is never called without an explicit `allowed_roots`. The default `_DEFAULT_ALLOWED_ROOTS` (:34) is `("/opt/autobot",)` — no `/tmp` (#15238): world-writable and shared, so a default including it let an unprivileged local process plant a file for any fallback-taking handler to read back. Prefer `PROJECT_ALLOWED_ROOTS` (:41) — `str(project_root())` — over the default for a request-supplied path scoped to this project.
- Decode before resolve: `_canonicalize` (:65) runs `_MAX_DECODE_ROUNDS` unquote passes plus NFKC. `realpath` decodes nothing, so a denylist on the raw string is always wrong.
- Containment is the **sole** authority — `relative_to`, both sides realpath'd. Pre-resolution refusals (absolute, `..`, drive qualifier) are defence in depth only; replacing it is a smell (#15786).
- The validated string is the string used. Validating `user_path` then opening something rebuilt from the original input is a finding.
- `resolve_within_sandbox` forbids **any** `..`, `~`, leading `/`, or `SANDBOX_INVALID_PATH_CHARACTERS` (:46) — in-bounds or not. `''`, `'/'`, `'//'` legitimately address the sandbox root and return it unchanged (#11823); a diff that makes them raise again breaks root listing.
- Upload **filenames** are their own gate: [`autobot_shared/security/upload_filename_policy.py`](../../autobot_shared/security/upload_filename_policy.py) `is_safe_file(filename, allowed)` / `require_safe_upload` (re-exported by `autobot-backend/security/upload_filename_policy.py`) — a bare name only (no `/`, no `\\`), a per-purpose allow-list (`ALLOWED_EXTENSIONS` documents, `AUDIO_EXTENSIONS`, `IMAGE_EXTENSIONS`, `ZIP_EXTENSIONS`, `TARBALL_EXTENSIONS`), a deny-list by name; every `UploadFile` route reaches it — `repo_tests/upload_routes_call_is_safe_file_guard_19088_test.py` fails on one that does not (#19088) — and a route-local copy is a finding (the conversation copy accepted `a/b.txt` until #18704).

**Known bypass shapes:** double percent-encoding (`%252e%252e`), Unicode confusables (`﹒﹒`, `‥`), null byte via encoding,
symlink pointing out of the root, a `MagicMock` or arbitrary object stringifying into a creatable tree (#14217).

## 2. Session / chat ownership

**Boundary:** an authenticated user vs. *another* authenticated user's session. This is
not an auth boundary — the caller is logged in — so a missing check reads as a working
endpoint.

**Canonical enforcement:** [`autobot-backend/security/session_ownership.py`](../../autobot-backend/security/session_ownership.py)
— `build_owner_metadata` (:44) the one owner stamper · `validate_session_ownership` (:742) the one read-side gate · `validate_ownership` (:580).
Two postures, one validator (#14016): the contract is the docstring of [`security/session_posture.py`](../../autobot-backend/security/session_posture.py). A failed durable owner lookup denies under both and claims nothing: "unknown" is never "unowned" (#14033).

**Invariants**
- Redis keys are `chat:session:{session_id}` — **not** namespaced by user. Key construction is never an ownership check; the metadata comparison is.
- Owner identity is `metadata.owner` = **username**, never a user id. A diff comparing against `user_id` is comparing the wrong field.
- Redis is a TTL cache; the session file's `metadata.owner` is the record of truth. An absent Redis record means "not cached", never "unowned" — [`session_ownership.py`](../../autobot-backend/security/session_ownership.py) `_owner_when_cache_is_empty` (:507) asks disk first and rehydrates **for the real owner, never for the caller** (#14018). Nobody claims an existing session with no owner, by reading or writing: an admin may act on it, anyone else gets the same 404 as a missing session, and nothing is written; an ownerless session is itself a defect. With no session at all, a read gets that 404 and a write creates it and records its owner. Not knowing which of the two it is denies (#20025).
- Undetermined enforcement policy degrades, in [`security/enforcement_mode.py`](../../autobot-backend/security/enforcement_mode.py), to `DEGRADED_ENFORCEMENT_MODE` (:53) and never to `disabled`: checks still run and violations are still recorded (#14010). A new `except` that returns `"disabled"` is a fail-open.
- A resolution that degraded stays marked `degraded` (:73), so a `log_only` decision record says which of the two `log_only` states produced it (#15159). It marks the record only — `log_only` is allow-and-audit in both, deliberately. A degraded route reporting the chosen `reason` is a finding.
- Only two legitimate fast-path bypasses exist, in [`security/session_ownership.py`](../../autobot-backend/security/session_ownership.py) — `_resolve_fast_paths` (:457): global auth disabled, and enforcement explicitly `disabled`. A third one added in a diff is a finding.
- Creating over an existing session id is a 409, identical for "owned by someone else" and "no recorded owner" — a 403 on the first would confirm who owns it (#14012).

## 3. Plugin loading

**Boundary:** the install endpoint. Loading executes arbitrary Python by design
([`loader.py`](../../autobot_shared/plugin_sdk/loader.py) — `import_module` (:544), then the
`spec_from_file_location` (:613) fallback). No load-time sandbox exists or is intended.

**Canonical enforcement:** every route in
[`autobot-backend/plugin_manager.py`](../../autobot-backend/plugin_manager.py) carries a
`Depends` on [`auth_middleware.py`](../../autobot-backend/auth_middleware.py)
`check_admin_permission` (:943).
Archive safety lives in [`autobot-backend/archive_safety.py`](../../autobot-backend/archive_safety.py)
— `validate_zip_metadata` (:29), `safe_extract` (:60), `MAX_UPLOAD_BYTES` (:21).

**Invariants**
- A plugin route without `Depends(check_admin_permission)` is remote code execution. This is the single highest-severity shape in this subsystem — check it first.
- Extraction goes through `archive_safety`; [`plugin_install.py`](../../autobot-backend/plugin_install.py) only re-exports `_validate_zip_metadata` and `_safe_extract`. A local `zf.extractall` reintroduces zip-slip and symlink escape.
- Names match `_NAME_PATTERN` (:37) before any filesystem touch; the target is claimed by `_claim_install_target` (:127) via `mkdir(exist_ok=False)`, which — with the per-name `_install_locks` — is what makes the collision check TOCTOU-free.
- Git installs: scheme restricted to http(s), `--` before the URL, `protocol.file.allow=never`, no submodule recursion, ref matched against `_GIT_REF_PATTERN` (:40), rejecting a leading `-` or `..`. Dropping any one is a finding on its own.
- `PluginRegistry._plugins` and `HookRegistry` are process-wide singletons that do not dedupe — a load path re-initialising a live plugin double-registers its callbacks (#14000).
- A credential resolver is injected only into a plugin whose resolved directory lies under a trusted built-in root ([`credential_binding.py`](../../autobot_shared/plugin_sdk/credential_binding.py) `bound_resolver`), never by `manifest.name` alone, since a self-declared name lets any installed plugin claim it (#18094); `plugin_install.py` refuses a community install that takes a built-in name. Both plugin hosts (startup `PluginManager`, API `PluginLoader`) take their search and trust lists from [`plugin_paths.py`](../../autobot-backend/plugin_paths.py); the CWD-relative dev fallback is searched but never trusted. The resolver narrows the sanctioned path and is not isolation: an in-process plugin can still read `os.environ` and module state.

## 4. Secrets & credentials

**Boundary:** plaintext lives only inside the store's own methods. Anything crossing out — a
response, a log line, an issue, a PR comment — is already redacted.

**Canonical enforcement:** [`encryption_service.py`](../../autobot-backend/encryption_service.py) AES-GCM + PBKDF2 for data at rest ·
[`autobot_shared/field_encryption.py`](../../autobot_shared/field_encryption.py) `encrypt_field`/`decrypt_field` for single columns ·
[`credential_store.py`](../../autobot-backend/knowledge/connectors/credential_store.py) `ConnectorCredentialStore` (:211) for connector/OAuth creds, ownership via `_require_owner` (:642) ·
[`autobot_shared/auth/internal_api_key.py`](../../autobot_shared/auth/internal_api_key.py) `verify_internal_api_key` (:17) for service-to-service (re-exported by `auth_middleware.py` and the SLM `services/auth.py`) ·
[`services/auth.py`](../../autobot-slm-backend/services/auth.py) `decode_token_async` (:130) for SLM token revocation.

**Invariants**
- No parallel crypto path. A diff introducing its own `Fernet(...)` or `AESGCM(...)` instead of calling the store is a finding regardless of whether the primitive is used correctly.
- Secrets compare with `secrets.compare_digest`, never `==`. A missing/`None` credential can never match — `verify_internal_api_key` returns `False` when either side is unset,
  and `/api/metrics/prometheus` admits only its dedicated read-only scrape token ([`prometheus_scrape_auth.py`](../../autobot-backend/monitoring/prometheus_scrape_auth.py); unset refuses every scrape; record, delivery, rotation: [`PROMETHEUS_SCRAPE_TOKEN_ROTATION.md`](PROMETHEUS_SCRAPE_TOKEN_ROTATION.md)).
- The issue-claims client credential (#18811) is a secret in its minter's own vault, presented as `<secret_id>.<verifier>` in `X-AutoBot-Claims-Credential` and checked per request by `SecretsCoordinator.verify_bearer` (constant-time, live, owner active). A successful check is audited as `secret.access`; failed checks are rate-limited per source and audited in aggregate, one `claims_credential.check_failures` event per source per window ([`coordination_issue_claims_throttle.py`](../../autobot-backend/api/coordination_issue_claims_throttle.py)). Only `claims_principal` in [`coordination_issue_claims_credential.py`](../../autobot-backend/api/coordination_issue_claims_credential.py) reads that header, so it authenticates nothing outside `/api/coordination/issue-claims`; the CLI keeps it in the kernel user keyring only, never on disk.
- Every `ConnectorCredentialStore` read takes `owner_id` and passes `_require_owner`; a new
  method that skips it grants cross-tenant credential read.
- Nothing reaches a log, HTTP error body, or outward artifact without
  [`secret_redaction.py`](../../autobot_shared/secret_redaction.py) (`redact_text` (:327) / `redact_mapping` (:337)) or
  [`security/redaction.py`](../../autobot_shared/security/redaction.py) (`redact_cloud_identifiers` (:67) / `redact_provider_error` (:81)).
  Exception text counts; a boto3 `ClientError` carries the account number in an ARN (#15324).
- Keys come from SSOT config, never a literal. A default value for an encryption key is a
  finding even when production overrides it via env var.
- SLM token revocation fails CLOSED (#16387, owner decision): when the HS256 jti-denylist check
  (`is_jti_revoked` (:114) in [`token_denylist.py`](../../autobot-slm-backend/services/token_denylist.py)) or the password-epoch check can't run because its store (the SLM's own PostgreSQL since #18663) errored,
  `decode_token_async` refuses the token (503 `revocation_check_unavailable`, with `Retry-After`; #18892 — 401 stays for an invalid or revoked token) instead of reading "could not check" as "not revoked" — a Redis outage takes SLM login down, including the backend admin path reached through the proxy (#16374).
- The RS256 authority-token path fails CLOSED the same way (#16412): [`rs256_denylist.py`](../../autobot-slm-backend/services/rs256_denylist.py)
  `is_rs256_jti_revoked` (:89) raises on a Redis error rather than reporting "not revoked"; its caller
  [`jwks_verifier.py`](../../autobot-slm-backend/services/jwks_verifier.py) `verify_authority_token` (:219) denies the token (401) at both call sites; the write side stays best-effort.
- The shared password-epoch helper fails CLOSED in both services (#16411, #16422, owner decisions): a Redis error, or a non-integer stored
  marker or `iat`, raises `RevocationCheckUnavailable` (a `ConnectionError`), which the SLM denies as above and [`auth_revocation.py`](../../autobot-backend/auth_revocation.py) denies with 401; an `except` reading it as "not revoked" is a fail-open.

## 5. Remote desktop access

**Boundary:** an authenticated user vs. the *managed desktop*. Not an auth boundary — the
caller is logged in — so a missing check reads as a working feature, which is how
[#17054](https://github.com/mrveiss/AutoBot-AI/issues/17054) survived.

**Canonical enforcement:** [`autobot-backend/api/ws_security.py`](../../autobot-backend/api/ws_security.py)
`enforce_ws_desktop_auth` — the one gate; `api/vnc_proxy.py`'s websockify route calls it before
proxying. A paired device is judged on its own grants (`DESKTOP_VIEW`+`DESKTOP_INPUT`, #15146); a
user credential must hold `mcp.desktop.control` via `role_has_permission`; everyone else is
refused `1008` before any RFB byte. Full reasoning is in that function's docstring.

**Invariants**
- **`control`, never `read`.** RFB carries framebuffer and input on one stream, so the socket
  cannot grant view without input — `mcp.desktop.read` would be a view-only grant that is not.
- **The permission table decides, not `is_admin_role`** (#13854). A bypass here reverses that
  ruling one call site at a time. Consequence: `superadmin` is admitted because its entry is derived from
  admin's set (#19125, owner decision 2026-10-21: "Super admin is the highest form of admin") —
  grant or change it in `ROLE_PERMISSIONS`, not in the gate. `desktop_ws_role_gate_17054_test.py` asserts
  both the table's answer and the socket's.

## 6. Memory graph / Graph-RAG ownership

**Boundary:** one authenticated user vs. *another user's* memory-graph entities and relations; a scope-less read looks like a working feature (#18825).
**Canonical enforcement:** [`owner_scope.py`](../../autobot-backend/autobot_memory_graph/owner_scope.py) `OwnerScope` (:72) is a REQUIRED argument of every graph read; `require_scope` (:138) fails closed; `entity_visible` (:157) / `redis_owner_clause` (:174) are the one rule; `from_tenant` (:104) builds it from the principal, never a request body.

**Invariants**
- A relation needs BOTH ends readable: [`queries.py`](../../autobot-backend/autobot_memory_graph/queries.py) `_readable_relation_ends` (:254) drops the edge, or its id and type leak.
- No admin bypass (`is_platform_admin` ignored); cross-user reads are `UNSCOPED_ALL_USERS`, system callers only. Ownerless entities are invisible, never rewritten (#17038).

## Cross-cutting

- **Egress:** any new outbound HTTP goes through the guarded fetch —
  [`autobot_shared/security/ssrf_guard.py`](../../autobot_shared/security/ssrf_guard.py)
  `fetch_safe_url` (:305) / `pinned_request_with_redirects` (:230). A bare `aiohttp`/`requests`
  call on a user-influenced URL is SSRF (core rule 8).
- **LLM failover moves prompts (#19753):** [`ModelFallbackCoordinator`](../../autobot-backend/llm_shared/model_fallback_coordinator.py)
  `fail_over` re-sends a turn's prompt to another model. It never carries a prompt from a local provider to an external one unless
  the operator wrote that chain (`AUTOBOT_FALLBACK_CHAIN_*`, `FallbackChain.operator_configured`) -- `failover_policy.locality_allows`
  -- and only while the turn has emitted no text and run no tool (`chat_workflow/llm_failover.py` `turn_has_acted`), so a side effect
  never replays. A model the user picked by hand never fails over. The shared degradation mark is set only by provider-wide causes
(`failover_policy.marks_provider_wide`): a caller's own credential failure (a principal is in scope, `caller_owns_credential`) is
surfaced and neither hops nor marks, and one local request's 5xx or timeout does not degrade a local model for everyone. A hop with no
provider, or from an unknown origin, counts as external and needs an operator-written chain; "local" is by provider type, not host. The
event, the response metadata and the log line carry `fallback_provider` and `operator_configured`.
- **Refactor fallout** historically outranks new code here: a renamed validator or store with
  call sites left on the old name silently removes the check. Grep the **old** identifier.
- **Prompt injection (#16488):** content `research`/`adopt`/`web-fetch` fetch is data, never
  instructions — contract at the top of each skill's `SKILL.md`. A clone goes only through
  [`scripts/research/safe_clone.py`](../../scripts/research/safe_clone.py) `neutralize` (:190) —
  `.git` deleted, agent-instruction files renamed — enforced by `block-dangerous-commands.sh`.
