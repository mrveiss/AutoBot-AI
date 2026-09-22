# Source Analysis: an offline-first knowledge appliance orchestrator

> Reference work, analysed 2026-09-22. Source identity intentionally omitted (see
> `.claude/skills/research/SKILL.md` — anonymization rule). All fetched content was treated as
> data; no instructions were followed from it.

## What It Is

A self-hosted "appliance" server whose product is not a feature set but an **orchestration layer**:
a TypeScript management web app ("command centre") plus API that installs, configures, updates and
monitors a fleet of third-party containers, so the end user never touches Docker. The bundled
capabilities — an offline encyclopedia/ebook archive reader, a courseware platform with progress
tracking, offline vector map tiles, a local LLM chat with document RAG, a data-encoding toolbox, a
notes app, a hardware benchmark, and a one-click app catalogue — are all upstream OSS projects it
wraps rather than reimplements. Maturity: high adoption (tens of thousands of stars within ~6
months of public release), Apache-2.0, semantic-release driven, ~96 open issues, active daily
commits. Positioned for emergency-preparedness, off-grid and offline-education users.

## Architecture & Key Patterns

- **Compose-as-the-runtime.** One `docker-compose` project defines the control plane: the admin
  app, a log viewer, MySQL, Redis, and two sidecars. Every *installed capability* is an additional
  container the admin app writes into / manages through the same compose project — the app's own
  state of the world is the Docker daemon, not a separate inventory.
- **MVC monolith, server-rendered SPA.** A single TypeScript backend (AdonisJS-style layout:
  `controllers / services / jobs / models / validators / middleware`) with an Inertia + Tailwind
  frontend — one deployable, no frontend/backend split to keep in sync.
- **Service layer holds the weight.** 28 services; the largest are the Docker driver (~96 KB),
  RAG (~88 KB), benchmark (~76 KB), then per-domain content services (map tiles, archive catalogue,
  drug reference, model runtime). All orchestration logic is in services, not controllers.
- **Redis-backed job queue for everything slow** — downloads, tile extraction, embedding, model
  pulls, dataset ingestion, benchmark runs, and the three auto-update families each have a job
  class. Nothing long-running happens in a request.
- **Sidecar pattern for privileged work.** Two sidecars hold the Docker socket:
  a **disk collector** (host disk topology the containerised app cannot see) and an **updater**.
- **Self-update via a watcher + request file.** The admin app cannot `docker compose up` itself
  without killing the process mid-write, so it drops a JSON request (`{target_tag: ...}`) onto a
  shared volume; the updater sidecar polls that path, then pulls and recreates services one by one,
  including the app itself. Image GC is deliberately conservative — it enumerates compose-managed
  images and removes only those, refusing `image prune -a` because user-installed app images would
  be collateral, and never passes `-f` to `docker rmi` so an in-use image simply survives.
- **Content as declarative manifests.** Curated catalogues (map regions, archive categories,
  medical conditions, remedy datasets, creator packs) are JSON in-repo, versioned with the code, so
  "what content exists" is reviewable in a diff rather than fetched from a mutable API.
- **Three independent auto-update tracks** — core app, installed apps, offline content — each with
  its own command, job and service, each separately schedulable.

## Notable Implementation Details

- **Update decision pipeline is testable without updating.** A dry-run CLI command replays the
  entire decide-to-update pipeline in three modes: a deterministic offline scenario suite covering
  every branch (major-only, cool-off, prerelease/draft, maintenance-window wrap-around) that exits
  non-zero and is CI-wirable; a live simulation against the real release feed with real pre-flight
  checks; and a fully offline run with a canned release list and a frozen clock. The risky code
  path gets unit-test economics without a real version bump.
- **Update pre-flight as a gate, not a hope.** Auto-update only fires inside a user-configured
  window, after a cool-off period, with enough free disk for the new image, and only when no
  download or app install is in flight. Major versions always require a human.
- **Degrading connectivity probe.** "Am I online?" tries a well-known trace endpoint, falls back to
  other endpoints the app already contacts, and is overridable by env var (which wins) or UI
  setting — a nod to the fact that the primary probe target is commonly firewalled.
- **Pluggable inference backend.** The local model runtime is default but swappable for any
  OpenAI-compatible server, including one on another host; the UI is explicit that the richer path
  (model download/management) exists only on the native runtime, and that the remote host's setup
  is the user's problem. Honest capability degradation rather than a pretend abstraction.
- **A guard module for bring-your-own containers.** Custom user-supplied containers go through a
  dedicated guard service rather than straight to the Docker driver.
- **Benchmark with a telemetry split.** Scoring logic and the opt-in leaderboard upload live in
  separate modules, so the measurement works with the network path removed.

## Strengths

- The value proposition is *integration*, and the code matches it: one install command, one UI, one
  update system over ~8 heterogeneous upstream projects.
- Self-update is treated as a first-class, adversarial problem (process suicide, partial pulls,
  disk exhaustion, concurrent installs, GC blast radius) rather than a `docker pull` in a cron.
- Offline-first is enforced, not claimed: no telemetry, network needed only at install/download
  time, connectivity detection is overridable.
