# Source Analysis: disk-tiered MoE expert streaming engine

**Date:** 2026-09-12
**Phase:** 1 + 2 (source analysis + AutoBot comparison)

## What It Is

A pure-C inference engine (Apache 2.0, ~2 months old, high-velocity open-source
project) built to run frontier-scale Mixture-of-Experts language models
(hundreds of billions to low-trillions of parameters) on consumer-class
hardware by treating VRAM, RAM, and NVMe storage as one unified memory
hierarchy instead of requiring the full model resident in fast memory. It
streams the small subset of MoE experts actually activated per token from
disk, with a learned cache and prefetch layer sitting on top. It ships a CLI,
an OpenAI-compatible HTTP server, a web dashboard, and a TUI client, and
explicitly documents its own uncertainty: "no SLA on speed, hard guarantee on
semantics." Maturity signals (28k+ stars, 3k+ forks in ~10 weeks, 2k+ commits,
weekly releases, an open experiments log) suggest an active research-driven
project rather than a stable, slow-moving library — treat performance claims
as current-snapshot, not settled.

## Architecture & Key Patterns

- **Single-engine-per-model-family-per-file.** Each supported model family
  (roughly eight, spanning ~7B to ~2.8T parameters) gets its own `.c`
  translation unit with shared headers for tensor views, quantization,
  tokenization, and the expert-store abstraction. No shared "generic
  transformer" abstraction layer — each family's routing/attention quirks are
  implemented directly rather than papered over by a common interface.
- **Storage tiering as a first-class runtime concern**, not a side detail:
  VRAM (optional) → pinned RAM (resident) → NVMe (streamed on demand), with a
  per-layer LRU plus a *learned* hot-store that pins the experts a given
  workload actually routes to, derived from a persisted usage log.
- **Backend plugins behind a vtable**, not `#ifdef` soup: CUDA, Apple Metal,
  and Vulkan are optional accelerators selected at build/run time; CPU-only
  execution is the baseline path and always works.
- **Python launcher, C engine.** The hot path is pure C with zero runtime
  dependencies; Python is only the CLI/orchestration/doctor-script layer
  (environment probing, model family registry, resource planning) — it never
  sits in the token-generation critical path.
- **Storage abstraction with an explicit lease contract.** The expert store is
  a vtable (`lookup` / `release` / `prefetch` / `stats` / `destroy`) with a
  hard rule documented in the header itself: a lookup returns a non-copyable
  lease that must be released exactly once; prefetch is advisory and must
  never evict a leased slot; debug builds assert zero outstanding leases at
  destroy. This is a textbook resource-lifecycle contract enforced by
  convention + debug assertions rather than by the type system (plain C, no
  RAII available).

## Notable Implementation Details

- **"JIT for weights."** The framing is deliberate and apt: a compiler JIT
  doesn't compile the whole program, it watches what actually runs and
  optimizes the hot path. Here, the router's per-token expert selection *is*
  the profiling signal, and placement (which tier an expert lives in) is
  continuously re-optimized against it — including a persisted usage log
  (`.coli_usage`-equivalent) that survives process restarts, so the engine
  measurably gets faster the more a given workload is repeated.
- **Compressed, persisted KV cache.** The attention mechanism used by the
  flagship supported model compresses per-token KV state ~57× (576 floats vs.
  32,768) and persists it to disk across restarts, so a conversation resumes
  "warm" — byte-identical continuation, zero re-prefill — rather than paying
  full prefill cost again.
- **Dual-SSD striping with graceful degradation.** If two drives are present,
  each expert is deterministically hashed to one drive, weighted by each
  drive's measured bandwidth, so prefetch and demand reads always target the
  same drive and nothing is double-cached. The mirror is validated at startup
  (per-file size + header hash must match the primary); a partial or
  mismatched mirror silently falls back per-file rather than failing the run;
  a read error on the mirror at runtime falls back to the primary with one
  warning, not a crash. Sidecars (usage log, KV cache) are deliberately never
  mirrored. This is a well-thought-out degrade-not-fail design for a
  performance optimization that could easily have been implemented as an
  all-or-nothing mode.
- **Lookahead prefetch grounded in a measured number, not a guess.** The
  project measured that routing decisions are ~71.6% predictable one layer
  ahead and built an async prefetch thread on that specific empirical
  finding, rather than a generic "prefetch N tokens ahead" heuristic.
