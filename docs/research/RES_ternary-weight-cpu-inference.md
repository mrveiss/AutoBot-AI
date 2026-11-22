---
tags:
  - research
---

# Research: ternary-weight ("1.58-bit") CPU inference

Status: Phase 1 and Phase 2 complete. Scoped to local model serving, embeddings and CPU-only nodes, read at `origin/main` 1d24d889d4. One measurement issue filed; see Linked issues.

## Source Analysis: an open-source inference engine for ternary-weight language models

### What It Is
The reference work is an inference engine for models whose weights are restricted to {-1, 0, +1}, which works out to about 1.58 bits per weight. It is a fork of the open-source engine that the local model server also builds on that adds ternary CPU kernels for x86 (AVX2) and ARM (NEON), plus a separate CUDA path for 2-bit-weight × 8-bit-activation matrix-vector products. Around those sit GGUF conversion tooling and thin Python wrappers over the engine's CLI and OpenAI-compatible server. It has been public since late 2024. The most recent additions are small ternary **embedding** models (270M and 0.6B parameters). It is mature as a research artefact and benchmark harness, and thin as a product: it ships scripts, not a library or a service.

### Architecture & Key Patterns
- **Fork of an upstream engine.** The engine is a git submodule pinned to an individual contributor's fork branch, not to upstream. The ternary kernels plug into the tensor library as new quantisation types.
- **Three kernel families.** One packs weights into 2 bits and uses a multiply-add kernel; it is the default on both architectures. The other two are lookup-table kernels, one for ARM and one for x86, in which precomputed tables of activation partial sums replace the multiplications.
- **Code generation at build time.** A script emits a generated kernel header. Its tile sizes are hard-coded for each model shape in the setup script, and pre-tuned variants are shipped for the published models.
- **A tuning header and auto-tuner** set the block sizes and the degree of parallelism.
- **Setup pipeline:** download → convert to GGUF → quantise → generate code → build with cmake/clang. The run scripts shell out to the built binaries.
- **Serving** uses the stock OpenAI-compatible server, CPU-only, with continuous batching and a loopback bind by default.
- **The GPU path is a separate PyTorch stack.** It has its own checkpoint format, generator and tokenizer, and is not wired into the GGUF path.

### Notable Implementation Details
- **"Lossless"** describes the kernel: it computes exactly what the ternary model computes. It does not mean an existing FP16 model can be converted to ternary without loss.
- **Activation-parallel unpacking** spreads the cost of unpacking 2-bit weights across several activation rows. It is reported as 1.15×–2.1× faster than the project's previous kernel.
- **Embedding-layer quantisation** (Q6_K or F16) cuts memory in small models, where the embedding table is a large share of the total.
- **A dummy-model generator** benchmarks a model *shape* without any trained weights. A companion script measures energy use.

### Strengths
- Large reported CPU speedups for models trained ternary from the start: 2.4×–6.2× on x86 and 1.4×–5.1× on ARM against full precision, with 55–82% less energy. A 100B ternary model is reported at 5–7 tokens/s on a single CPU.
- A 2B-parameter model needs about 0.4 GB for its weights, so it runs on small nodes with no GPU.
- It reuses the GGUF ecosystem, so the OpenAI-compatible server comes for free. It is MIT-licensed.

### Weaknesses / Limitations
- **Few usable models.** Only models trained ternary from the start benefit. There is one official chat model of about 2.4B parameters, two embedding models, and a handful of community models. Existing FP16 models cannot be converted without heavy quality loss.
- **Patchy kernel/architecture coverage.** The embedding models run on x86 only, each lookup-table kernel runs on one architecture only, and some models have no fast kernel at all on a given architecture.
- **A fork that lags upstream.** Upstream fixes, including security fixes, arrive late. Build breakage caused by upstream drift is documented in the project's own FAQ.
- **A fragile build.** It needs clang ≥ 18, and the code-generation parameters are hard-coded per model. Build failures are among the most-reacted open issues.
- **Gaps for running it as a product.** The scripts exit the process on any error. There is no library API, no packaging and no model registry. The GPU path is a separate stack.

### Visible vs Hidden Metrics
- **Visible (self-reported):** 2.4×–6.2× x86 speedup, 55–82% energy cut, 100B on one CPU, "lossless", 0.4 GB for a 2B model. The speedups compare the *same ternary model* at full precision. They do not compare against a 4-bit quantisation of a stronger full-precision model, which is the choice an adopter actually faces.
- **Hidden:** a second inference runtime to build, pin and patch; a capability ceiling set by a handful of checkpoints; slow security patching of a forked server; per-architecture kernel gaps across a mixed fleet; and a supply-chain risk from a submodule pinned to an individual's fork.
- **Weighing:** it pays off only on CPU-only or power-limited nodes, and only where a small model is good enough: routing, classification, short extraction, embeddings. For general chat and agent work, the hidden costs and the capability ceiling outweigh the speedup.