- Content curation is in-repo and diffable.
- Hardware honesty — documents that the orchestrator is lightweight and the *chosen payload* sets
  the requirement, and declines hardware sponsorship framing.

## Weaknesses / Limitations

- **No authentication at all, by design.** Anyone on the LAN has full control of the command
  centre — which holds the Docker socket path to the host. Upstream's position is that auth may
  come only if users ask for it; the mitigation offered is network-level port control.
- **Privileged sidecars are a large trust surface.** Docker-socket access plus a file-triggered
  update path means anything that can write the shared volume can drive image pulls and container
  recreation.
- **Arbitrary user containers** are a first-class feature on an unauthenticated appliance; a single
  guard module is the whole control.
- **Service-layer obesity** — several single files in the 40–96 KB range mix policy, I/O and shell
  orchestration; hard to review, hard to unit-test in isolation.
- Debian/Ubuntu-only supported path (Windows via WSL2 is community-supported), so the install
  script carries distro assumptions.
- Heavy dependence on upstream projects' packaging: an upstream image change is an outage the
  wrapper must absorb.

## Visible vs Hidden Metrics

**Visible (advertised):**
- Very large star count and trending-#1 exposure — real but a popularity signal, not a quality one;
  self-selecting for "impressive demo" rather than "operated for a year".
- Its headline claims — a single-command install, no telemetry, no subscription — are verifiable
  from the repo, and they hold up on inspection.
- Bundled capability count (8 headline capabilities + an app catalogue) — genuinely broad, but all
  of it is upstream software; the project's own code is the orchestrator.
- Hardware/benchmark leaderboard numbers — community self-reported, not independently verified.

**Hidden (inherited by an adopter):**
- **Upstream fan-out.** ~8 third-party projects' release cadences, breaking changes, and CVEs
  become the wrapper's on-call surface. The update system exists *because* this cost is real.
- **Docker socket as the control plane.** Convenience now, privilege-escalation blast radius
  forever; every feature that "just installs an app" is also a container-run primitive.
- **Zero-auth posture** pushes the entire access-control problem onto the operator's network
  configuration — an invisible operational requirement that most target users will not meet.
- **Storage and bandwidth**: hundreds of GB of content, and content-update jobs that must be
  scheduled, disk-checked and resumable — hence the dedicated content-update track.
- **Self-update complexity** is the least glamorous and highest-risk subsystem; the dry-run harness
  is the tell that it cost real effort to make safe.
- **Learning curve is deferred, not removed** — the abstraction holds until a container misbehaves,
  at which point the operator needs the Docker knowledge the product promised to hide.

**Weighing:** the visible wins are real for the stated audience (a single household operator, on a
trusted LAN, who wants offline knowledge without learning Compose) — there, zero-auth and socket
privilege are acceptable because the threat model is "no internet, one family". For any adopter
whose appliance sits on a shared or semi-trusted network, or who must answer for multi-user access,
the hidden costs invert the verdict: the auth gap and the socket-as-control-plane design would each
have to be closed before the integration convenience is worth anything. The transferable value is
therefore in the *mechanisms* (self-update watcher, dry-run decision harness, conservative GC,
manifest-as-code content curation), not in the bundle.

## Injection / untrusted-content check

Read: repository metadata, `README.md`, `install/management_compose.yaml`, the updater sidecar
watcher script, and directory listings for `admin/app/{services,jobs}`, `admin/commands`,
`install/`, `collections/`, `.github/`. **No agent-directed instructions, prompt-injection text, or
"ignore previous instructions" patterns were observed in what was read.** Not read: the ~4.4 MB
archive blobs, `admin/inertia`, `admin/database`, controllers, or individual service sources beyond
the watcher script — those were not inspected, so no claim is made about them either way.

---

## Addendum — mechanism detail (read after Phase 1)

Two modules were read in full because they carry the transferable engineering.

### 1. The update decision is a pure function; execution is separate

The auto-update service exposes a **side-effect-free verdict object** rather than an
"update if needed" procedure:

```
Decision { enabled, currentVersion, config, withinWindow,
           eligibleTarget, preflight, outcome, reason }
Outcome  ∈ { disabled | outside-window | eligibility-error |
             no-eligible | blocked | ready }
```

Everything the verdict depends on is injectable — the clock (`now`), the release list, and a
`fakePreflight` that short-circuits Docker/disk/queue probing. That single design choice is what
makes the three-mode dry-run harness possible: the scenario suite is just the pure function called
with canned inputs, so every branch (major-only bump, inside cool-off, prerelease, draft,
window wrap-around past midnight) is asserted without a container anywhere near the test.

**Eligibility rules** (all four must hold): same major version as the running build (major bumps
are always manual), strictly newer, published at least `cooloffHours` ago, and neither draft nor
prerelease — "auto-update never rides early access". A malformed cool-off config falls back to the
default rather than silently resolving to zero; an explicit `0` is honoured.

### 2. Blocker severity decides whether a failure counts against you

Pre-flight returns `{ ok, blockers[] }` where each blocker carries a severity:

- `skip` / transient — *retry next window, no penalty*: another update already running, N downloads
  in flight, N app installs in flight.