- **Opt-in, measured, reversible speed/fidelity tradeoffs.** A cache-aware
  routing mode (bias expert selection toward what's already resident, within
  a bounded rank window) ships **default-off**, with explicit knobs for how
  much true-top-K fidelity to trade away, and built-in telemetry — cache hit
  rate, swap percentage, agreement vs. true top-K, KL divergence of the
  routing distribution — surfaced specifically so a user can quantify the
  fidelity cost of turning it on. The docs explicitly say "treat as
  experimental... do not default it on."
- **Speculative decoding shipped with its own failure mode documented.** The
  project found that a lower-precision draft head collapses acceptance to
  near-zero and that draft/verify must run the *same* kernel implementation
  or acceptance silently degrades — both fixed and pinned as defaults, with
  the failure mode written up in the issue tracker rather than silently
  patched over.
- **An "open hypotheses" section in the README itself** — a running table of
  things the project believes might be true, what's been measured so far, and
  what would falsify it, explicitly inviting negative results. This is a
  research-log posture baked into the top-level documentation, not just an
  engineering-blog aside.

## Strengths

- Treats storage bandwidth/latency as a real, budgeted resource throughout
  (overlapped I/O, `O_DIRECT`, batch-union of expert reads across a batch)
  rather than assuming memory-speed access and bolting on caching later.
- Faithfulness discipline: optimizations that could change model outputs
  (cache-aware routing, speculative drafting) are opt-in, measured, and
  validated token-exact against a reference implementation; the docs are
  explicit about which levers change semantics vs. which only change
  placement/speed.
- Degrade-gracefully engineering throughout (dual-SSD fallback, partial
  mirrors, disableable speculation) rather than fragile all-or-nothing
  features.
- Unusually honest public documentation of negative/mixed results (a
  regression found in one speculative-decoding configuration, hardware
  classes where an optimization loses) — lowers the risk of an adopter
  inheriting an undocumented footgun.

## Weaknesses / Limitations

- Pure C with zero dependencies is a deliberate tradeoff that buys build
  portability at the cost of implementation velocity and memory-safety
  tooling maturity compared to a Rust/C++ equivalent — the project relies on
  discipline + debug assertions (e.g. the lease-count assert) rather than a
  type system that can enforce the resource contract at compile time.
  Fenced-off, no shared abstraction across the ~8 model-family files means
  each new supported model is substantial bespoke C, which is a real ongoing
  maintenance cost as model architectures multiply.
- Extremely young project (created ~10 weeks before this analysis) with a
  correspondingly high commit/release velocity — useful signal of active
  development, but also means APIs, env-var flags, and file formats are
  plausibly still shifting; not yet a stable target to pin a dependency to.
  125 open issues against ~2k commits is a normal ratio for this stage, not
  a red flag by itself, but not evidence of a settled API either.
- Baseline CPU-only throughput on the largest supported models is very low
  (sub-0.1 tokens/sec) — the headline "runs a huge model on a small box"
  claim is true but the useful-without-a-GPU-cluster performance envelope is
  narrow; most of the exciting numbers require multiple high-end GPUs.
- The learned hot-store / usage-log approach optimizes for *repeated,
  similar* workloads on a *single* machine; it is unclear how it behaves for
  bursty, highly varied, or multi-tenant workloads where the usage
  distribution never stabilizes — the docs don't address this case.

## Visible vs Hidden Metrics

- **Visible:** headline token/sec numbers across hardware tiers (self-reported
  by the project, reproducible via its own published benchmark harness but
  not independently audited by a third party); star/fork counts as a proxy
  for community traction; the "runs a 2.8T model on 32GB" framing.
- **Hidden:** the real adoption cost is the bespoke-per-model-family C
  maintenance burden (no shared transformer abstraction — a new frontier
  model family is a new multi-thousand-line file, not a config change); the
  operational complexity of tuning a multi-tier cache/prefetch/speculation
  system correctly for a given workload and hardware mix (many env-var
  knobs, each requiring its own A/B to get right); the correctness risk
  surface of any of the opt-in fidelity-trading levers (cache-aware routing,
  speculative drafting) if a downstream user enables them without reading
  the telemetry; and the project-youth risk (breaking changes, unproven
  long-term API stability) for anyone embedding it rather than just running
  it standalone via CLI.
- **Weighing:** for a use case that just wants to run one or two of the
  already-supported model families locally via the CLI/server, the hidden
  costs are mostly irrelevant — you consume the tiering/caching machinery as
  a black box. The hidden costs dominate for anyone considering *embedding*
  the engine or *replicating* its tiering architecture in-house: the
  maintenance burden of the per-model bespoke C, and the tuning burden of
  the cache/prefetch/speculation knob surface, are the real price, not the
  headline throughput numbers.

