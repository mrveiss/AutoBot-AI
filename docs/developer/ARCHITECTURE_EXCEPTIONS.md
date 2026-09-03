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