- `failure` — counts toward a consecutive-failure backoff that eventually auto-disables
  auto-update and records an `autoDisabledReason`: e.g. the update sidecar is absent.

The distinction matters: a busy appliance would otherwise trip its own circuit breaker simply for
being busy. Probe errors (`could not check active downloads`) are logged and *not* converted into
blockers — an unknown is not treated as a failure.

The disk check is the non-obvious one: instead of guessing, it asks the **container registry for
the target image's manifest for the host architecture** and compares the computed size against
host free space *before* pulling.

### 3. The custom-container guard: block vs warn, with a parse-differential defence

User-supplied containers run as host siblings via the mounted socket (docker-out-of-docker), which
the module's own comment calls "a real host-takeover vector". The posture is explicit —
*hard-block the catastrophic, warn-but-allow the merely risky* so a trusted admin keeps their power:

| Hard-blocked | Warned (overridable with a force flag) |
|---|---|
| Mounting the Docker socket | Host path outside the managed storage root |
| `/`, `/etc`, `/proc`, `/sys`, `/boot`, `/dev`, `/run`, `/var/run` | Image from a registry outside the trusted set |
| The app's own install tree **or any ancestor of it** | Moving tag (`:latest` or untagged) instead of a digest/pin |
| Relative paths; malformed image references | |

The detail worth stealing: **paths containing a colon are rejected outright**, because the colon is
the bind-mount delimiter and Docker would re-split the string into a *different* mount than the one
validated — a parse-differential bypass. The guard re-checks this even though the validator already
does, so it "self-defends for any caller that skips validation". Defaults cap custom containers at
1 GB / 1 CPU unless overridden.

This corrects the Phase 1 characterisation of the guard as thin: it is small but deliberate, and
the block/warn split plus validate-what-will-actually-be-parsed are the reusable ideas.

---

# Phase 2 — AutoBot Comparison

**Focus (set by the owner mid-run): the overlap with AutoBot's air-gapped mode.**

## 0. The overlap is real and already has an owner: #17226

