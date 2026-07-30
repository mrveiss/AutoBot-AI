# Large-model inference on lean hardware — capability audit

**Date:** 2026-07-30
**Question:** can AutoBot load and run large models on memory-constrained hardware, as
[`llm_shared/optimization/`](../../autobot-backend/llm_shared/optimization/) claims to?
**Answer:** the capability is scaffolded but non-functional. Four independent defects each defeat the
claim, plus three wiring/hygiene gaps.

---

## 1. Reference techniques for memory-bounded inference

The state of the art for running a model larger than available RAM is a small, well-understood set of
techniques. Recorded here as a target architecture, independent of any particular implementation.

**Split weights by residency class, not by layer.**

| Tier | Contents | Handling |
| --- | --- | --- |
| Resident | Embedding / tied head, attention projections, routers, dense shared FFN, norms | Memory-mapped read-only, wrapped for GPU access with no heap copy |
| Streamed | Sparse / conditionally-used weights (MoE routed experts, or cold layers) | Stored in per-layer files at fixed stride; only the weights actually selected are read, per token |
| Cached | The streamed weights currently in use | Fixed slot count per layer, preallocated and page-aligned, **LFU eviction with recency tie-break** |
| KV | Attention keys/values | Fixed-capacity **circular ring** for sliding-window layers; linear append-only only for full-attention layers |

**Read exactly the bytes needed.** Positional reads (`pread` / lazy tensor slicing) of the precise
byte range into a preallocated, reused slot. Whole-file demand paging is measurably worse under
memory pressure — a cold read via demand paging measured ~3.5× slower than an explicit ranged read in
the reference work, and the gap widened to ~8× throughput in a full streaming workload, because the
VM subsystem controls read timing and concurrency and the machine cannot keep the working set warm.

**Hide I/O behind compute that has no data dependency on the routing decision.** Per layer:

| Phase | Work |
| --- | --- |
| 1 | GPU: norm, QKV, RoPE, KV write, attention, output projection, router → selected weight IDs ready for CPU readback |
| 2 | CPU: cache plan (hits / misses / slot ownership), bounded **parallel** reads for misses only. GPU concurrently runs the always-resident dense branch — free latency cover |
| 3 | GPU: selected-weight branch, weighted reduction, combine with the dense branch, post-FFN norms, residual |

**Dispatch cache hits before miss-filled work.** Coarse-grained is both faster and easier to
synchronise than launching each group the instant its read lands — finer-grained overlap measured
*slower* and changed generated output.

**Apply the same bounded-memory rule to acquisition.** A model installer should never materialise the
full checkpoint: bind a transaction to a pinned upstream revision plus a canonical range plan, issue
bounded ranged requests, write straight into final offsets through tile-sized scratch, `fsync` file
and parent directory before recording a range durable, record a per-range destination digest, and
promote the directory atomically. Cancellation pauses rather than deletes; resume re-validates
recorded digests and re-fetches only missing or damaged ranges. Ranged transfers must re-apply the
range header across redirects, validate the response's content range, and hard-fail on byte overrun —
the server is not trusted to honour the request.

**Techniques deliberately not worth building.** Each of these was measured in the reference work and
rejected; AutoBot should decline to re-run them:

