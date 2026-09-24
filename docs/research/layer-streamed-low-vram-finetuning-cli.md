---
tags:
  - research
---

# Source Analysis: A Single-Config, Layer-Streamed LLM Fine-Tuning CLI

Phase 1 only — source analysis. AutoBot comparison **not started** (awaiting go-ahead).

## What It Is

An independently maintained, community-carried, permissively licensed CLI that reduces
LLM fine-tuning and post-training to one declarative config file and one command. Mature
and very actively developed: a test corpus larger than its source, daily pushes, a busy
issue tracker, and a recent release in which every merged pull request came from outside
the maintainer.

Its implementation language, licence name, repository metrics and internal layout are
omitted deliberately -- the owner ruled on 2026-09-22 that a source's own stack and paths
are identifying, not just its name, and several of those figures together identify a
project uniquely. The same treatment was applied to
`local-first-agent-runtime-context-frugal-loop.md`. Scope spans SFT, six preference objectives, GRPO/GSPO
reinforcement learning, NF4/QLoRA quantization, adapter management, evaluation and
benchmarking, a web UI, an MCP server, cloud offload, a plugin system and a recipe catalog.
Its headline capability is training an 8B model on a 4 GB consumer GPU by streaming frozen
base layers through a small VRAM buffer pool.

## Architecture & Key Patterns

- **`src/` package split by concern**: `commands/` (CLI surface), `config/` (Pydantic v2
  schema as declared single source of truth), `trainer/` (one module per backend),
  `utils/` (streaming runtime, shard format, adapter wiring), `monitoring/` (callbacks,
  trace log, dashboard), `plugins/`, `mcp_server/`, `ui/` (HTTP + SSE + static JS),
  `cloud/`, `registry/`, `recipes/`, `eval/`, `bench/`.
- **Light core, heavy extras.** Base install carries only CLI/validation/formatting
  dependencies; the training stack (tensor framework, model library, adapter and
  preference-trainer libraries) lives behind an optional extra and is lazy-imported
  *inside functions*, never at module top — so the light CLI path can plan, validate and
  forecast a run without importing the training stack at all.
- **Pure planner / runtime / on-disk-format split** for the flagship feature: arithmetic,
  tier choice and the architecture allowlist in a torch-free module; buffer pool, weight
  source, prefetch scheduler and layer wrapper in a second; checkpoint sharding in a third.
  Shared constants are re-exported from the owning module rather than redeclared, with the
  drift risk named in a comment.
- **Declared-not-inferred capability matrix.** Which config fields a given (task, backend)
  pair actually *reads* is a hand-maintained table, because three inference strategies were
  tried and measured as inadequate (import-graph reachability detects none of the known
  gaps; single-module reads invent false gaps for fields handled in helpers; dry-run exits
  before a trainer exists, so runtime tracing observes nothing). Tests bound the table's
  drift; unreviewed pairs report *nothing* rather than guessing.
- **Config-key detection separated from config-key policy**: one pure module finds keys the
  schema cannot place and suggests the intended field; whether that is a warning or a hard
  failure is the caller's switch.
- **Plugin discovery without execution**: third-party entry points are enumerated and
  described from package metadata alone; the module is imported only after explicit opt-in,
  and the enabled state persists across processes.
- **Callback-based monitoring** (`pre_train` / `post_train` / `pre_step` / `post_step`)
  shared by the trainer, the plugin layer, the tracker and the live dashboard.

## Notable Implementation Details

1. **Layer streaming.** The frozen base sits in pinned host RAM (or a disk tier) and is fed
   to the GPU one decoder layer at a time through a small pool of pre-allocated VRAM
   buffers; embeddings and an untied output head share a second single-slot pool. Peak VRAM
   is therefore bounded by one decoder layer plus one vocabulary matrix instead of the whole
   model, with only adapters, their gradients and optimizer state resident.
2. **Constants labelled by provenance.** A safety-margin constant is commented as *"a chosen
   safety margin, not a measured bound"*, explicitly distinguishing it from the measured
   constants beside it, and the failure mode it guards (unevictable pinned host memory plus
   page-cache pressure defeating a dynamic free-RAM check) is written down with its issue.