Before anything is proposed, the prior art: [#17226](https://github.com/mrveiss/AutoBot-AI/issues/17226)
(open, filed 2026-09-21) — *"air-gapped operation is achievable by hand but is not a mode, and
nothing tests that it holds"* — already carries five acceptance criteria: one documented switch that
forces the underlying offline flags, an enumeration of every runtime external dependency with a
pre-seed procedure, a test asserting zero outbound DNS on a cold start, loud failure naming the
missing artefact, and deployment-doc coverage.

Everything below is therefore scoped as **what the reference work adds to #17226**, not as a new
air-gap proposal. Three of its mechanisms fall inside #17226's existing ACs and should be absorbed
as implementation notes; two fall outside it and are genuinely new.

Verified independently while framing this:

| Claim in #17226 | Re-verified | Evidence |
|---|---|---|
| `TRANSFORMERS_OFFLINE` defaults False | holds | `autobot_shared/ssot_config.py:2138` |
| No single switch forces the HF offline family | holds | `HF_HUB_OFFLINE` appears **once in the repo**, inside a test — `autobot-backend/system_benchmarks_performance_test.py:376`; `HF_DATASETS_OFFLINE` zero hits |
| ~10 `from_pretrained` sites | **13 non-test files** | `grep -rl from_pretrained --include=*.py`, tests excluded |

One nuance #17226 does not record: the cold-boot-without-network *technique* already exists in that
single test, which socket-patches and additionally sets `HF_HUB_OFFLINE` because "a keep-alive
connection could evade the socket patch" (#16404). The AC asking for a zero-DNS cold-start test has
a working local precedent to generalise from, rather than needing invention.

## 1. Offline is a *detected state*, not only a flag — and our detector answers a different question

**What the reference work does:** connectivity is probed against a well-known external endpoint,
with a fallback chain to other endpoints the app already contacts, overridable by env var (which
wins) or a UI setting — explicitly because the primary probe target is commonly firewalled.

**What AutoBot has** — audited, not assumed:
`autobot-frontend/src/composables/useNetworkStatus.ts` is a real, tested implementation with a
three-way feature taxonomy (`local-only` / `requires-network` / `prefers-network`,
`useNetworkStatus.ts:37`), a 30 s singleton probe loop, a two-consecutive-failure threshold so one
slow response cannot flip the whole app offline (`:56-69`), and browser online/offline event
handling. It has unit tests (`__tests__/useNetworkStatus.test.ts`).

**The delta, and it is a correctness bug for air-gap rather than a missing feature:** the probe
targets `${getApiBase()}/health` (`useNetworkStatus.ts:72`) — it answers *can the browser reach the
backend*, i.e. LAN reachability. In a fully air-gapped install the backend is perfectly reachable,
so the probe reports **online**, and every feature classified `requires-network` renders as
available while having no internet at all. The taxonomy is sound; it is wired to the wrong signal.

Compounding it — and stated precisely, because a first pass overstated this: the *composable* has
real consumers — `components/ui/OfflineBanner.vue`, mounted app-wide at `App.vue:533`, and
`composables/useActionQueue.ts`, a localStorage-persisted retry queue for actions submitted while
offline. What has **no consumers is the `FeatureConnectivity` taxonomy itself**: outside the
composable and its tests, no component declares `local-only` / `requires-network` /
`prefers-network`, so `isFeatureAvailable()` is never consulted by a UI surface. (#6566, closed,
previously called this dead infrastructure; the banner and queue landed, the classification did
not.)

- **Visible benefit:** features that cannot work air-gapped grey out with a reason instead of
  failing at call time.
- **Hidden cost:** every UI surface must be classified, and a wrong classification is worse than
  none — a `local-only` feature mislabelled `requires-network` disappears in exactly the
  deployment it was built for. Needs a default-open policy (unclassified = available).
- **Verdict:** adopt-with-conditions — two distinct signals (`backendReachable`, `internetReachable`),
  not one `isOnline`; classification rolled out per surface, not big-bang.
- **Effort:** moderate (backend probe + signal split trivial; classifying surfaces is the cost).

## 2. Silent fallback is the anti-pattern #17226 is already arguing against

AutoBot's container execution **silently falls back to uncontainerized `LocalBackend` subprocess
execution when the Docker daemon is unreachable** (`autobot-backend/api/sandbox_health.py`,
`_docker_sdk_present` / `_daemon_reachable`). On an air-gapped or hardened host that is a security
posture change happening quietly, and it is the same failure shape #17226's AC names: *"startup
fails loudly with a named missing artefact rather than attempting a fetch."*

The reference work's equivalent gate refuses to proceed and records *which* precondition failed,
with a severity that distinguishes "retry later" from "count this against me" (see Addendum §2).

- **Verdict:** adopt the principle, and widen #17226's loud-failure AC to cover **capability
  degradation**, not only missing model artefacts.
- **Effort:** trivial to surface (health endpoint already computes both booleans); the policy
  decision — refuse vs. warn — is the real work.

## 3. The pre-seed manifest #17226 asks for is half-built already — and the half that exists is the hard half

**What the reference work does:** every downloadable artefact — map regions, archive categories,
curated content packs — is a **versioned in-repo JSON manifest**. "What content exists" is a diff,
not a runtime API call. Its `TRUSTED_REGISTRIES` / digest-pin warnings push the same way for images.

**What AutoBot has** — audited:

| Piece | State | Evidence |
|---|---|---|
| HF model artefacts pinned by revision **and** SHA-256 weight digest, verified post-download, fail-closed | **exists, and is better than the reference work** | `autobot_shared/pinned_model_registry.py` — `PinnedModel{revision, weight_digests}`, `get_pinned_revision():134`, `verify_cached_model():158` |
| Coverage of that registry | **6 models** | `_REGISTRY` keys: CLIP, wav2vec2, whisper-base, BLIP-2, CodeBERT, speaker-diarization-3.1 |
| Call sites that load models | **13 non-test files** | `grep -rl from_pretrained --include='*.py'`, tests excluded |
| In-repo manifest for *builtin skills* | exists — good precedent | `autobot-backend/skills/builtin/*/SKILL.md` (12), loaded by `skills/registry.py` with `_SOURCE_PRIORITY = {builtin:100, custom:50, hub:30, external:20}` — in-repo beats remote on collision |
| In-repo catalogue of **downloadable models/content** | **absent** | `config/llm_models.yaml` (502 lines) configures routing/params for *already-reachable API models*, not pullable weights; greps for `model_catalog`, `models.json`, `content_catalog` → 0 hits |
| Bulk pre-seed / prefetch command ("download everything this install will need") | **absent** | `grep -rliE 'preseed|pre_seed|prefetch|seed_models|download_all_models'` → hits are unrelated cache-warming (`memory/manager.py`, `utils/advanced_cache_manager.py`); no model-seeding entry point |

**The delta is narrow and concrete.** #17226 AC#2 ("every runtime external dependency enumerated,
with a documented pre-seed procedure") does not need a new subsystem — it needs the pinned registry
extended from 6 entries to full coverage of the 13 load sites, plus one command that walks the
registry and fetches. The registry's design already does what a naive content manifest cannot:
digest verification, so a sneakernet-delivered cache can be *proved* correct rather than trusted.

Caveat worth recording: `repo_tests/transformers_resume_download_guard_test.py` shows
`resume_download` was deliberately removed from all 18 call sites (transformers 5.15.1) — AutoBot
**traded resumability for fail-closed integrity**. For air-gapped pre-seeding over a slow or
metered link, that trade bites, and any pre-seed command must plan around it (fetch to a staging
area, verify, then move) rather than re-introducing resume.

- **Visible benefit:** an operator can enumerate and stage every artefact before disconnecting.
- **Hidden cost:** the registry becomes a maintenance obligation — a new `from_pretrained` site
  that skips it silently re-opens the hole. Needs a guard test (`from_pretrained` call sites ⊆
  registry) or the enumeration rots. AutoBot already has ratchet/guard machinery for exactly this.
- **Verdict:** adopt — as implementation notes on #17226 AC#2, not as a new issue.
- **Effort:** moderate.

## 4. Large downloads bypass the job system AutoBot already has

**What the reference work does:** every slow thing is a queued job — downloads, tile extraction,
embedding, model pulls, dataset ingestion — and the update pre-flight *counts in-flight downloads*
as a reason to defer (Addendum §2).

**What AutoBot has:** a mature Celery + Beat stack (`autobot-backend/celery_app.py`, ~20 beat
entries, queues `celery`/`deployments`/`memory`/`analytics`), a documented canonical progress
primitive (`TaskExecutionTracker`, per `docs/architecture/async-work.md`), and Celery-backed
knowledge reindexing with `update_state(PROGRESS)`.

**And yet the one multi-gigabyte path skips all of it:** `POST /api/adapters/ollama/pull`
(`autobot-backend/api/adapters.py:109-135`) streams progress through the live HTTP response for as
long as the client stays connected — no Celery task, no job ID, no persisted progress, no resume,
and **no free-disk precheck** (`grep -n 'disk_usage\|free_space'` over that file and
`llm_shared/adapters/ollama_adapter.py` → 0 hits). It also has **no frontend caller** outside the
generated OpenAPI types, so it is unreachable from the GUI today.

This matters for air-gap twice over: the pre-seed step is exactly a large download, and the
reference work's disk pre-flight (ask the registry for the image's size *before* pulling) is the
mechanism that stops a half-staged artefact from filling the disk of a machine nobody can reach.