| Technique | Why it loses |
| --- | --- |
| Speculative cross-layer weight prefetch | Adjacent layers share almost no selected weights (Jaccard 0.039; copying the previous layer's choices predicts 7%). Killed by offline analysis before any runtime cost. |
| OS read-advice hints (`F_RDADVISE` and equivalents) | Seven variants. Some large wins, some large collapses; no policy reliably predicted which. Default off. |
| Speculative / read-ahead I/O | Fast in isolation, slowed decode and stretched prefill ~50%. |
| Compressed weight storage | Zstd ~10%, LZ4 0.06% — not worth the decode cost. |
| Quantized (4-bit) KV cache | Saved only ~82 MiB at 4K, *lost* the advantage at longer contexts against a ring-based FP16 layout, and failed the output-quality gate. |
| Monolithic kernel fusion | Forcing incompatible work into one wrapper cut throughput ~34%. Targeted fusions with compatible shapes and data lifetimes are fine. |

**Vector-width loads must respect the live byte offset, not the fixture's.** A 32-bit packed-load
path passed an offset-zero unit test and produced garbage in real decode, because live sub-tensor
offsets were only 2-byte aligned. Kernel and slicing tests must use production-shaped offsets.

**Gate changes by class, not uniformly.** Claimed-lossless transformations require exact byte or
output identity. Changes that reorder floating-point work require a distributional quality oracle
(delta-NLL, top-1 agreement) against reference outputs. Anything reusing a buffer a GPU command may
still own requires an explicit ownership/queue-order proof. A promising microbenchmark only *starts*
an experiment — end-to-end throughput and quality decide whether it ships. Mechanism counts
(fewer allocations, fewer dispatches, fewer reads) are not outcomes: several changes reduced all
three and still lost end to end.

---

## 2. What AutoBot has today

`autobot-backend/llm_shared/optimization/` (~12k LOC, 14 modules) is a layer-streaming
inference stack whose stated purpose matches the target architecture above. It originates
from issues #1946, #1952, #1964, #3104 and #3140.

> *"During batch/offline inference the entire model need not reside in VRAM simultaneously… Memory
> requirements are therefore bounded by the largest single layer rather than the full model."*
> — [layer_inference.py:8-12](../../autobot-backend/llm_shared/optimization/layer_inference.py#L8-L12)

Modules present: `layer_inference.py`, `meta_eviction.py`, `kv_cache.py`, `hf_quantizer.py`,
`model_inspector.py`, `pipeline.py`, `attention_backend.py`, `flash_attention.py`, `ssm_kernels.py`,
`profiler.py`, `prompt_compressor.py`, `token_optimizer.py`, `cloud_batcher.py`, `connection_pool.py`.

**Audit scope.** Greps across `autobot-backend/`, `autobot_shared/`, `autobot-npu-worker/` (worktrees
excluded) for `openvino|NPU`, `from_pretrained|safetensors|gguf|snapshot_download`,
`mmap|memmap|safe_open|device_map|low_cpu_mem_usage|max_memory|offload_folder|accelerate`,
`sha256|checksum|digest`, `Range: bytes=|resume_download|Content-Range`, `revision=`. Files read:
`layer_inference.py`, `kv_cache.py`, `meta_eviction.py`, `model_inspector.py`, `pipeline.py`,
`adapters/layer_inference_adapter.py`, `adapters/registry.py`, `initialization/lifespan.py`,
`autobot-npu-worker/workers/worker_node.py`, `workers/pipeline_parallel.py`,
`services/npu_pipeline/npu_client.py`.

---

## 3. Defects

| # | Location | Defect |
| --- | --- | --- |
| **D1** | [layer_inference.py:264](../../autobot-backend/llm_shared/optimization/layer_inference.py#L264) | `load_layer()` calls `torch.load(state_dict_path, map_location="cpu", weights_only=True)` — **deserialising the entire checkpoint into RAM** — then filters to one layer's key prefix. Peak memory is the *whole model*, exactly what the module claims to avoid. |
| **D2** | [layer_inference.py:424-425](../../autobot-backend/llm_shared/optimization/layer_inference.py#L424-L425) → [:503](../../autobot-backend/llm_shared/optimization/layer_inference.py#L503) | `_run_layer_loop` runs once per generated token and calls `load_layer()` once per layer inside it → **num_layers × max_new_tokens full-checkpoint loads**. A 32-layer model generating 64 tokens deserialises the checkpoint 2,048 times. There is no cache of any kind between the loop and the file. |
| **D3** | [layer_inference.py:349](../../autobot-backend/llm_shared/optimization/layer_inference.py#L349), [:498](../../autobot-backend/llm_shared/optimization/layer_inference.py#L498), [:616](../../autobot-backend/llm_shared/optimization/layer_inference.py#L616) | `hidden = input_ids.float()` feeds **raw token IDs as hidden states**. `get_layer_names()` ([:215-230](../../autobot-backend/llm_shared/optimization/layer_inference.py#L215-L230)) emits only `model.layers.N` — never `model.embed_tokens` or `lm_head` — and `_greedy_sample` argmaxes over the *hidden* dimension, not vocab. The engine cannot produce correct tokens. |
| **D4** | [kv_cache.py:254-278](../../autobot-backend/llm_shared/optimization/kv_cache.py#L254-L278) | `trim_to_length()` sets `entry.filled_len = max_len`. Since `update()` appends at `[start:end]` ([:374-376](../../autobot-backend/llm_shared/optimization/kv_cache.py#L374-L376)) and `get()` returns `[:filled_len]` ([:193](../../autobot-backend/llm_shared/optimization/kv_cache.py#L193)), this **retains the oldest `max_len` positions and silently discards the newest** — backwards for the sliding-window use its own docstring names. With the hard `ValueError` on overflow ([:369-373](../../autobot-backend/llm_shared/optimization/kv_cache.py#L369-L373)), long generation either corrupts context or hard-fails. |
| **D5** | [layer_inference.py:249](../../autobot-backend/llm_shared/optimization/layer_inference.py#L249) | Docstring promises `.pt` **or `.safetensors`**, but `torch.load` cannot read safetensors. `grep safe_open` across the backend → **zero hits**. Safetensors offers lazy per-tensor slicing without full deserialisation — the fix for D1 is available and unused. |
| **D6** | [lifespan.py:1274-1312](../../autobot-backend/initialization/lifespan.py#L1274-L1312) | `_register_llm_adapters()` registers only Ollama, OpenAI, Anthropic, Groq. `LayerInferenceAdapter` is defined ([layer_inference_adapter.py:32](../../autobot-backend/llm_shared/adapters/layer_inference_adapter.py#L32)) and exported ([`adapters/__init__.py`:23](../../autobot-backend/llm_shared/adapters/__init__.py#L23)) but **never registered** → unreachable from `GET /api/adapters`. The stack is dead on arrival in production. |
| **D7** | [meta_eviction.py](../../autobot-backend/llm_shared/optimization/meta_eviction.py) | Zero production callers (only `meta_eviction_test.py`), while [layer_inference.py:578](../../autobot-backend/llm_shared/optimization/layer_inference.py#L578) carries a private `_move_to_meta` duplicate. Two implementations of one concept — canonical-source violation. |

**No revision pinning or weight integrity verification (cross-cutting).**
`grep -rn "revision=" autobot-backend autobot_shared autobot-npu-worker` → **zero non-Alembic hits**,
against **18 `# nosec B615` suppressions** carrying the comment *"revision pinning managed
operationally"* — with no mechanism implementing that claim. Affected call sites include
[layer_inference.py:186](../../autobot-backend/llm_shared/optimization/layer_inference.py#L186),
[:462](../../autobot-backend/llm_shared/optimization/layer_inference.py#L462),
[model_inspector.py:267](../../autobot-backend/llm_shared/optimization/model_inspector.py#L267),
[code_embedding_generator.py:124](../../autobot-backend/code_embedding_generator.py#L124),
[ai_hardware_accelerator.py:625](../../autobot-backend/ai_hardware_accelerator.py#L625),
[multimodal_processor/processors/vision.py:103](../../autobot-backend/multimodal_processor/processors/vision.py#L103).
The only `sha256` uses in `llm_shared/` are cache-key hashing
([token_optimizer.py:104](../../autobot-backend/llm_shared/optimization/token_optimizer.py#L104),
[providers/cache_utils.py:33](../../autobot-backend/llm_shared/providers/cache_utils.py#L33)) — no
downloaded artifact is ever verified. A mutable upstream tag can silently change the weights AutoBot
executes, in production embedding, vision, and audio paths, not only in the dormant layer engine.

---

## 4. Where AutoBot's design is ahead

- **Multi-machine pipeline parallelism.** [`workers/pipeline_parallel.py`](../../autobot-npu-worker/workers/pipeline_parallel.py),
  [`worker_node.handle_partial_forward`](../../autobot-npu-worker/workers/worker_node.py#L105) and
  [`services/npu_pipeline/npu_client.py`](../../autobot-backend/services/npu_pipeline/npu_client.py)
  shard layer ranges across worker hosts over `POST /partial_forward`, with capability-based planning
  ([`detect_capabilities`](../../autobot-npu-worker/workers/worker_node.py#L38) derives `max_layers`
  from `total_vram // vram_bytes_per_layer`) and concurrent
  [`batch_partial_forward`](../../autobot-backend/services/npu_pipeline/npu_client.py#L164).
  Scaling out across several lean machines is a strictly larger design space than streaming from one
  SSD on one host. *Caveat: the only `get_layers()` implementations found are test doubles — the
  production model loader behind this path was not located. Architecture ahead of implementation.*
- **Hardware and provider portability.** The adapter and provider registries span Ollama, OpenAI,
  Anthropic, Groq, AI-stack and process adapters; the NPU worker dispatches by architecture family
  ([openvino_dispatch.py:219-221](../../autobot-npu-worker/workers/openvino_dispatch.py#L219-L221)).
  A residency-tiered runtime bound to one GPU API and one model shape has none of this.
- **Quantization breadth.** [`hf_quantizer.py`](../../autobot-backend/llm_shared/optimization/hf_quantizer.py)
  handles GPTQ/AWQ/BnB generically rather than one fixed affine scheme.
- **Empty-weight model inspection.** [`model_inspector.py:190`](../../autobot-backend/llm_shared/optimization/model_inspector.py#L190)
  counts parameters via an `accelerate` meta-device skeleton — sizing a model without downloading it.

---

## 5. Prioritised remediation

| P | Item | Effort |
| --- | --- | --- |
| **P0** | **The streaming engine does not stream** (D1, D2). Invalidates the headline capability; fully in-scope and self-inflicted. | Moderate |
| **P0** | **The engine cannot produce correct output** (D3). Any D1/D2 fix is unverifiable until this is closed. | Moderate |
| **P1** | **Sliding-window KV keeps the wrong end of the context** (D4). Silent context corruption. | Trivial (correctness) / moderate (ring) |
| **P1** | **No revision pinning or weight-integrity verification.** Supply-chain exposure across 18 suppressed findings, in live production paths. | Moderate |
| **P2** | **The stack is unregistered** (D6). Fixing P0-P1 changes nothing user-visible until the adapter is registered. | Trivial |
| **P2** | **Duplicate meta-eviction implementations** (D7). Collapse onto one canonical function. | Trivial |
| **P3** | **No measured baseline.** [`profiler.py`](../../autobot-backend/llm_shared/optimization/profiler.py) exists, but no benchmark records peak RSS or tok/s for this path — so no change to it can be judged end to end. | Moderate |

### Files affected

| File | Change |
| --- | --- |
| [layer_inference.py](../../autobot-backend/llm_shared/optimization/layer_inference.py) | Replace whole-checkpoint `torch.load` with `safetensors.safe_open` + per-tensor `get_slice`; add a bounded LFU slot cache keyed by layer name, reused across the token loop; hoist layer loading out of the per-token loop; add `model.embed_tokens` / `lm_head` to `get_layer_names` and route hidden states through them; drop the private `_move_to_meta` in favour of `meta_eviction.evict_layer_to_meta`. |
| [kv_cache.py](../../autobot-backend/llm_shared/optimization/kv_cache.py) | Fix `trim_to_length` to retain the **newest** `max_len` positions; follow up with ring storage for sliding-window layers and a wrap-aware `get()`. |
| [lifespan.py](../../autobot-backend/initialization/lifespan.py) | Register `LayerInferenceAdapter` in `_register_llm_adapters()` behind a config flag, once the engine passes an end-to-end output check. |
| 18 `from_pretrained` call sites | Add `revision=` from a pinned-model registry in `ssot_config`; verify downloaded artifact hashes; remove the matching `# nosec B615` suppressions. |
| `llm_shared/optimization/` (new test) | End-to-end acceptance test asserting peak RSS < full-checkpoint size **and** token-for-token parity against a `transformers` reference on a small model — the gate that would have caught D1-D3 at merge. |

### Recommendation

Treat this as a defect umbrella over `llm_shared/optimization/`, not as new feature work. The target
architecture in §1 is the design to converge on once D1-D3 are closed; the "not worth building" table
in §1 is a list of work to explicitly decline.

### Filed

Umbrella **#13030**, with children:

| Issue | P | Scope |
| --- | --- | --- |
| #13031 | P0 | Streaming engine does not stream — whole-checkpoint load per layer, per token (D1, D2, D5) |
| #13032 | P0 | Engine cannot produce correct output — no embedding, no LM head, wrong sampling axis (D3) |
| #13033 | P1 | KV sliding window retains the oldest positions instead of the newest (D4) |
| #13034 | P1 | No model revision pinning or weight integrity verification; 18 suppressed findings |
| #13035 | P2 | Adapter never registered + duplicate meta-eviction implementation (D6, D7) |
| #13036 | P3 | No end-to-end memory/correctness baseline for the optimization package |

Discovered during the audit and filed separately, since neither is on the umbrella's path:

| Issue | Scope |
| --- | --- |
| #13048 | Pipeline-parallel model loader has no production `get_layers()` — only test doubles (see §4) |
| #13049 | Consolidate architecture-family, dtype and compression taxonomies + duplicated `accelerate` loader |

Ordering: #13032 gates #13031 (memory work is unverifiable without correct output). #13035 lands last
(registering a broken engine turns dormant defects into live ones). #13034 is independent and can run
in parallel.

**Also observed, not yet filed:** the multi-machine pipeline-parallel path
([pipeline_parallel.py](../../autobot-npu-worker/workers/pipeline_parallel.py),
[worker_node.py](../../autobot-npu-worker/workers/worker_node.py)) has no located production
`get_layers()` implementation — only test doubles. Worth a discovery issue if confirmed.
