# Architecture Exceptions

This document records intentional deviations from the standard AutoBot architecture.
Each entry explains what diverges, which canonical module it mirrors (where applicable),
why the exception exists, and how to keep the two in sync.

---

## Windows NPU Worker — Standalone Redis Client

**File:** `autobot-npu-worker/resources/windows-npu-worker/app/utils/redis_client.py`
**Mirrors:** `autobot_shared/redis_client.py`
**Issue:** #5438

**Reason:** The Windows NPU worker is packaged as a self-contained executable via PyInstaller.
It cannot import from `autobot_shared/` at runtime because the shared package is not bundled
with the executable. The standalone redis_client.py replicates the subset of functionality
needed by the worker.

**Sync cadence:** When `autobot_shared/redis_client.py` changes (connection parameters,
retry logic, health-check helpers), manually mirror those changes here. Reference this
document to surface the obligation.

---

## Windows NPU Worker — Standalone Background-Task Retention

**File:** `autobot-npu-worker/resources/windows-npu-worker/app/async_compat.py`
**Mirrors:** `autobot_shared/async_compat.py` (`fire_and_forget`)
**Issue:** #15642

**Reason:** Same packaging constraint as the standalone Redis client above, and established
from the packaging files rather than assumed: `installer/npu_worker.spec` runs PyInstaller's
`Analysis` over `app/npu_worker.py` with `pathex=[app]`, and `scripts/install.ps1` copies
only `app`, `config`, `gui`, `installer`, `nssm`, `scripts`, `tests` and the requirements
file. `autobot_shared/` is on none of those paths, so importing the canonical
`fire_and_forget` would ship an `ImportError` to a Windows NPU node. The mirror replicates
only what the worker needs: a module-level retention set, a done callback that releases the
reference, and a failure log — the fix #15522 defines for a discarded task launch.

**Sync cadence:** When `autobot_shared/async_compat.py`'s `fire_and_forget` changes,
manually mirror the change here. `repo_tests/background_task_retention_ratchet_test.py`
records `autobot-npu-worker/` as a proven zero, so a new discarded launch in this tree
fails there regardless of which module the retention came from.

---

## `utils/gpu_vector_search.py` — FAISS-GPU Hybrid Search Client Type

**File:** `autobot-backend/utils/gpu_vector_search.py`
**Issue:** #5800

**Pattern bypassed:** Direct use of raw chromadb client methods rather than going
through a `BaseCollection` ABC instance.

**Status:** Partially migrated. The `HybridVectorSearch` constructor and
`get_hybrid_vector_search` factory now accept a `BaseClient` (from
`knowledge.backends`) rather than `Any`. The internal call sites
(`get_or_create_collection`, `get_collection`, `list_collections`) all exist on
`BaseClient`, so any conformant adapter works.

**Why the collection call sites are NOT wrapped in `BaseCollection`:**
`HybridVectorSearch` interleaves FAISS-GPU vector search with ChromaDB document
storage in a single hybrid pipeline. The collection object returned by
`get_or_create_collection` / `get_collection` is used immediately for
`collection.add(...)`, `collection.get(...)`, `collection.query(...)`, and
`collection.count()` — all of which are defined on `BaseCollection`. The code
therefore already benefits from the abstraction at the client level; the collection
objects returned satisfy the `BaseCollection` contract and callers do not reach for
any chromadb-specific attribute.

**GPU-specific operations** (`faiss.StandardGpuResources`, `faiss.index_cpu_to_gpu`,
`faiss.index_gpu_to_cpu`) exist in `GPUVectorIndex` and are entirely independent of
the ChromaDB client. They cannot be expressed through any vector-store ABC; they
require direct FAISS C++ bindings by design.

---

## `knowledge/rag_benchmarks.py` — EphemeralClient in Test Fixtures

**File:** `autobot-backend/knowledge/rag_benchmarks.py`

**Pattern bypassed:** Direct `chromadb.EphemeralClient()` instead of `InMemoryClient`
from `knowledge.backends`.

**Status:** Intentional test exception.