---

## AutoBot Comparison: reference work → AutoBot

**Prior art already on disk:** [[lean-hardware-model-loading]] (2026-07-30)
audited AutoBot's memory-bounded inference stack
(`autobot-backend/llm_shared/optimization/`) against a *different* reference
work covering the same general problem (layer-streaming, not MoE-expert
streaming). That audit's P0 defects are now fixed — #13031/#13032/#13033
closed 2026-08-16 (checkpoint is now memory-mapped and cached per path via
`_mapped_checkpoints`, not reloaded whole per token; embedding/LM-head wiring
and sampling-axis bug fixed; KV sliding-window trim direction fixed). Still
open: #13034 (no revision pinning/integrity check), #13035 (adapter never
registered — the engine has **no production caller**), #13036 (no
memory/correctness baseline). This status gates every verdict below: a
feature built on top of a code path nothing calls yet earns no throughput,
only maintenance.

### What We Can Adopt

**1. Pair every lossy/fidelity-trading toggle with a quantified fidelity
metric, not just a savings metric.**

- Already-exists audit: `autobot-backend/llm_shared/optimization/prompt_compressor.py:341-364`
  (`get_compression_stats`) reports only size metrics — `tokens_saved`,
  `average_compression_ratio`, `overall_compression_ratio`. No downstream
  output-quality/agreement signal. `token_optimizer.py` and `hf_quantizer.py`
  were also checked (`grep -n "quality|telemetry|fidelity"`) — no hits.
  AutoBot's lossy optimizations report what they saved, never what they cost.
- Visible benefit: the reference work's cache-aware routing mode ships
  default-off with built-in telemetry (cache hit%, swap%, agreement vs.
  true top-K, KL divergence) specifically so a user can see the fidelity
  price of the speed win before deciding to enable it.
- Hidden cost: an agreement/KL-style metric needs a reference (uncompressed)
  output to diff against, which costs the very compute the optimization is
  trying to save — has to be sampled/offline, not per-request.
- Verdict: **adopt-with-conditions** — add an offline/sampled fidelity check
  to `prompt_compressor.py`'s and `hf_quantizer.py`'s stats output rather
  than an inline per-call cost. Cheap, general, applies beyond inference.
- Effort: moderate (design the offline sampling harness once, reuse it).

**2. Persist per-layer/tensor access frequency across restarts to bias what
stays warm.**

- Already-exists audit: `layer_inference.py`'s `_mapped_checkpoints` cache
  (`layer_inference.py:284-286`) is in-process and per-path only, cleared on
  restart; `meta_eviction.py`'s `MetaDeviceEvictionManager` (`meta_eviction.py:276-320`)
  tracks `evicted_indices` for the current run only — no cross-session
  learning. `grep -rln "usage_log|hot_store|access_count"` across
  `llm_shared/` → zero hits.
- Visible benefit: the reference work's persisted usage log measurably
  speeds up repeated/similar workloads on the same host — "gets faster the
  more you use it."