- **Verdict:** adopt-with-conditions — route model pulls through Celery + `TaskExecutionTracker`
  (the canonical primitive, not a third ad-hoc Redis job dict — `api/knowledge_vectorization.py`
  already added a second scheme, which is the drift to avoid), and add a free-space precheck.
- **Hidden cost:** low — the queue, the tracker and the workers already exist; this is wiring an
  outlier onto an existing rail, and it removes a bespoke streaming path rather than adding one.
- **Effort:** moderate.

## 5. The backend has no "am I online" primitive at all — this is the core new gap

**What AutoBot has:** one hardcoded WAN check —
`autobot-backend/utils/system_validator.py:832-851`,
`socket.create_connection((NetworkConstants.PUBLIC_DNS_IP, 53))`, where `PUBLIC_DNS_IP` is a static
class attribute `"8.8.8.8"` (`autobot_shared/network_constants.py:178`).

Every property the reference work's probe has, this one lacks:

| Property | Reference work | AutoBot |
|---|---|---|
| Configurable endpoint | env var wins over UI setting | hardcoded constant |
| Fallback chain when the primary is firewalled | yes, falls back to endpoints the app already contacts | none |
| Exposed as reusable runtime state | yes | no — one-shot startup diagnostic |
| Alters behaviour | drives offline UX | **warning log only** |