**Rationale:** `TestRealKBBenchmarks._ensure_collection()` (line 883) intentionally uses
`chromadb.EphemeralClient()` to exercise ChromaDB's hnswlib HNSW path. `InMemoryClient`
uses a pure-Python brute-force search that cannot replicate the HNSW recall characteristics
this benchmark measures. A swap to `InMemoryClient` would make the test meaningless.

**Grep check:** `grep -rn "EphemeralClient" autobot-backend/` should return only this file.

---

## `api/skills_repos.py` — Broad `except Exception` in `sync_repo`

**File:** `autobot-backend/api/skills_repos.py` (function `sync_repo`, ~line 126)
**Issue:** #5802

**Pattern bypassed:** AutoBot convention is to catch specific exception types rather
than bare `Exception`.

**Reason:** `_sync_packages` performs a composite operation involving network I/O
(fetching from an upstream repository), git operations (clone/pull), and filesystem
writes — each of which raises a distinct exception hierarchy (`aiohttp` exceptions,
`gitpython` exceptions, `OSError` subclasses). Listing every possible type would be
fragile and would not improve error handling since all paths produce the same HTTP 502
response. The broad catch is bounded to this one call site; the exception is logged in
full and re-raised as an `HTTPException` so no information is silently swallowed.

**Grep check:** `grep -n "except Exception" autobot-backend/api/skills_repos.py`

---

## `api/skills_governance.py` — Broad `except Exception` in `detect_gap`

**File:** `autobot-backend/api/skills_governance.py` (function `detect_gap`, ~line 108)
**Issue:** #5802

**Pattern bypassed:** AutoBot convention is to catch specific exception types.

**Reason:** `SkillGenerator.generate()` makes an LLM API call that may fail through
network errors, provider-specific HTTP errors, token-limit errors, JSON decode errors,
or any exception raised inside a dynamically loaded LLM adapter. The failure mode is
non-fatal (the endpoint returns `{"success": false, ...}` rather than raising), so a
broad catch with a warning log is the correct boundary. Narrowing the catch would
either miss real failures or require enumerating every LLM adapter's private exception
classes.

**Grep check:** `grep -n "except Exception" autobot-backend/api/skills_governance.py`

---

## `api/skills_governance.py` — Broad `except Exception` in `promote_skill`

**File:** `autobot-backend/api/skills_governance.py` (function `promote_skill`, ~line 229)
**Issue:** #5802

**Pattern bypassed:** AutoBot convention is to catch specific exception types.

**Reason:** `SkillPromoter.promote()` writes files to the filesystem and may invoke
git operations to register the promoted skill. Failures can originate from
`PermissionError`, `FileExistsError`, `OSError`, `subprocess.CalledProcessError`, or
git library exceptions. All failure paths produce the same HTTP 500 response; the
exception is logged in full and re-raised as `HTTPException` so no information is
silently swallowed. Narrowing the catch would add fragility without improving
observability.

**Grep check:** `grep -n "except Exception" autobot-backend/api/skills_governance.py`

---

## `FlashAttentionV2` / `TestFlashAttentionV2` — Published Algorithm Name

**Pattern bypassed:** `py-duplicate-concept` rule flags `Enhanced*`/`Unified*`/`*V2` class names that shadow a base-name class. `FlashAttentionV2` and `TestFlashAttentionV2` match the `*V2` pattern but are intentional exceptions.

**Reason:** "FlashAttention-2" is a published algorithm (Dao et al., 2023, NeurIPS) with an established canonical name in the ML literature. The `V2` suffix identifies the specific paper/algorithm revision, not a code-organisation era marker. Renaming to `FlashAttention` would lose the version identity and make it impossible to distinguish from the original FlashAttention algorithm.

**Waiver pattern:** Any file defining `FlashAttentionV2` or `TestFlashAttentionV2` should carry an inline suppression on the class line:

```python
class FlashAttentionV2:  # canonical: ignore py-duplicate-concept — published algorithm name FlashAttention-2 (Dao et al. 2023) (#10666)
```

**Grep check:** `git grep -n "FlashAttentionV2"` should return only flash-attention implementation and test files.

---

## VNC Service Account — Real Home Directory (not `nologin`'s no-home)