3. **Silent-config-drop detection.** Keys no model declares used to be dropped silently, so a
   misspelled quantization or length key changed nothing while the run reported valid. The
   detector walks the raw mapping against the model tree, suggests the nearest declared
   field, bounds the scan, escapes key names before they reach the terminal, and honours a
   legacy root-level remap so a historically valid spelling is not refused. The release that
   flips warn→refuse is a single constant that the CLI message, the docs line and the
   deadline test all read.
4. **Streaming-transport auth without a token in the URL.** Event-stream endpoints accept
   either a bearer token or a single-use ticket: an authenticated POST mints a 30-second
   random ticket into a lock-guarded store, and consumption pops it (expiry sweep on every
   access), so the credential that appears in a query string is one-shot and short-lived.
5. **Capability probes instead of version checks.** A dependency that removed a constructor
   argument across several releases rather than one is validated by *constructing* each
   config with the exact keyword arguments the wrappers pass, per version — the
   compatibility floor is derived from that table rather than from a spot check.
6. **Defect-first release notes.** The current release leads with the failure it repairs —
   the same config silently trained a different recipe on one backend, because six
   validated, documented options were read by nothing there.

## Strengths

- Tests outweigh source by mass; nearly every module docstring names the issue that
  produced it, giving unusually high code-to-rationale traceability.
- Honest defaults: unreviewed backend pairs report nothing rather than guessing, the
  flagship feature is opt-in and labelled beta behind an architecture allowlist, and stale
  measurements are annotated as stale in the README with the issue tracking re-measurement.
- Benchmarks ship in-repo as raw result files, plus a notebook that caps the process to
  4 GB and asserts a streamed model is bit-identical to a resident one — a claim a reader
  can re-run rather than trust.
- Breaking changes are announced one release ahead with the deadline encoded as a constant.
- Operational hygiene: multi-OS × multi-Python CI matrix, pre-commit config, code owners,
  security policy, translated READMEs, changelog fragments.

## Weaknesses / Limitations

- **File sizes are extreme.** The config schema is a single 312 KB module; four more files
  exceed 95 KB (data commands, streaming runtime, recipe catalog, SFT trainer). There is no
  size ratchet — under AutoBot's 600-line cap most of this hot path would be non-compliant,
  and the schema being both SSOT and one file means every new field touches it.
- **The flagship number is stale by the project's own admission**: the headline throughput
  and peak-VRAM figures predate a correctness repair that cost measurable throughput at
  larger sizes, and have not been re-measured on the 4 GB card since; the re-measurement is
  an open issue.
- **Capability-matrix coverage is one pair** (one task on one backend). Every other
  combination is unreviewed, so the class of bug it exists to catch remains open elsewhere —
  and that class had already been filed at least four times, one field at a time.
- **Beta constraints on the headline feature**: opt-in, architecture-allowlisted, and gated
  by a RAM-headroom fraction that is an unmeasured judgement call.
- **Surface far wider than its core**: cloud offload, MCP server, web UI, distillation,
  autopilot, environments, experiments and migration all sit in one package, carried largely
  by outside contributors, with ~137 issues open.
- The persisted plugin enable-state file is a new on-disk trust surface for a tool whose
  plugins execute arbitrary code once enabled.

## Visible vs Hidden Metrics

- **Visible:** a large public following; an 8B model trained on a 4 GB laptop GPU at
  roughly 120 tok/s and 3.32 GB peak; a bit-exactness claim against a resident run; a
  citable paper; a multi-OS, multi-interpreter CI matrix; a README in several languages. *Independence:* the throughput figures are
  self-reported and stale; the second-device reproduction is described as independent; the
  strongest artifact is the free-tier notebook that lets any reader reproduce the memory cap
  and the bit-exactness assertion themselves.
- **Hidden:** tight coupling to a fast-moving training stack whose floors need probe-tables
  to maintain; a single-file 312 KB SSOT that every schema change contends on; a
  review-maintained ignore-matrix that rots unless re-reviewed per backend (their own
  regression); layer streaming trading a VRAM constraint for a *host RAM* constraint, where
  pinned unevictable memory plus page-cache pressure can OOM a run that passed the
  free-memory pre-flight; silent fallback for architectures outside the allowlist; a
  feature surface sustained by community PRs rather than a maintainer team.