`grep -rniE "is_online|offline_mode|network_check" --include='*.py'` returns no real symbol (only
alembic's unrelated `context.is_offline_mode()` at `migrations/env.py:116`).

Consequence, stated plainly: **a fully air-gapped backend host is indistinguishable from a healthy
one.** Cloud-provider degradation happens only *reactively*, as a side effect of each provider's own
failed HTTP health check inside `ProviderRegistry._check_health_cached`. Nothing proactively says
"this box has no WAN" and adapts — skipping cloud-provider health checks, hiding web-research
surfaces, or refusing to start a fetch that cannot succeed.

Two partial precedents exist and should be reused rather than re-invented:
`autobot-backend/utils/graceful_degradation.py` already models `DegradationLevel.OFFLINE` with
consecutive-failure and error-rate thresholds (`:36`, `:519`) — but is wired **only** to the Claude
API path (`utils/claude_api_integration.py`). And `autobot_shared/http_egress_guard.py`
(`EgressBlockedError`, `_assert_egress_allowed()`, over `url_safety.is_public_url`) already
intercepts every guarded outbound request — it decides *where* traffic may go (anti-SSRF), and is
the natural chokepoint at which a mode could make the answer "nowhere".

- **Visible benefit:** air-gap becomes an observable, testable state rather than an operator claim.
- **Hidden cost:** a probe that is wrong in the *pessimistic* direction disables working features;
  it needs the reference work's hysteresis (the frontend already has a 2-failure threshold,
  `useNetworkStatus.ts:56-69` — reuse that shape, don't invent a second one).
- **Verdict:** adopt — as a **new acceptance criterion on #17226**, since its current ACs cover the
  static switch but not the detected state. Specifically: a backend `internet_reachable` signal
  with a configurable endpoint + fallback list, surfaced through the existing egress guard, and a
  mode where the guard denies by policy rather than by probe.
- **Effort:** moderate.

## 6. What AutoBot already does better

| Area | Why ours wins |
|---|---|
| **Artefact integrity** | The reference work only *warns* on a moving `:latest` tag and trusts a registry allowlist. AutoBot pins revision **and** SHA-256 weight digest and verifies after download, fail-closed (`pinned_model_registry.py:158`). Digest beats allowlist — a pre-seeded cache can be proven, not trusted. |
| **Local-first inference as doctrine, not default** | Ollama is registered **first, always, regardless of API keys** (`provider_registry.py:544-559`), cloud providers register only when a key is present (`:565-620`), and `set_fallback_chain()` documents "local providers should appear before cloud providers to honour the local-first philosophy" (`:121-128`). The reference work makes the local runtime a default; AutoBot makes it a structural invariant. |
| **Inference-backend breadth** | `custom_openai.py` covers vLLM, llama.cpp server, LM Studio, Jan.ai and Ollama-in-compat-mode over a shared `OpenAICompatibleProvider` base, plus a native in-process vLLM provider. The reference work offers local-runtime-or-OpenAI-compatible and says the remote host is the user's problem. |
| **Background work** | Celery + Beat (~20 scheduled entries) + a documented canonical progress primitive. The reference work's queue is comparable; our scheduler coverage is broader. |
| **Egress policy** | `http_egress_guard.py` enforces an outbound-address policy on the shared client. The reference work has no egress policy at all — it simply does not call out much. |
| **Auth** | The reference work ships **no authentication by design**. AutoBot admin-gates plugin install/load/unload and sandbox execution (`check_admin_permission`, `auth_middleware.py:962`). Not close. |
| **Container hardening** | Spawned containers get `network_mode: none`, `read_only`, `no-new-privileges`, `cap_drop: ALL`, memory/CPU limits (`secure_sandbox_executor.py:735-756`), and images are operator-fixed allowlists — no user-supplied image path exists. The reference work permits arbitrary user images with block/warn guardrails. |

**No mandatory egress exists:** `grep -rliE "license_key|license_server|activation_server|phone.?home"`
→ **0 hits**; the only "telemetry" middleware reads internal Prometheus CPU load, not a vendor
endpoint; Ollama unreachable at startup is a warning, not a failure
(`startup_validator.py:296-303`). The air-gap claim is substantively true today — it is the
*mode and the proof* that are missing, exactly as #17226 says.

## 7. Discovered problems outside the air-gap scope (must not be dropped)

**7a. `gpu_optimization/benchmarking.py` does not benchmark anything.** Every function in
`autobot-backend/utils/gpu_optimization/benchmarking.py` returns hardcoded constants with
`# Simulated` comments — `measured_bandwidth = 480.0` GB/s (`:31`),
`measured_tflops = 27.5` (`:54`), mixed-precision `speedup_factor = 1.8` (`:77`), Tensor-Core
`speedup_factor = 3.5` (`:100`), each preceded by an `asyncio.sleep` to "simulate test time". The
module's name and docstrings claim real measurement. Any decision trusting it is silently wrong on
any hardware unlike the machine those numbers came from. The genuinely-real detection lives
elsewhere (`utils/model_optimization/system_resources.py` via `psutil`/`pynvml`,
`utils/gpu_optimization/gpu_detection.py` via `nvidia-smi`/`rocm-smi`/sysfs) — this is a measurement
that reports *nothing found* as *a number*, which is the failure mode `MEASUREMENT_DISCIPLINE.md`
exists to prevent. **Needs an issue.**

**7b. Plugin code runs unsandboxed and in-process, and the capability model is declared but not
enforced.** `PluginLoader._import_plugin_class` (`autobot_shared/plugin_sdk/loader.py:522`) imports
third-party plugin code — installable via `plugin_install.py::install_from_zip` /
`install_from_git` — directly into the FastAPI process via `importlib`, with full backend
privileges. `plugin_sdk/capabilities.py` defines `Capability`, `TrustTier` and a
`CapabilityChecker` with a Redis audit stream, but the audit found **no call site where
`CapabilityChecker.check()` gates a plugin operation** at runtime outside the admin
`/approve-capabilities` endpoint; `trust_tier` is self-declared in the manifest with no signature
verification. Install/load are admin-gated, which bounds the exposure — but a loaded "community"
plugin has core-code blast radius. **Needs an issue** (check for an existing one first).

**7c. Marketplace auth is uneven.** `GET /marketplace/categories` (`api/marketplace.py:412`) and
`GET /marketplace/installed` (`:472`) have **no** auth dependency at all; `POST /marketplace/install`
(`:496`) requires only `get_current_user`, not admin — though activation still needs the
admin-gated `/plugins/{name}/load`. **Needs an issue.**

**7d. Container orchestration is triplicated.** `SecureSandboxExecutor`, `DockerBackend` and
`DockerTaskWorkspace` each open their own `docker.from_env()` and duplicate the hardening flags —
`docker_task_workspace.py`'s own docstring admits it "copies the exact constraint set" from the
sandbox executor "so the two paths can never diverge independently", i.e. drift is being prevented
by hand. A shared constraint constant would make divergence impossible rather than merely
discouraged. **Needs an issue.**

**7e. Two parallel progress-tracking schemes.** `docs/architecture/async-work.md` names
`TaskExecutionTracker` as canonical, but `api/knowledge_vectorization.py` tracks progress in its own
ad-hoc Redis job dict while `tasks/knowledge_tasks.py` uses Celery `update_state`. Third scheme
would arrive with model-pull work (§4) if not consolidated first. **Needs an issue.**

**7f. The pluggable vector-store interface has exactly one implementation.**
`knowledge/backends/base.py` was built to decouple from ChromaDB (#5062); only ChromaDB adapters
and an in-memory test double exist. Any air-gap story assuming vector-backend swap-ability does not
hold in code. **Record as a known limitation, not necessarily an issue.**

## 8. Self-update: we solved the harder half; they solved the half we skipped

This is the closest and most useful comparison in the whole exercise. AutoBot's built-in updater
lives in `autobot-slm-backend/api/code_sync.py` (mounted `/api/code-sync`, `autobot-slm-backend/main.py:697`) with
`POST /self-update` (`:3453`) and the one-click `POST /update-all` (`:5856`); OS-package updates are
a separate domain in `api/updates.py`.

### Where AutoBot is ahead

| Mechanism | AutoBot | Reference work |
|---|---|---|
| **Not killing yourself mid-update** | The ansible run is detached into a **transient systemd service in `system.slice`** — deliberately not a `--scope`, so it survives `systemctl restart autobot-slm-backend` (`services/playbook_executor.py:46-63`, `_prepare_detached_run:877-926`); output is file-backed because a pipe dies with the parent (`:111-121`) | A privileged sidecar container holding the Docker socket, polling a request file |
| **Blast radius of the executor** | systemd unit, no Docker socket | Docker socket = full host control, permanently mounted |
| **Surviving the restart** | DB-persisted resume plan (`api/_resume_plan.py`), replayed at boot by `resume_update_all_orchestration()` (`autobot-slm-backend/main.py:290-296`) | Sidecar simply continues; no resume state |
| **Knowing what happened** | `services/self_update_log_reader.py::read_self_update_verdict():232` parses `PLAY RECAP` post-hoc — because the triggering process is dead before the run ends — and handles logrotate truncation (`:41-76`) | Sidecar logs |
| **Conservative GC** | `_RELEASE_KEEP` (default 3) prunes frontend builds but **excludes whatever `current`/`previous` symlinks resolve to** (`services/slm_frontend_build.py:131-150`); `_SNAPSHOT_KEEP` (default 3) prunes oldest-first (`api/code_sync.py:2449-2464`) | Enumerates compose-managed images, refuses `prune -a`, never `rmi -f` — same instinct, ours is more granular |

AutoBot's detach mechanism is strictly better than the sidecar: same problem, no privileged socket.

### Where the reference work is ahead — and it is the entire decision layer

| Gate | Reference work | AutoBot |
|---|---|---|
| Free disk before applying | asks the registry for the target image's size for the host arch, compares to free space | **absent on the self-update path** — `grep -n disk playbooks/update-all-nodes.yml` → 0 space checks. It exists for *OS updates* (`ansible/apply-system-updates.yml:29-38`, <5 GB fails) and *provisioning* (`pre-deployment-validation.yml:29-30,136-158`, 10 GB min) — just not where self-update runs |
| Maintenance window | user-configured start/end, wrap-around aware | **model exists, disconnected** — `MaintenanceWindow` (`models/database.py:507`, `api/maintenance.py`) gates the *reconciler* (`services/reconciler.py:692-695`) but `grep -n MaintenanceWindow api/code_sync.py api/updates.py` → **0 hits** |
| Cool-off / soak after a release | `cooloffHours`, malformed config falls back to default, explicit 0 honoured | **absent** — `grep -rn "cool.?off\|cooldown"` over the update paths → 0 hits |
| Major vs minor approval | major always manual | **absent** — code-sync is commit-hash based, no semver. `UpdateInfo.severity` exists (`models/database.py:300`) but `apply_updates` never branches on it; `UpdatePolicy.FULL/SECURITY/MANUAL` (`services/manifest_loader.py:161-201`) is reported by `GET /nodes/{id}/update-policy` and consulted by **nothing** |
| "No other job in flight" | counts in-flight downloads and app installs as `skip`-severity blockers | **partial** — `fleet_sync_guard.py` locks `/fleet/sync`, `_update_all_start_lock` locks `/update-all`, but plain `POST /self-update` → `resolve_and_queue_self_update` (`:3417-3450`) takes **neither**; nothing stops it racing `/update-all` or itself |
| Blocker severity taxonomy | `skip` (retry, no penalty) vs `failure` (counts toward auto-disable backoff) | absent — there is no backoff to protect |
| Dry-run of the decision | three modes incl. frozen clock + canned releases, CI-wirable, exits non-zero | **absent** — the Ansible layer *has* `dry_run` but the caller hardcodes it off (`api/updates.py:948`, `"dry_run": "false"`, never a parameter). `grep -rln "freezegun\|freeze_time"` → **0 hits repo-wide** |
| Decision as a pure, side-effect-free verdict | `Decision{outcome, reason, …}` with injectable clock/releases/preflight | absent — decision logic is interleaved with execution, which is *why* no harness is possible |

**Root cause of the whole right-hand column:** AutoBot's update decision is not a separable value.
The reference work's one structural choice — *compute a verdict object, then act on it* — is what
makes every gate above cheap to add and cheap to test. Ours has ~20 incident-driven regression
tests named after issue numbers (`tests/api/test_code_sync_*`, `test_*_<issue>.py`) rather than a
scenario matrix, so each new "should this proceed?" branch ships with no harness to test it against.

### The unfinished work this exposes

`ansible/roles/dependency_patching/` is **fully implemented** — venv tar.gz backup, 7-day retention
(`autobot-slm-backend/ansible/roles/dependency_patching/defaults/main.yml:10-12`), and a `playbooks/rollback-dependencies.yml` — and is **invoked by
nothing**: `grep -rln "dependency_patching" api/*.py services/*.py` → 0 hits;
`grep -n dependency_patching playbooks/update-all-nodes.yml playbooks/system-update.yml` → 0 hits.
Meanwhile the whole-machine self-update path it was built for has **no rollback at all** — the real
`_snapshot_component` / `_rollback_component` pair (`api/code_sync.py:2467-2584`, with a genuine
health gate at `:2592-2636` so a slow-but-healthy restart is never wrongly reverted) is called only
from the per-component drift-resolve path (`:3032`), never from `_ansible_self_update`.

Per the project's own rule — *debris is unfinished work; cleanup means finishing it* — the
`dependency_patching` role is not dead code to delete, it is a rollback mechanism to **wire into
`update-all-nodes.yml`**.

- **Verdict:** adopt the decision-layer pattern — **high value, and it is the single highest-value
  item in this report**. Refactor the self-update decision into a side-effect-free verdict
  (`outcome` enum + `reason` + injectable clock/inputs), then hang the existing-but-disconnected
  gates (`MaintenanceWindow`, `UpdatePolicy`, a disk check, a cool-off) off it, and add the
  scenario suite.
- **Hidden cost:** honestly assessed — this is a refactor of a 6,025-line router that currently
  works, on the path that updates production. It must be done decision-first (extract the verdict,
  assert the current behaviour is unchanged, *then* add gates), or it trades a missing gate for an
  outage. `freezegun` becomes a new test dependency.
- **Effort:** significant.

## 9. Specific AutoBot files affected

| File | Change |
|---|---|
| `autobot_shared/pinned_model_registry.py` | Extend `_REGISTRY` from 6 entries toward the 13 `from_pretrained` load sites; add a guard test asserting call sites ⊆ registry |
| *(new)* pre-seed command | Walk the registry, fetch + `verify_cached_model`, stage-then-move (no `resume_download`, per `repo_tests/transformers_resume_download_guard_test.py`) |
| `autobot_shared/ssot_config.py:2138` | One offline switch that forces `TRANSFORMERS_OFFLINE` + `HF_HUB_OFFLINE` (+ `HF_DATASETS_OFFLINE`) together — #17226 AC#1 |
| `autobot_shared/http_egress_guard.py` | Chokepoint for the offline mode: deny by policy, raising `EgressBlockedError` with the named artefact, rather than attempting a fetch |
| *(new)* backend connectivity probe | `internet_reachable` with configurable endpoint + fallback list; replaces the hardcoded `8.8.8.8:53` in `utils/system_validator.py:832-851` / `autobot_shared/network_constants.py:178`; reuse the 2-failure hysteresis shape from `useNetworkStatus.ts:56-69` |
| `autobot-backend/utils/graceful_degradation.py` | Generalise `DegradationLevel.OFFLINE` beyond the Claude-API path |
| `autobot-frontend/src/composables/useNetworkStatus.ts` | Split `isOnline` into `backendReachable` + `internetReachable`; keep `OfflineBanner.vue` / `useActionQueue.ts` on the former |
| Frontend surfaces | Declare `FeatureConnectivity` per surface (default-open: unclassified = available) so `isFeatureAvailable()` finally has consumers |
| `autobot-backend/api/adapters.py:109-135` | Route Ollama pulls through Celery + `TaskExecutionTracker`; add a free-space precheck; wire a frontend caller (currently unreachable from the GUI) |
| `autobot-backend/api/sandbox_health.py` | Make the Docker→`LocalBackend` fallback loud, not silent |
| `autobot-slm-backend/api/code_sync.py` | Extract a side-effect-free update verdict; take a lock on `POST /self-update` (`:3417-3450`); call `_snapshot_component`/`_rollback_component` from the whole-machine path |
| `autobot-slm-backend/ansible/playbooks/update-all-nodes.yml` | Add the free-disk gate that `apply-system-updates.yml:29-38` already has; wire in the orphaned `dependency_patching` rollback role |
| `autobot-backend/utils/gpu_optimization/benchmarking.py` | Measure, or remove the claim — see §7a |

## 10. Bottom line

The reference work is **not ahead of AutoBot on air-gap capability** — ours has stronger integrity
pinning, a real egress guard, local-first inference as a structural invariant, authentication, and
a self-update executor that needs no privileged socket. It is ahead on **one thing**: treating
"should this happen right now?" as a *value you can compute, inspect and test* rather than control
flow you have to run. That single pattern is what unlocks the pre-flight gates, the cool-off, the
window, the backoff and the dry-run harness — and it is directly reusable for the air-gap mode
#17226 asks for, whose ACs ("fail loudly with a named missing artefact", "a test asserts a cold
start performs no outbound DNS") are decision-shaped in exactly the same way.

Recommended sequencing: (1) fold §1/§3/§5 into #17226 as implementation notes and one new AC for
the detected-state probe; (2) file §7a–§7e separately — they are outside air-gap scope and must not
ride on it; (3) treat §8 as its own umbrella, decision-extraction first.