**File:** `autobot-slm-backend/ansible/roles/vnc/tasks/main.yml`,
`autobot-slm-backend/ansible/roles/vnc/defaults/main.yml`
**Issue:** #14319 (shell corrected in PR #14412 review round 2)

**Pattern bypassed:** Every other per-service account on the platform
(`autobot-backend`, `autobot-ai`, `autobot-npu`, `autobot-browser`,
`autobot-tts`) is `system: true` with `shell: /usr/sbin/nologin` and no home
directory — the account exists only to own files and run one systemd unit.

**Reason — home directory only, NOT the shell:** VNC starts an interactive
desktop session and needs a real home directory (`~/.vnc/passwd`,
`~/.vnc/xstartup`, `~/.vnc/config`) to hold its state; a `nologin` account
with `create_home: false` has nowhere to put it. That is the ONLY dimension
this account deviates on. The shell field does not need to change:
`vnc-server.service.j2` starts `vncserver` through systemd's `User=`
directive, which execs the unit's `ExecStart` directly and never consults
`/etc/passwd`'s shell field, and `templates/xstartup.j2` carries its own
`#!/bin/bash` shebang, so the kernel resolves the interpreter from the
script itself when `vncserver` execs it — nothing in the VNC path needs the
account's login shell to be anything other than `nologin`. `autobot-vnc`
(the account's default name — see `vnc_user` in `defaults/main.yml`) is
therefore `system: true`, `shell: /usr/sbin/nologin`, `create_home: true` —
identical to every other per-service account except `create_home`. A
standing interactive login shell on a service account is an unnecessary
persistence foothold; `su -s /bin/bash - autobot-vnc` still works as root
for interactive debugging if that is ever needed.

**What it explicitly does NOT get:** sudo access of any kind, and the
account is validated to never be `autobot_admin` (the emergency admin
safety-net account) — see the `assert` task at the top of `tasks/main.yml`.

**Grep check:** `grep -n "vnc_user\|vnc_forbidden_user" autobot-slm-backend/ansible/roles/vnc/defaults/main.yml`

---

## Compose Prometheus Scrape Token — Generated by `secrets-init`, Not the SLM

**Files:** `docker/secrets-init.sh`, `docker/with-secrets.sh`, `docker-compose.yml` (autobot-prometheus)
**Issue:** #16375

**Pattern bypassed:** "Credentials always via the canonical secrets manager" — on a fleet
deployment the scrape token's record is the SLM `SystemSecret` (mirrored to the System vault),
delivered by the deploy roles.

**Reason:** compose runs an SLM container, but no path delivers SLM-held secrets into the other
compose containers: the SLM's deploy path is ansible over SSH to fleet nodes, which compose does
not use. The token must exist in two places at start (backend env and a file Prometheus reads),
so it is generated by `secrets-init` like the compose JWT and root key (#9905), kept in the
`autobot_secrets` volume, and never overridable by env (a one-sided override would refuse every
scrape). Compose is the local/dev topology; production is the fleet path.

**Grep check:** `grep -n "PROMETHEUS_SCRAPE_TOKEN" docker/secrets-init.sh docker/with-secrets.sh`
shows one generator and one export; no other compose file sets the variable.

---

## Service-Discovery Cache TTL — Plain Shared Constant, Not Env-Backed

**File:** `autobot_shared/service_discovery.py`
**Issue:** #14465

**Pattern bypassed:** "Cache TTL — never hard-code — module-level constant
from an env var."

**Reason:** `slm/agent/health_collector.py`'s discovery-sweep cache TTL and
`services/reconciler.py`'s restart-churn window (which must stay
comfortably larger than that TTL, or the churn signal regresses to a pulse
that misses most heartbeats) run in two DIFFERENT processes on two
DIFFERENT machines — the agent on each fleet node, the backend on the
manager host. An env var only provides a genuine single source of truth if
it is set to the identical value on every one of those machines; nothing in
either process can enforce that. A plain constant, shipped in the one
codebase both processes deploy from, cannot drift that way — changing it is
one edit that reaches every node on the next code-sync, not an env var an
operator has to remember to set identically everywhere.

**Grep check:** `grep -rn "SERVICE_DISCOVERY_TTL_S" autobot_shared/service_discovery.py autobot-slm-backend/slm/agent/health_collector.py autobot-slm-backend/services/reconciler.py` should show one definition and two importers, no second hardcoded literal.

---

## SLM → node proxy calls — not routed through the guarded fetch

**File:** `autobot_shared/node_proxy.py`
**Callers:** `autobot-slm-backend/api/voice_proxy.py`, `api/personality_proxy.py`, `api/memory_lifecycle_proxy.py`
**Issue:** #14886 (decision), #13625 (Rule 8's origin audit)

**Pattern bypassed:** Rule 8 — "outbound HTTP goes through the guarded fetch
(egress policy)". These calls use `httpx` directly, via the shared node client.

**Reason:** Rule 8's origin audit scoped `guard_egress`/`ssrf_guard` to external
connectors whose target host arrives from *customer* configuration, where a
hostile value is the threat being defended against. A control-plane → node call
has neither property: the host comes from `AUTOBOT_BACKEND_URL` or the
identity-authority base, both operator-set deployment config, and the request
body never influences it. Nothing under `autobot-slm-backend/` routed through the
guarded fetch before this change either — grepping for `guard_egress` or
`ssrf_guard` there returns zero hits. So the state was undocumented rather than
decided, which is what #14886 asked to fix. Fixing it in one proxy alone would
have created a fourth inconsistent pattern, so it is decided once, here, and
applied by every caller of the shared client.

**What keeps it safe instead:** TLS verification is on by default
(`autobot_shared/tls.py::tls_verify_enabled`, pinned by
`autobot_shared/node_proxy_test.py::test_tls_verification_is_on_by_default`), the
internal API key travels only on that verified channel, and the target host is
never taken from a request.

**Revisit when:** a node proxy's target host starts coming from anything a
request can influence — a fleet member id resolved from a request body, a
customer-supplied node URL. At that point the host is attacker-influenced and
the guarded fetch applies.

**Grep check:** `grep -rn "guard_egress\|ssrf_guard" autobot-slm-backend/` should
stay empty, or this entry needs replacing with the migration.

## SLM event severity enums — not aliased to the shared Severity

**File:** `autobot-slm-backend/models/database.py:195` (`EventSeverity`), `:729` (`SecurityEventSeverity`)
**Issue:** #18098

**Pattern bypassed:** the one canonical `autobot_shared.status_enums.Severity`.

**Reason:** (1) `models/database.py` must stay path-loadable without a package path
(`database.py:35`, `:215`; the migration gate;
`migrations/migrate_system_secrets_to_vault_test.py:87`;
`tests/services/test_security_posture_auditor.py:28-50`), and the bare name
`status_enums` there resolves to the SLM's own `autobot-slm-backend/status_enums.py`
(`database.py:41`; `conftest.py:399-405`), so `autobot_shared.status_enums` cannot be
imported there. (2) Both are `(str, Enum)`, persisted as `.value` into indexed
`String(16)` columns (`database.py:235`, `:801`). (3) `api/security.py:425`
`for sev in SecurityEventSeverity:` builds the threat-summary keys, so an alias would
grow the response from 4 to 10 keys.

**What keeps it safe instead:** the values are a strict subset of the canonical
lowercase values; every consumer uses `.value` (the consumer audit found no
str-equality, no member JSON and no `Enum` column); the guard
`repo_tests/severity_enum_fork_guard_18098_test.py` records them as out of its scan.

**Revisit when:** `models/database.py` stops being path-loaded, or the canonical module
gains a subset ladder usable at the iteration site.

**Grep check:** `grep -n "class .*Severity(str, enum.Enum)\|class .*Severity(str, Enum)"
autobot-slm-backend/models/database.py` should list exactly these two. (The same
pattern over all of `models/` also lists `PortConflictSeverity` in `manifest.py`, a
different vocabulary.)

## SLM Recovery Page — No i18n Runtime, English-Only

**File:** `autobot-slm-backend/static/recovery.html`
**Served by:** `autobot-slm-backend/api/health.py`'s `health_router` (`GET /api/recovery`) — co-located with `frontend_bundle_status`, the probe for the exact condition this page recovers from, rather than a dedicated router (#15462 review, also keeps `main.py` under its grandfathered line-count ceiling, #14236)
**Issue:** #15462

**Pattern bypassed:** "No hardcoded UI strings — anything user-facing needs
i18n across all 11 locales."

**Reason:** This page exists because the SLM frontend's build output can be
missing or broken (#15462 — a directory holding one file, no `index.html`,
serving 403 for the whole `/slm/` tree while every service reported
healthy). The Vue i18n runtime ships as part of that same frontend bundle,
so wiring the recovery page into it would make the recovery surface depend
on the exact artifact it exists to work around — reintroducing the single
point of failure this issue is about. The page is therefore a single,
dependency-free static HTML file with inline CSS/JS: no framework, no
bundler, no build step, no CDN import, nothing that can itself fail to
build. It is served directly by the SLM backend (`FileResponse`), reachable
through `location /slm/api/` in nginx — a reverse-proxy block, not a
static-file alias, so it does not depend on `dist/` either.

**How the text is handled:** All strings are English, hand-written directly
into `recovery.html`. This is a deliberate scope limit, not an oversight —
an operator locked out of the dashboard by a broken build needs a page that
loads at all, in front of a full translation matrix for a page that exists
purely to run one action (sign in, trigger self-update).

**Revisit when:** a lightweight, dependency-free i18n mechanism exists that
does not require the frontend bundle to be servable (e.g. a tiny inline
dictionary the backend renders server-side from `Accept-Language`) — at that
point this page can adopt it without reintroducing the coupling described
above.

**Grep check:** `grep -c '<script' autobot-slm-backend/static/recovery.html`
should show the page has no `<script src=` — everything it loads is inline
in the same file, never fetched from a bundler-produced path.

---

## `task_claim` / `work_claims` — Two Redis Claim Primitives, Kept Separate

**Files:** `autobot-backend/services/task_claim.py`, `autobot_shared/coordination/work_claims.py`
**Issue:** #15957 (owner ruling, 2026-09-10)

**Pattern bypassed:** "Reuse from `autobot_shared/` — one canonical
implementation per concept; consolidate, never fork."

**Reason:** They look like one concept implemented twice — both are
owner-checked, TTL-bounded Redis claims — and they are two concepts.
`task_claim` claims **the task itself**; `work_claims` claims **the work a task
touches** (paths, kb entries, devices, projects, config). Two agents can hold
claims on different scopes while working the same task, and one agent can hold
a task while touching scopes it never claimed. Collapsing them would make the
answer to one question read as the answer to the other.

The structural reason makes an adapter worse, not merely unnecessary.
`task_claim` emits audit on every outcome of `claim_task`, `renew_claim` and
`release_claim`, including the fail-open `redis_unavailable` and `redis_error`
(the renew and release fail-open branches emitted nothing until #16217).
`work_claims` emits none and cannot: `autobot_shared` must not import
from `autobot-backend`. An adapter could not move emission down, so it would
leave a backend-side wrapper still owning audit, signatures and tests — the same
constraint that already put `services/claim_yield.py` (#15948) in the backend
package rather than beside the primitive it extends.

The Lua an adapter could unify is smaller than it looks. Measured 2026-09-10 as
non-blank lines: `task_claim` has 10 (release 5, renew 5); `work_claims`'
matching release and renew scripts have 12 (4 and 8). Its 35-line acquire script
has no counterpart, because `claim_task` uses a plain `SET NX EX`. About ten
lines a side is not worth a migration across a live double-pickup guard.

*Correction recorded rather than silently edited:* the analysis this ruling was
made on said "every outcome" is audited, counted 8 emission sites, and put the
shared Lua at "roughly 40 lines". Measured, there are 5 emission sites, the
fail-open branches above are unaudited, and the comparable Lua is about ten
lines a side. Both corrections strengthen the decision rather than weaken it.
#16217 has since audited those four fail-open branches, so there are now 9.

**How the split is enforced:** `task` is a **reserved** kind in `work_claims`,
not merely an absent one. Absent produced "unknown scope kind" — the same
answer a typo gets — so a caller reaching for `task:` could not tell a decision
from a gap. `RESERVED_KINDS` now refuses it with the reason and the destination,
through `_require_kind`, which every entry point that names a kind calls —
`Scope.parse`, `list_claims`, and `branch_stewardship.prune_closed_branches` — so they cannot
drift apart. `RESERVED_KINDS` is a read-only mapping, as `VALID_KINDS` beside it
is a `frozenset`, so no caller can un-reserve a kind at runtime. Both module
docstrings state the split.

**Revisit when:** `autobot_shared` gains an audit sink that does not import
from `autobot-backend`. That removes the structural half of this reason; the
conceptual half (task identity vs work scope) would still need arguing on its
own merits.

**Grep check:** `grep -n '"task"' autobot_shared/coordination/work_claims.py`
should show `task` only as a `RESERVED_KINDS` key, never inside `VALID_KINDS`;
`grep -c 'from services' autobot_shared/coordination/work_claims.py` should be
`0`.

---

## `utils/ollama_connection_pool.py` — Superseded, Kept In-Tree Pending Removal

**File:** `autobot-backend/utils/ollama_connection_pool.py`
**Superseded by:** `autobot-backend/llm_shared/base_provider.py` (`BaseProvider._concurrency_semaphore`),
`autobot_shared/http_client_manager.py` (`HTTPClientManager`)
**Issue:** #16527

**Reason:** `OllamaConnectionPool` bundled two concerns — bounding concurrent
Ollama requests (`asyncio.Semaphore` + queue/stats) and pooling the underlying
HTTP connections — behind its own `acquire_connection()`. Both are now owned
canonically elsewhere: `HTTPClientManager` already pools TCP connections for
every outbound call via one `aiohttp.TCPConnector` (`acquire_connection()`
itself borrows from it through `tracked_session()`, so the pool never owned
its own connections), and `BaseProvider.__init__` now creates a per-provider
`asyncio.Semaphore` sized from `LLMSettings.max_concurrent_requests`, which
bounds Ollama's in-flight requests automatically since `OllamaProvider`
subclasses `BaseProvider`. The pool's only caller, `llm_shared/adapters/
ollama_adapter.py::OllamaAdapter`, is registered for diagnostics
(`api/adapters.py`: `list_adapters`, `test_adapter_environment`,
`probe_adapters`, `pull_model`) and never sits on the live chat/stream path —
`services/llm_service.py` calls `OllamaProvider.chat_completion()` directly
through the registry, so wiring the pool into the adapter would not have
bounded anything real. Retiring it is explicitly the fix here, not a unilateral
deletion: it is marked superseded in its module docstring rather than removed,
pending a dedicated removal PR once the new semaphore has run in production.

**Revisit when:** the new per-provider semaphore has been running in
production long enough to trust, at which point `utils/ollama_connection_pool.py`
and `utils/ollama_connection_pool_test.py` can be deleted outright — tracked
in #16539.

**Grep check:** `grep -rln "OllamaConnectionPool\|get_ollama_pool" autobot-backend/ | grep -v ollama_connection_pool` should show only `llm_shared/adapters/ollama_adapter_test.py` or nothing — no new production caller should appear without updating this entry.

## Per-Service `User`, `Organization`, `UserService` and `OrganizationService` Bindings

**Files:** `autobot-backend/user_management/models/{user,organization}.py`, `autobot-slm-backend/user_management/models/{user,organization}.py`, `autobot-backend/user_management/services/user_service.py`, `autobot-slm-backend/user_management/services/user_service.py`, `autobot-backend/user_management/services/organization_service.py`, `autobot-slm-backend/user_management/services/organization_service.py`
**Shared core:** `autobot_shared/user_management/models/user.py` (`UserCore`), `autobot_shared/user_management/user_service*.py` and `autobot_shared/user_management/organization_service.py` (`OrganizationService`, abstract: raises `TypeError` when `organization_model`/`user_model` are unbound)
**Issues:** #12647, #15068, #17312 (symbol-fork ratchet), #18449

**Pattern bypassed:** "One definition per concept" as measured by `repo_tests/symbol_fork_baseline.json`.

**Reason:** these names are NOT second implementations. The behaviour has exactly one
definition in `autobot_shared`; each service keeps a thin binding that must be a concrete,
separately mapped class: the two services attach different SQLAlchemy relationships and
columns (backend: activity tracking and Company OS columns; SLM: none) and register in different
mapper registries, so one shared mapped class would break `configure_mappers()` on one side.
`UserService` bindings only set `user_model` and, in the backend, two hooks. Each service's
`OrganizationService` only binds its own concrete `Organization` and `User` mappings (two
ClassVars); the behaviour has one definition in `autobot_shared`. Same registry-per-service
constraint as `User`/`Organization`. Since the detector now counts a same-name subclass of a
shared definition as a binding (#17312), `UserService` and `OrganizationService` no longer
appear in `symbol_fork_baseline.json`; `User` and `Organization` do and stay, because they
subclass `UserCore`/a differently named core, not a same-name shared class.
`repo_tests/one_user_service_15068_test.py` pins that shape by behaviour: a class carrying the
account-handling methods anywhere else is a failure whatever it is called.

**Revisit when:** the two services share one SQLAlchemy registry, or the detector learns to
treat a subclass of a differently named shared core (`UserCore`) as a binding. (Its same-name
subclass half landed in #17312.)

**Grep check:** `grep -rn "^class \(User\|Organization\|UserService\|OrganizationService\)\b" autobot-backend/user_management autobot-slm-backend/user_management autobot_shared/user_management` should list `UserService` and `OrganizationService` in `autobot_shared` plus one `UserService`, `OrganizationService`, `User` and `Organization` subclass binding per service.

## SLM Admin `Base` and Shared User-Management `Base`

**Files:** `autobot-slm-backend/models/database.py` (`Base`), `autobot_shared/user_management/models/base.py` (`Base`, re-exported by both services' `user_management/models/base.py`)
**Issues:** #1878, #10862 (tablename collision guard), #17312 (symbol-fork ratchet)

**Pattern bypassed:** "One definition per concept" as measured by `repo_tests/symbol_fork_baseline.json`.

**Reason:** the two `Base` classes own different metadata registries bound to different PostgreSQL databases (`slm` and `slm_users`). `main.py` creates each registry's tables on its own engine. One shared `Base` would put both databases' tables in one metadata (each `create_all` would create the other database's tables) and would add the shared Base's `created_at`/`updated_at` columns to SLM tables that declare their own (a schema change). The shared `Base` is already the single definition for the backend and the SLM user-management side. `check_tablename_collisions` polices the split. `Base` stays in `symbol_fork_baseline.json`, as `User` and `Organization` do.

**Revisit when:** the SLM admin models and user-management models move to one database, at which point `INTENTIONALLY_SHARED_TABLENAMES` ("roles") must also be resolved.

**Grep check:** `grep -rn "^class Base(" autobot-slm-backend autobot_shared` should show exactly `models/database.py` and `user_management/models/base.py`.

## `config/loader.py` — Stdlib `logging`, Own YAML Read (not `load_config_file`)

**File:** `autobot-backend/config/loader.py` (`load_yaml_config`)
**Shared authority it does not use:** `autobot_shared/config_file_loading.py` (`load_config_file`)
**Issue:** #17855

**Reason:** `config/loader.py` is on the logging-manager initialisation path: it
uses stdlib `logging` on purpose so that loading configuration cannot deadlock
waiting on a logger that itself needs configuration (the GH#7765 pattern noted
at the top of the module). `load_config_file` imports
`autobot_shared.logging_manager`, so adopting it here would reintroduce exactly
that cycle. The other YAML config loaders in #17855 row 8 have no such
constraint and were migrated. This loader never writes defaults back to disk, so
the behaviour the shared loader exists to guarantee is already met; what it
lacks is the loaded-versus-defaults distinction (`LoadedConfig.source`).

**Revisit when:** `load_config_file` (or a logging-free core of it) no longer
imports `logging_manager`, at which point `load_yaml_config` should delegate to
it and this entry be removed.

**Grep check:** `grep -n "logging_manager" autobot_shared/config_file_loading.py` — if empty, this exception is obsolete.

---

## Memory graph vs knowledge-base visibility — two models on purpose

**Files:** `autobot-backend/autobot_memory_graph/owner_scope.py`, `autobot-backend/knowledge/search_filters.py`
**Issue:** #18825

**Reason:** the two stores answer different questions with the same words, so one predicate would be wrong for one of them.

| Word | Memory graph (`owner_scope.py`) | Knowledge base (`search_filters.py`) |
|---|---|---|
| owner | `owner_user_id`; a read sees only its own entities | `owner_id`; one input among several to `check_access` |
| org | the owner's own entities inside an org context (org narrows, never grants) | `organization` visibility grants every member of the org, whoever owns the fact |
| shared | `__shared__` owner: readable by every signed-in user | `shared` visibility: readable only by the users named in the fact's share list |
| system | `__system__` owner: readable by NO scoped read, only `UNSCOPED_ALL_USERS` | `system` visibility: readable by every signed-in user |
| admin | no bypass | explicit read APIs may pass `is_admin`; chat grounding never does |
| group / access level | not modelled | `group` membership and `access_level` grant reads |

The graph is a RediSearch TAG filter plus a pure-Python predicate over two stamped fields. The KB decision needs
ownership-manager lookups (share lists, group membership). Sharing the predicate would either give graph entities a share list
and groups they do not have, or flip `system` in one store. Sharing only the constants would hide that `shared` and `system`
mean opposite things in the two places, so the graph names stay `__shared__` / `__system__` (reserved owner ids that no real
user id can take) and the KB's stay lower-case visibility values.

**Revisit when:** the graph gains sharing between users or groups; then reuse the KB's `check_access` rather than growing
a third model in `owner_scope.py`.

**Grep check:** `grep -n "OWNER_USER_FIELD\|SHARED_OWNER_ID" autobot-backend/autobot_memory_graph/owner_scope.py` -- if
`owner_scope.py` ever imports from `knowledge/search_filters.py`, this exception is obsolete.

## Monitoring Role — FHS `/etc` and `/var` Service Paths

**Files:** `autobot-slm-backend/ansible/roles/monitoring/defaults/main.yml`
**Canonical it does not use:** `autobot.base_dir` (the one install root, #18880)
**Issue:** #18556

**Reason:** `alertmanager_config_dir`, `alertmanager_data_dir`, `prometheus_config_dir`
and `prometheus_data_dir` (also `grafana_data_dir`) are `/etc/<svc>` and `/var/lib/<svc>`
paths. These are the FHS locations for host-wide configuration and variable state, the
paths the upstream packages and their systemd units use, and operators and backup tooling
look for them there. Only the install directories (binaries) live under the install root,
derived as `{{ autobot.base_dir | dirname }}/<svc>`.

**Revisit when:** the platform decides to relocate service state under the install root.

**Grep check:** `grep -n "_config_dir\|_data_dir" autobot-slm-backend/ansible/roles/monitoring/defaults/main.yml` -- if no `/etc` or `/var` literal remains, this exception is obsolete.

## Compose Postgres Variables — Same Concept, Compose's Own Values

**Files:** `docker-compose.yml`, `autobot_shared/postgres_identity.py`
**Canonical it does not use:** the fleet values of `AUTOBOT_POSTGRES_USER` and `SLM_DB_NAME`
**Issue:** #19408

**Reason:** Each name means one concept everywhere: `AUTOBOT_POSTGRES_USER` is the login role
on the user-management database, and `SLM_DB_NAME` is the SLM control-plane database. Only
the values differ. The postgres image creates one role, so compose uses the owner role
(`COMPOSE_OWNER_ROLE`) where a fleet host has `autobot_app`, and keeps its existing database
(`COMPOSE_SLM_DB_NAME`) where a fleet host has `slm`. Renaming either would move existing
compose volumes. The compose SLM defaults to that owner role too; a non-default
`SLM_POSTGRES_USER` must already exist, because compose creates only the owner role.

**Enforced by:** `COMPOSE_KEY_VALUES` in `repo_tests/postgres_identity_one_source_19320_test.py`
allows these values in compose files only.