- **Weighing:** the split is sharp by intent. For adopting the *techniques* — unknown-key
  refusal with suggestions, declared-not-inferred capability tables, pure/runtime module
  splits, single-use stream tickets, light-core/heavy-extras with in-function imports,
  provenance-labelled constants — hidden costs are near zero: each is small, dependency-free
  and portable. For adopting the *tool as a dependency*, the hidden costs dominate the
  visible wins: a pre-1.0 CLI with a stale flagship benchmark, one reviewed backend pair and
  a monolithic config SSOT is an operational bet, not a stable library. Adopt patterns, not
  the dependency.

## Provenance & Safety Notes

- Accessed read-only through the hosting platform's contents and tree APIs. Nothing was
  cloned, and no fetched code was executed.
- The source ships an agent-instruction file. It was read **as data, not followed**, and
  checked for injected instructions: none found — it is an ordinary contributor guide for
  its own repository. That check covers that file plus the ~10 files read for this analysis;
  the remaining ~1,200 files in the tree were **not** scanned.

---

# AutoBot Comparison

Phase 2. Every item below was audited against AutoBot code first; the greps and paths
checked are cited so a reader can tell *nothing found* from *did not look*.

## What We Can Adopt

### A1 — A detector for config keys nobody reads, across both declaration planes

- **Applies to:** [`autobot_shared/ssot_config.py`](../../autobot_shared/ssot_config.py),
  [`autobot_shared/env_registry.py`](../../autobot_shared/env_registry.py) + 9 component
  siblings, [`pipeline-scripts/check_env_var_registry.py`](../../pipeline-scripts/check_env_var_registry.py).
- **Already-exists audit.** `difflib` / `get_close_matches` / `did you mean` / `unknown_key`
  in `ssot_config.py` → **0 hits**. `extra="forbid"` → **0**; `extra="ignore"` → **20**, one
  per settings class, every class reading the same `.env`. A typo'd key is therefore dropped
  in silence and the field keeps its default. We *do* own an env-var registry with types,
  ranges, `deprecated_since` and `replaces` (`env_registry.py:20-30`) enforced by a
  pre-commit hook — but that hook's population is `os.getenv()` call sites only
  (`check_env_var_registry.py:4`), and the pydantic `alias=` plane is not in it.
- **Measured drift between the two planes:** 437 distinct `AUTOBOT_*` aliases declared in
  `ssot_config.py`, 259 names registered in `env_registry*.py`, **404 aliases absent from the
  registry**, 33 names declared in both, and **13 of those 33 disagree on their default** —
  including `AUTOBOT_ENV` (`ssot_config.py:1656` defaults to development,
  `env_registry.py:201` to production), the Postgres database and user, three TLS paths, and
  two service host defaults (one plane loopback, the other a routable LAN address).
- **Visible benefit:** a misspelled key fails loudly instead of silently keeping a default,
  and the two planes stop contradicting each other.
- **Hidden cost:** `extra="forbid"` is *not* the port — the process environment legitimately
  carries unrelated variables, so this must be a detector over the `AUTOBOT_`-prefixed
  namespace plus a plane-reconciliation test, not a pydantic switch. It will fail on hosts
  carrying legacy keys, so it needs a warn→refuse deadline.
- **Verdict: adopt.** The hidden cost is one pure module plus one guard test; the visible
  win is a live correctness defect (13 conflicting defaults) rather than a hypothetical.
- **Effort:** moderate.

### A2 — A declared (setting × provider) support table

- **Applies to:** [`autobot-backend/llm_shared/providers/`](../../autobot-backend/llm_shared/providers/),
  `LLMConfig` in `ssot_config.py:230-565`.
- **Already-exists audit.** No such table exists (`backend_support` / capability-matrix greps
  → none). Confirmed instances of the bug class it catches: `AUTOBOT_CHAT_TEMPLATE` occurs
  **exactly once repo-wide** — its own declaration at `ssot_config.py:377` — while providers
  read `request.metadata["chat_template"]` (`providers/ollama_provider.py:122,220`,
  `providers/vllm_base.py:139`) and the only writers of that metadata key are tests;
  `LLMConfig.timeout` (`:272`) has no provider reader, each provider hardcoding its own HTTP
  timeout (`providers/ollama.py:346-347,458`, `adapters/ollama_adapter.py:75,131`); seven
  tier-model fields (`reasoning_model`, `coding_model`, `rag_model`, `agent_model`,
  `research_model`, `analysis_model`, `planning_model`) have no non-test reader; and three
  aliases are declared twice on different fields — `AUTOBOT_LLM_TIMEOUT` binds both an int at
  `:272` and a float at `:598`, plus `AUTOBOT_DEFAULT_LLM_MODEL` and
  `AUTOBOT_PERMISSION_SYSTEM_V2`.