## AutoBot Comparison

### What We Can Adopt

| # | Candidate | AutoBot target | Already-exists audit | Visible benefit | Hidden cost | Verdict | Effort |
|---|---|---|---|---|---|---|---|
| 1 | Benchmark a ternary embedding model as a CPU-node option | `autobot-backend/knowledge/rag_benchmarks.py`; `autobot_shared/embedding_model.py` (`KNOWN_EMBEDDING_MODEL_PREFIXES` has no ternary family) | Switching the embedding model at runtime, with rebuild and cutover, already exists (#19377, #19379). The embedding space is recorded only for indexes with a known build path (`knowledge/index_embedding_space.py`); the hybrid FAISS index and the accelerator collections carry a refusal instead, because their build model is not reproducible. What is missing is a measured quality/latency comparison against `DEFAULT_EMBEDDING_MODEL` (`ssot_config.py`). | 1.3×–2.3× faster CPU prefill at about 2 bits per weight | Needs the forked runtime (neither Ollama nor the OpenVINO NPU worker can run it); x86 only; switching re-indexes every vector | **adopt-with-conditions**: measure first, and adopt a runtime only if quality is at least as good on AutoBot's own KB | moderate |
| 2 | A ternary chat model for the routing, classification and light tiers on CPU-only nodes | `autobot_shared/ssot_config.py` tier constants; `autobot_shared/agent_model_tiers.py` | The tiers exist and are driven by the SSOT config. Local serving is Ollama (`llm_shared/providers/bootstrap.py`). No ternary model is used anywhere. | Faster, cheaper CPU decoding; about 0.4 GB | A second runtime outside Ollama; slow patching of the fork; one usable model; tool-use quality unproven | **rejected-by-hidden-metrics** for now. Revisit only if Ollama's own runtime can load ternary weights (upstream has native ternary quantisation types; Ollama support not verified). | significant |
| 3 | Per-host kernel tuning and build-time code generation | n/a | n/a | Up to 2× kernel speed | Tile parameters hard-coded per model, per-architecture builds; conflicts with the rule that updates go through the builtin updater only | **rejected-by-hidden-metrics** | significant |

### What We Already Do Better
- **Provider abstraction and failover.** The registry, fallback chain and failover policy live in `llm_shared/provider_registry.py`, `fallback_chain.py` and `failover_policy.py`. The reference work hard-wires one binary per script and exits on any failure.
- **Generic OpenAI-compatible support.** `llm_shared/providers/custom_openai.py` would consume the reference work's server unchanged, so no new provider is needed.
- **Backend selection by hardware.** `llm_shared/hardware.py` tries backends in a priority order (OpenVINO NPU, then OpenVINO, CUDA and CPU). The reference work chooses kernels in hand-coded setup branches.
- **Embedding-space integrity.** A single model resolver plus a recorded embedding space per index stop vectors from different models being mixed. The reference work has no such concept.
- **Model pinning.** `autobot_shared/pinned_model_registry.py` pins HF revisions. The reference work downloads unpinned repositories and builds from a fork submodule.

### Gaps & Opportunities
1. **No measured CPU-only embedding alternative.** Every embedding path uses either the default Ollama model or the NPU worker's model / MiniLM. Adopt #1 is filed as a measurement. It is blocked until the benchmark harness scores the real KB with a real embedding (#13243).
2. **Watch item:** native ternary quantisation in the upstream engine. If Ollama loads it, #2 above no longer needs a second runtime.

### Specific Code/Files Affected (only if #1 proceeds)
- `autobot-backend/knowledge/rag_benchmarks.py`: a ternary benchmark arm reporting recall@k, latency and RAM on a CPU-only node.
- `autobot_shared/embedding_model.py`: add the family prefix only if the benchmark passes.
- Serving: an OpenAI-compatible embedding endpoint. `llm_shared/providers/` has no embedding operation; embeddings are served by `services/npu_client.py` (`generate_embedding_with_fallback`: NPU worker first, Ollama as the fallback), so a new serving path would be added there, deployed by the builtin updater.

## Linked issues

- #21775 perf(kb): benchmark a ternary-weight embedding model as a CPU-node option against the current default