- Hidden cost: Redis- or file-backed frequency state to reason about,
  staleness risk if the workload distribution shifts, and — decisively —
  **zero current payoff**: `LayerInferenceAdapter` is unregistered (#13035),
  so this path has no production caller to warm up for.
- Verdict: **adopt-with-conditions**, gated on #13035 landing first. Filing
  this now would be optimizing a code path nothing reaches.
- Effort: moderate.

**3. Disk-persisted KV cache for zero-re-prefill conversation resume.**

- Already-exists audit: `kv_cache.py:9-12` documents persistence "across the
  entire forward pass AND across generation steps" — explicitly in-process
  only, not across restarts. No serialization path found
  (`grep -n "persist|pickle|to_disk" kv_cache.py` → no disk-write hits).
- Visible benefit: the reference work resumes a conversation byte-identical
  after a restart with zero re-prefill cost.
- Hidden cost: KV-tensor serialization, versioning against model/quant
  changes (a stale cache from a different weight revision must never be
  reused), and — same blocker as #2 — the local layer-streaming engine has
  no production caller today. AutoBot's live conversation paths go through
  hosted-provider adapters (Ollama/OpenAI/Anthropic/Groq) where raw KV
  tensors aren't even exposed to the caller, so this only helps the dormant
  local engine.
- Verdict: **rejected-by-hidden-metrics** for now — revisit only if/when the
  local layer engine gets a production caller; today the build cost has no
  addressable path to a benefit.

**4. Multi-drive (dual-SSD) weight striping with deterministic hashing and
graceful per-file fallback.**

- Already-exists audit: `grep -rln "dual.*ssd|mirror.*disk|stripe"` across
  `autobot-backend/` and `autobot_shared/` → no hits outside an unrelated
  credentials test file.
- Visible benefit: near-additive read bandwidth from a second drive, degrades
  to single-drive on mismatch/failure rather than failing the run.
- Hidden cost: drive-hash/validate/fallback logic to build and maintain, for
  a single-host vertical-scaling technique. AutoBot's architecture already
  targets the same underlying problem (not enough resource on one machine)
  horizontally instead — see "Already Do Better" below — and the local
  engine this would attach to has no production caller yet (#13035).
- Verdict: **rejected-by-hidden-metrics** — AutoBot's chosen scaling axis for
  this problem is multi-machine, not multi-disk; building both is redundant
  complexity for one host class.

### What We Already Do Better

- **Provider/hardware portability.** AutoBot's adapter and provider
  registries span hosted APIs (Ollama, OpenAI, Anthropic, Groq) *and* local
  NPU dispatch by architecture family
  (`autobot-npu-worker/workers/openvino_dispatch.py:219-221`). The reference
  work is a single bespoke engine per model family with no hosted-provider
  fallback — every new model is a new multi-thousand-line C file, whereas
  AutoBot can point the same call site at a hosted API instead of building a
  local engine at all.
- **Broader quantization scheme support.** `hf_quantizer.py` handles
  GPTQ/AWQ/BnB generically rather than one fixed native scheme; the reference
  work supports several native formats (int4/int8/fp4/fp8/MXFP4) but only
  those it ships kernels for.
- **A chosen path to "not enough resource on one machine" that scales
  horizontally, not just vertically.** `autobot-npu-worker/workers/pipeline_parallel.py`
  and `worker_node.handle_partial_forward` (`worker_node.py:105`) shard layer
  ranges across worker *hosts*, with capability-based planning
  (`detect_capabilities`, `worker_node.py:38`) — a strictly larger design
  space than striping across two drives on one box. **Caveat carried over
  from the prior audit and re-verified today:** #13048 (no production
  `get_layers()` — only test doubles) is still open, so this is a better
  *architectural choice*, not yet a working advantage.

### Gaps & Opportunities

- **Layer-granularity streaming cannot capture MoE sparsity.** `grep -rln
  "MoE|num_experts|expert_id" autobot-backend/llm_shared/` → only
  `model_inspector.py` (parameter-counting/sizing, not the streaming path).
  `layer_inference.py` streams whole layers; for a MoE layer that means
  loading every expert even though the router only activates a small
  fraction per token — exactly the sparsity the reference work's entire
  design exploits (~40B active of 744B, per the source's own numbers). If
  AutoBot ever targets a large local MoE model, layer-level granularity caps
  the achievable memory reduction well below what expert-level residency
  would achieve — this is a structural ceiling, not a bolt-on feature, and
  is independent of and larger in scope than items #1-4 above. Worth a
  discovery issue if/when a MoE model lands on the local-engine roadmap;
  premature to file as actionable work while the engine has no production
  caller (#13035) and no MoE model is targeted.

### Specific Code/Files Affected

| File | Change | Depends on |
| --- | --- | --- |
| `autobot-backend/llm_shared/optimization/prompt_compressor.py` | Add an offline/sampled fidelity metric to `get_compression_stats()` | none — can land now |
| `autobot-backend/llm_shared/optimization/hf_quantizer.py` | Same fidelity-telemetry pattern for quantization mode selection | none — can land now |
| `autobot-backend/llm_shared/optimization/meta_eviction.py`, `layer_inference.py` | Persisted cross-restart access-frequency store to bias eviction | #13035 (adapter registration) landing first |
| `autobot-backend/llm_shared/optimization/kv_cache.py` | Disk-persisted KV for warm resume | deferred — no production caller; revisit if one appears |
| — | Dual-drive weight striping | not recommended — see rejected verdict above |
| `autobot-backend/llm_shared/optimization/` (new) | MoE expert-level residency/streaming | deferred discovery item — only if a local MoE model is targeted |

## Filed issues

| Finding | Issue |
|---|---|
| Report a sampled fidelity score beside every lossy optimization's savings (adopt now) | #16569 |
| Persist layer and tensor access frequency across restarts to seed the warm set | #16570, blocked by #13035 |
| Umbrella for this code area | #13030 |