- **Visible benefit:** an operator can be told which settings the selected provider ignores,
  instead of setting a value that changes nothing.
- **Hidden cost:** a hand-maintained table rots unless a drift test bounds it — the reference
  work regressed exactly this way. It must also start narrow; a table covering every provider
  is one nobody can review honestly.
- **Verdict: adopt-with-conditions** — seed it only with the fields already *proven* unread
  above, and land the drift test in the same change.
- **Effort:** moderate.

### A3 — Explicit opt-in before third-party plugin code is imported

- **Applies to:** [`autobot_shared/plugin_sdk/plugin_manager.py`](../../autobot_shared/plugin_sdk/plugin_manager.py),
  [`autobot_shared/plugin_sdk/loader.py`](../../autobot_shared/plugin_sdk/loader.py).
- **Already-exists audit.** *Discovery* is already manifest-JSON only — `loader.py:248`
  `rglob("plugin.json")` → `:251` `json.load` → `:253` `PluginManifest(**data)`, with no
  import — so we already match the reference work on the listing path. The delta is what
  happens at boot: `plugin_manager.py:106` iterates every discovered manifest, `:121` loads
  it (`loader.py:550` `importlib.import_module`, file-path fallback `:631` `exec_module`)
  and `:123` enables it, wired into startup at
  `autobot-backend/initialization/lifespan.py:1973-1978`. There is no per-plugin opt-in gate,
  enable/disable mutates in-memory status only (`plugin_sdk/base.py:207`), and only plugin
  *config* is persisted (`autobot-backend/plugin_manager.py:693`). Signature, checksum and
  sandbox greps (`sha256|hashlib|checksum|cosign|gpg|signature|sandbox|seccomp|RestrictedPython`)
  over `plugin_sdk/`, `plugin_install.py` and `plugin_manager.py` → **none found**. Separately,
  `loader.py:116` uses `importlib.util.find_spec`, whose own docstring (`:110-113`) records
  that third-party `__init__` code executes during the dependency check.
- **Visible benefit:** plugin code stops executing at boot merely because a directory exists.
- **Hidden cost:** a persisted enabled-state store is new durable state — it needs a system of
  record, an operator approval path, and it falls under the rule that an agent never rewrites
  stored state on its own. It also changes behaviour for existing deployments, which would
  have to enable their plugins once.
- **Verdict: adopt-with-conditions** — the gate is worth it; the persistence design is the
  expensive half and should be specified before either is built.
- **Effort:** significant.

### A4 — A removal deadline for the `?token=` WebSocket fallback

- **Applies to:** [`autobot_shared/websocket_subprotocol.py`](../../autobot_shared/websocket_subprotocol.py).
- **Already-exists audit.** The deadline-as-a-constant pattern is **already owned locally** —
  `autobot-backend/middleware/sunset_legacy_health.py:45` declares a sunset date read by its
  test. It is simply not applied here: `deadline|removal|sunset|deprecat` greps against
  `websocket_subprotocol.py` → **0 hits**. The fallback is deliberate and observable
  (`resolve_ws_token`, one throttled warning per route) but open-ended.
- **Visible benefit / hidden cost:** closes the migration instead of leaving it running
  indefinitely; cost is that a straggler client breaks at the deadline, which is the point
  of announcing one.
- **Verdict: adopt.** **Effort:** trivial.

### Rejected by hidden metrics — layer streaming itself

AutoBot's only resident torch models are an LSTM code-completion model (`#904`,
`autobot-backend/training/completion_model.py`) and the NPU/GPU inference path; LLM work is
delegated to providers rather than trained in-process. Adopting a VRAM-streaming trainer
means owning a training stack we do not have, and inheriting a host-RAM pinning constraint,
an architecture allowlist and a beta feature — real hidden costs against a visible win we
have no use for. **Rejected.**

## What We Already Do Better

1. **WebSocket token transport.** We keep the credential out of the URL entirely —
   `Sec-WebSocket-Protocol: bearer, <jwt>` preferred, with read and echo owned by one module
   (`websocket_subprotocol.py`) and a repo guard failing any module that authenticates a
   socket then calls `.accept(` itself. The reference work's answer to the same problem is a
   30-second single-use ticket, which still puts a credential in a query string and adds a
   lock-guarded expiring store to maintain. Ours also logs fallback use, throttled per route.
2. **A typed env-var registry.** `EnvVarSpec` carries type, default, description, component,
   numeric range, `deprecated_since` and `replaces` (`env_registry.py:20-30`) and a pre-commit
   hook enforces registration of `os.getenv` call sites. The reference work has no equivalent
   registry — its schema is the only plane. (Our defect is the *second* plane, not this one.)
3. **Plugin install-time protections.** Beyond manifest-only discovery, which matches them, we
   validate the plugin config schema with Draft 2020-12 (`loader.py:50`), validate hook names
   (`:344`) and required env (`:347`), extract archives zip-slip- and symlink-safe
   (`plugin_install.py:127`), validate git URL and ref (`:178`, `:192`) and enforce runtime
   capabilities (`plugin_sdk/capabilities.py:197`). The reference work has none of these.
4. **Import hermeticity is measured, not asserted.** We run a sandboxed import guard with a
   frozen shrink-only offender baseline whose detector boundary is written down —
   `repo_tests/import_hermeticity_known_offenders.py` states which events it can see and that
   absence from the list is *not* proof of inertness. The reference work's equivalent rule
   ("no top-level heavy imports") lives in a docstring with no guard.
5. **A file-size ratchet.** Our 600-line cap against their 312 KB single-module config schema.

## Gaps & Opportunities

Prioritised by impact.

1. **Two declaration planes for one concept, already drifted.** 13 of the 33 vars declared in
   both disagree on their default, `AUTOBOT_ENV` (development vs production) worst among them.
   This is a live correctness defect, not a missing pattern. → A1. **Filed: #17419**, sub-issue of umbrella #13264.
2. **Every discovered plugin is imported and enabled at boot**, with no persisted opt-in and no
   signature or checksum check, into the backend process. → A3. **Filed: #17421**, blocked by #17420.
3. **A live bug on the manual plugin-load path.** `autobot-backend/plugin_manager.py:271` calls
   `loader.load_plugin(manifest, plugin_config, grant_capabilities=auto_grant)` but the
   loader's signature is `load_plugin(self, manifest, config=None)` (`plugin_sdk/loader.py:320`)
   and `grant_capabilities` appears nowhere in that module — so the call raises `TypeError`.
   The comment above it (`:265-268`, issue #9049) states that capabilities must be explicitly
   operator-approved and auto-granted only for official plugins, which means the intended
   approval gate is the broken argument. **Filed: #17420.**
4. **Declared-but-unread LLM settings and duplicate aliases** — `chat_template`, `timeout`,
   seven tier-model fields, three aliases bound twice. → A2.
5. **No deadline on the `?token=` fallback.** → A4.
6. **The env-registry hook's green is narrower than it reads.** It proves "no unregistered
   `os.getenv` call site", not "every `AUTOBOT_*` variable is registered" — 404 aliases sit
   outside its population. Worth stating in the hook itself, per our measurement rules.

## Specific Code/Files Affected

| File | Change |
|---|---|
| `autobot_shared/ssot_config.py` | Source of the 437 aliases; fix 3 duplicate aliases and the 13 conflicting defaults |
| `autobot_shared/env_registry*.py` | The second plane; reconcile or make it the single declaration |
| `pipeline-scripts/check_env_var_registry.py` | Extend population to `alias=` declarations; state the boundary in the failure text |
| *(new)* `autobot_shared/config_unknown_keys.py` | Pure detector over the `AUTOBOT_`-prefixed namespace, with suggestions; policy left to the caller |
| *(new)* `autobot_shared/provider_support.py` | Declared (setting × provider) ignore-table, seeded from the proven-unread fields, with a drift test |
| `autobot_shared/plugin_sdk/plugin_manager.py` | Opt-in gate before `load_plugin`; do not enable everything discovered |
| `autobot_shared/plugin_sdk/loader.py` | Accept (or drop) `grant_capabilities`; document that `find_spec` executes package `__init__` |
| `autobot-backend/plugin_manager.py` | Fix the `grant_capabilities` call at `:271` |
| `autobot_shared/websocket_subprotocol.py` | Deadline constant for the `?token=` fallback, read by the warning and a test |
| `autobot-backend/services/incremental_trainer.py` | `:19` top-level `training.completion_trainer` import makes torch eager, defeating this module's own `lazy_torch` use at `:17` |
