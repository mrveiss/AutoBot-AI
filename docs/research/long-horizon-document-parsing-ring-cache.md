---
title: "Research: a long-horizon document-parsing vision-OCR model"
created: 2026-09-29
reviewed: 2026-09-29
status: current
tags:
  - research
  - ocr
  - vision-language
  - inference
---

# Research: a long-horizon document-parsing vision-OCR model

- **Source:** the reference work — a vendor-published open-weight vision-OCR model (name, authors and URL withheld per the anonymization rule)
- **Fetched:** 2026-09-29 (read-only: repo API, raw file reads, model-hub API — no clone)
- **Phase:** 1 (Source Analysis) + 2 (AutoBot Comparison) — both complete 2026-09-29

**Local file aliases** (the upstream filenames carry the source's identity, so this doc
refers to them by role; line numbers are upstream-accurate):

| Alias used here | Role |
|---|---|
| `modeling_vlm.py` | the vision-language wrapper: preprocessing, `infer`, `infer_multi` |
| `modeling_decoder.py` | the MoE text decoder, incl. the ring-cache attention class |
| `deepencoder.py` | the two-stage vision encoder and MLP projector |
| `infer.py` | the batch driver shipped in the repo |

---

## Source Analysis: a long-horizon document-parsing vision-OCR model

### What It Is

An open-weight (MIT, code **and** weights) vision-language model for **document parsing** —
image or PDF page in, structured markdown-ish text out, with optional
`<|det|>type [bbox]<|/det|>` grounding markers around each block. Its pitch is not accuracy
per page but *horizon*: parsing a whole multi-page document in **one shot**, inside a single
32,768-token context, instead of page-by-page with stitching. It openly positions itself as an
incremental push on an earlier open vision-OCR model it acknowledges as its starting point,
and it inherits that model's encoder design and most of its decoder code.

Maturity is **young and load-bearing at once**: the repo is ~3.5 months old (created
2026-06-18, last push 2026-07-29 — two months stale as of this writing), yet carries
26,515 stars, 2,776 forks and 1.67M model-hub downloads. The GitHub repo itself is almost
empty — a README, a 329-line batch driver, a PDF of the paper, and a 12.45 MB prebuilt
serving-runtime wheel. **All the actual code lives on the model hub** as `trust_remote_code`
Python shipped beside the weights (~3.3 GB of source-visible modelling code, 6.67 GB bf16
safetensors). 80 of 100 issues are open; the maintainers answer sporadically.

### Architecture & Key Patterns

**Two-stage vision encoder → linear projector → sparse MoE decoder.**

1. **Encoder** (`deepencoder.py`): a windowed-attention SAM-style ViT (width 768, 12 layers,
   global attention only at blocks 2/5/8/11 — `deepencoder.py:606-712`) runs at full 1024×1024
   resolution where attention is cheap because it is windowed. Its output then passes through
   **two stride-2 convolutions** (`net_2`: 256→512, `net_3`: 512→1024, `deepencoder.py:695-709`)
   for a 16× spatial token reduction, and only *then* into a CLIP-L-style global-attention
   transformer (width 1024, 24 layers). The expensive global attention therefore never sees the
   high-resolution grid. This is the inherited design and it is the single best idea in the stack.
2. **Projector**: a linear MLP projector, 2048 → 1280 (`config.json` `projector_config`).
3. **Decoder**: a 12-layer sparse MoE, hidden 1280, 64 routed experts + 2 shared, **top-6 per
   token**, first layer dense (`first_k_dense_replace: 1`), vocab 129,280, 32k positions,
   `use_mla: false`. Only a small fraction of decoder weights is active per token.

**Token budget.** `num_queries = ceil((image_size / patch_size) / downsample_ratio)` =
`ceil((1024/16)/4)` = 16, and each page is emitted as `(16+1)*16 + 1` = **273 vision tokens**
(`modeling_vlm.py:1191-1211`). At 273 tokens/page a 32k window holds roughly 100 pages of
*prefix* — the whole "long-horizon" claim reduces to that arithmetic plus the next item.

**Two resolution modes.** *Untiled* is a single 1024×1024 global view. *Tiled* is
aspect-ratio-matched cropping (`dynamic_preprocess`, `modeling_vlm.py:175-215`) into 2–32 local
640px crops plus a global thumbnail, picking the tile grid whose aspect ratio is closest to the
page. Multi-page parsing supports **the untiled mode only** — tiling and long-horizon are mutually
exclusive, which is the central unadvertised trade.

### Notable Implementation Details

**1. A ring-buffer KV cache during decode — the actual novelty.**
`SlidingWindowLlamaAttention` (`modeling_decoder.py:1232-1372`) splits the cache in two.
Prefill (vision tokens + prompt) is written once and **never evicted**. Generated tokens then
occupy a fixed **W = 128**-slot ring appended after the prefill; once full, each new token
overwrites slot `prefill_len + ring_pos`, `ring_pos = (ring_pos + 1) % W`, **in place**
(`modeling_decoder.py:1358-1367`). KV memory is therefore **constant no matter how long the
output runs** — that is the entire basis of the unbounded-output framing. RoPE is applied before the
write so absolute position rides in the key, and decode attends over the full cache with no
causal mask (softmax over keys is permutation-invariant, so ring disorder is harmless).

**2. The framework's own sliding-window path is deliberately disabled to make this work.**
Around every `generate()` call the code copies `config.sliding_window_size` into a private
`config._ring_window`, sets `config.sliding_window = None`, and restores it afterwards
(`modeling_vlm.py:998-1000, 1021, 1233-1237, 1257`), with the comment *"Disable
config.sliding_window to prevent DynamicCache from truncating prefill tokens."* Ring state
(`_prefill_length`, `_ring_pos`) is monkey-patched onto the stock cache object per layer. It
works, but generation state is passed through a mutated config object and attributes grafted
onto a framework class — both break on a framework upgrade.

**3. The ring path is eager attention only.** `ATTENTION_CLASSES` registers
`"mha_eager": SlidingWindowLlamaAttention` and leaves `mha_flash_attention_2` **commented out**
(`modeling_decoder.py:1380-1390`). The long-horizon path therefore materialises the full
attention-weight matrix on every decode step. The headline capability runs on the slowest
attention implementation in the file.

**4. A sliding-window no-repeat-n-gram logit processor, sized to cover the ring's blind spot.**
`SlidingWindowNoRepeatNgramProcessor` (`modeling_vlm.py:354-384`) bans any token that would
complete a previously-seen n-gram (default `ngram_size=35`) within the last `window` tokens,
`-inf`-ing the offending logits. The defaults are the tell: `ngram_window=128` for single-image,
**`1024` for multi-page** — i.e. the repetition guard searches up to 1024 tokens of generated
history that the *attention* can no longer see (W=128). The guard is not an extra: it is the
compensation mechanism for the ring's memory loss, and the same processor is reimplemented as a
custom logit processor inside the bundled serving-runtime wheel so both paths behave alike.

**5. Streaming throughput telemetry in the model file.** `TPSTextStreamer`
(`modeling_vlm.py:386-426`) prints recent and average tokens/sec every N tokens, excluding
prefill from the clock. Small, but it means the long-horizon path is observable by default
rather than through an external harness.

**6. Post-processing is left to the caller.** The README hands out a regex
(`DET_RE = re.compile(r'<\|det\|>([^<\s]+)(?:\s*\[[^\]]*\])?\s*<\|/det\|>(.*)')`) for stripping
grounding markers back into plain blocks for benchmark scoring. There is no parser, no schema,
no validation — the structured-output contract is a text convention, not a type.

### Strengths

- **Constant-memory decoding.** The ring cache genuinely decouples KV memory from output length.
  For a 100-page document emitting tens of thousands of tokens this is the difference between
  fitting and not fitting.
- **Encoder ordering is principled.** High resolution where attention is windowed, 16× conv
  downsample, global attention only on the reduced grid. 273 tokens per full page is a strong
  compression ratio for a parse that keeps layout and bounding boxes.
- **Genuinely permissive.** MIT on code *and* weights, with no usage rider — rarer than it looks
  in this category.
- **Single-file deployability.** One safetensors shard, a stock `transformers` entry point, and
  a documented OpenAI-compatible serving path; the batch driver boots its own server and reuses
  a running one if `/health` answers (`infer.py:82-133`).
- **Fast third-party uptake.** Serving-runtime, training-framework, cloud and demo integrations
  all landed within ~5 weeks of release.

### Weaknesses / Limitations

- **The headline feature and the top defect are the same mechanism.** With W=128, the model
  cannot see anything it wrote more than 128 tokens ago. The most-reported failures — infinite
  repetition loops (#55, #82, #84) and *"output quality collapses after 2–3 pages"* while KV
  stays constant (#53) — are not incidental bugs; they are the ring doing exactly what it is
  built to do. #55 identifies the mitigation's own limit precisely: `ngram_size=35` never fires
  on short repeating units.
- **Headline benchmark not independently reproduced.** An open issue (#66) reports measuring a
  benchmark text edit-distance of 0.087 against ~0.042 implied by the published overall score —
  a ~2× gap on the primary metric, with other sub-metrics at parity. Unanswered. A separate
  issue (#1) questions the attribution in the paper's main ablation table. **No metric in this
  analysis is independently verified.**
- **CUDA-only in practice.** 14 hardcoded `.cuda()` calls in the wrapper. CPU works only after
  patching them out; Apple Silicon produces empty output or crashes mid-generation (#18, #48,
  #81). Non-NVIDIA accelerators are undocumented (#32, #38, #99).
- **Cannot tensor-parallel evenly.** 10 attention heads is not divisible by 4 (#76) — a
  4-GPU serving layout is simply unavailable.
- **Serving integrations are fragile.** The tiling mode crashes one serving engine with a
  multimodal-token-count mismatch (#63); the batch driver fails to start against the published
  processor config (#46); the wrapper class was initially unsupported by the runtime it ships a
  wheel for (#12). Transformers and server paths are reported to produce *different* output
  quality (#14).
- **Throughput is the unstated cost.** An adopter reports **8–19× slower per page than a
  classical CPU OCR engine, on GPU** (#100). Consistent with the eager-attention finding above.
- **Supply chain.** Weights require `trust_remote_code=True` — model load executes vendor Python.
  The hub repo has **one branch, `main`, and zero tags**, so there is no semantic revision to
  pin; only a commit SHA. Both repos ship a **prebuilt wheel of an unreleased dev build of a
  serving runtime** (`…dev11416+g92e8bb79e`), 12.45 MB of binary with no matching source, which
  the documented install instructions put into your environment before anything else.
- **Bundled driver binds `0.0.0.0` with no auth.** `infer.py:23` hardcodes the host; the launched
  inference server has no key, and the README's own snippet sets `session.trust_env = False`.
  Fine as a benchmark harness, unsafe as a deployment template — which is how it reads.
- **Stale and thinly maintained.** No push in two months, 80 open issues, several unanswered
  reproduction reports, hardcoded parameters and no resume in the batch driver (#17). Issue
  threads include unsolicited third-party self-promotion (#69, #97) — normal for a repo this
  visible, noted only because the issue tracker is the de-facto documentation here.

### Visible vs Hidden Metrics

**Visible (all vendor-self-reported or popularity-derived; none independently verified here):**

| Claim | Value | Verification status |
|---|---|---|
| "One-shot long-horizon parsing" | whole multi-page doc in one 32k context | Mechanism confirmed in code; quality at horizon **contested** (#53) |
| Benchmark overall score | implied text edit-dist ~0.042 | **Contested** — community measures 0.087 (#66), unanswered |
| Vision-token compression | 273 tokens/page @1024² | Confirmed by arithmetic in `modeling_vlm.py:1191` |
| Constant KV memory | independent of output length | **Confirmed** in `modeling_decoder.py:1358-1367` |
| Popularity | 26.5k stars · 2.8k forks · 1.67M downloads · 4.3k likes | Real, and ~5 weeks old — adoption, not validation |
| Licence | MIT, code + weights | Confirmed |

**Hidden (the costs an adopter inherits):**

- **Quality decays with the very horizon being sold.** Any pipeline using this for >2–3 pages
  per call must budget for repetition loops and drift, and needs its own detector — the n-gram
  guard is documented as insufficient by the maintainers' own issue tracker.
- **Latency.** ~8–19× a classical OCR engine per page, GPU included. Fine for a batch
  parse-to-knowledge-base job, disqualifying for an interactive path.
- **Hardware lock-in.** NVIDIA-only, and not on a 4-GPU split. No NPU or Apple-Silicon path.
  ~7 GB of weights resident.
- **Executable-model risk.** `trust_remote_code=True` plus an unpinnable revision plus an
  unauditable prebuilt wheel. Every model load is remote code execution against a moving target.
- **Framework fragility.** Ring state is monkey-patched onto framework internals and passed via a
  mutated config; the shipped requirements pin one `transformers` version while the config
  declares another. An upgrade in the host project can silently break the ring or silently
  disable it.
- **Output contract is a regex.** Downstream structure extraction is the adopter's problem,
  permanently.
- **Maintenance burden.** Two months stale, 80 open issues, contested headline number. Adopting
  means owning the integration.

**Weighing.** The visible wins are real but narrow, and two of the three hidden costs attack the
headline directly: the horizon degrades over the horizon, and it does so slowly (eager
attention). For an **offline, GPU-resident, batch document-ingestion** job where per-page latency
is irrelevant and a repetition detector is cheap to add, the compression ratio and constant-memory
decode are worth having. For anything interactive, anything non-NVIDIA, or anything that cannot
accept remote-code model loading against an untagged revision, the hidden metrics veto it
outright. **The transferable idea is the ring-buffer-over-pinned-prefix cache pattern —
"pin the context, ring the continuation" — not this model.**

---

## AutoBot Comparison: the reference work → AutoBot

**Scope audited:** `autobot-backend/llm_shared/optimization/` (KV cache, layer inference,
flash attention, meta eviction), `autobot-backend/context_window_manager.py`,
`autobot-backend/media/document/` (OCR, extraction, pipeline, provenance),
`autobot-backend/llm_shared/providers/`, and every `from_pretrained` call site in the repo.
Every claim below cites what was read or grepped.

### What We Can Adopt

#### 1. Pin-the-prefix / ring-the-continuation KV retention — *adopt-with-conditions*

- **Where it lands:** [autobot-backend/llm_shared/optimization/kv_cache.py:254-305](autobot-backend/llm_shared/optimization/kv_cache.py#L254-L305)
- **Already-exists audit:** `LayerKVCache.trim_to_length` + `_retain_tail` read in full — a
  sliding window already exists and was already corrected once (#1964, #13033; the docstring
  records that it used to truncate the *pointer*, silently keeping the wrong end of the
  sequence). `grep -rn "trim_to_length"` returns **only `kv_cache_test.py`** — zero production
  callers. [flash_attention.py:207](autobot-backend/llm_shared/optimization/flash_attention.py#L207)
  `GrowingKVCache` grows in fixed chunks and never evicts.
  [context_window_manager.py:387](autobot-backend/context_window_manager.py#L387) does
  prioritized trimming, but at the *message* plane, not the KV plane. Nothing in the tree pins
  a prefix.
- **The delta, and only the delta:** two things AutoBot's version does not do. (a) `_retain_tail`
  keeps the **tail only** — wired as-is on a long generation it evicts the system prompt and task
  prefix, the exact tokens that must survive. The reference work splits the cache: prefill is
  written once and never evicted, and only *generated* tokens rotate. (b) `_retain_tail` clones
  the retained window and `copy_`s it down to offset 0 on **every** trim — O(window) memcpy per
  call; a ring writes one slot and advances a modulo counter, O(1).
- **Visible benefit:** KV memory constant regardless of output length; no per-step copy.
- **Hidden cost:** ring order is not chronological, so any code that assumes a linear cache
  layout (mask construction, cache inspection, debugging, `get()`'s `k[:, :filled_len]` contract)
  must be re-checked; and the reference work's own issue tracker is the proof that this retention
  policy *requires* a compensating repetition guard (item 3) to be usable at all. It is also a
  second retention policy to maintain beside `_retain_tail`, not a replacement for it.
- **Verdict:** **adopt-with-conditions** — as an opt-in `retain_prefix + ring` mode *inside*
  `LayerKVCache`, landed together with item 3, and **without** the eager-attention coupling the
  source pairs it with. Belongs under existing umbrella **#13030**, not a new one.
- **Effort:** moderate.

#### 2. The `kv_cache` parameter that is accepted and ignored — *fix, not adopt*

- **Where:** [layer_inference.py:397](autobot-backend/llm_shared/optimization/layer_inference.py#L397)
  and its own docstring at `:406-408` — *"The `kv_cache` argument is accepted for API consistency
  and future integration with LayerKVCache but is not inspected in this implementation."*
- **Audit:** `LayerInferenceEngine.generate()`
  ([layer_inference.py:526-538](autobot-backend/llm_shared/optimization/layer_inference.py#L526-L538))
  re-concatenates `input_ids` and calls `_run_layer_loop(input_ids, ...)` over the **full
  sequence every step** — there is no cache in the decode loop at all. So `kv_cache.py` and the
  only engine that would consume it are not connected in either direction. External references
  to `LayerInferenceEngine`: one, `llm_shared/adapters/layer_inference_adapter.py`, itself
  exported from `adapters/__init__.py:23` with no further production call path found.
- **Verdict:** a declared-but-unenforced parameter — the same shape as the
  `MCPBridgeManifest.resource_limits` finding in [[model-hardware-standard]]. Wire it in scope
  of **#13030**; item 1 is meaningless until this is true. **Effort:** moderate.

#### 3. A sliding-window no-repeat-n-gram logit processor — *adopt-with-conditions, as a dependency of 1*

- **Where it lands:** the local decode loop,
  [layer_inference.py:526-538](autobot-backend/llm_shared/optimization/layer_inference.py#L526-L538)
- **Already-exists audit:** `repeat_penalty` is passed through to one provider
  ([providers/ollama.py:118](autobot-backend/llm_shared/providers/ollama.py#L118),
  [llm_shared/models.py:63](autobot-backend/llm_shared/models.py#L63)); `LLMRequest` carries
  `frequency_penalty` and `presence_penalty`
  ([llm_shared/models.py:162-163](autobot-backend/llm_shared/models.py#L162-L163)); and
  `chat_workflow/` has **tool-call** loop detection (`_LOOP_DETECTION_WINDOW`, call-fingerprint
  based). None is an n-gram ban at the token plane. `generate()` is pure greedy
  (`_greedy_sample`) with no sampling parameters at all.
- **Recorded ruling — this was already evaluated.** Epic **#13892** ("Also evaluated and
  deferred: a decode-layer n-gram repetition guard") defers it on a better-grounded reason than
  the one below: *"It only earns its place once something generates long-form output over
  documents; today nothing does."* This analysis does not re-propose it.
- **Delta:** no text-level repetition guard on any locally-decoded path.
- **Visible benefit:** blocks the single most-reported failure of a windowed cache.
- **Hidden cost:** an n-gram ban is blunt — it corrupts legitimately repetitive output (tables,
  CSV, code, enumerations), and the source's own tracker shows the size parameter is hard to set
  (their default of 35 never fires on short repeating units). Adopting it buys a tunable that is
  wrong by default for document-shaped output.
- **Verdict:** **adopt-with-conditions** — only alongside item 1, never enabled on a full-context
  path where it has no blind spot to compensate for. **Effort:** trivial (~25 lines).

#### 4. The model itself, for layout-aware OCR — *rejected-by-hidden-metrics*

- **Already-exists audit:** [media/document/ocr.py:211-229](autobot-backend/media/document/ocr.py#L211-L229)
  — `OcrResult.pages: Dict[int, str]`, plain text per page, no block types, no bounding boxes.
  [pipeline.py:193-213](autobot-backend/media/document/pipeline.py#L193-L213) `_merge_ocr_text`
  folds OCR text only into pages whose text layer is empty.
  [extraction.py:390-424](autobot-backend/media/document/extraction.py#L390-L424) `_pdf_tables`
  gets tables from pdfplumber, which needs a vector line/text layer. So AutoBot genuinely lacks
  layout-aware parsing of *image-only* pages — the gap is real.
- **Why it is still rejected:** ~7 GB weights resident, NVIDIA-only (14 hardcoded `.cuda()`),
  8–19× Tesseract per page on GPU, `trust_remote_code=True` against a hub repo with one branch
  and zero tags, and a prebuilt binary wheel in the documented install path. AutoBot's ingestion
  runs CPU-only and bounded today; adopting this trades every one of those properties for table
  structure on scanned pages. The hidden metrics veto it outright.
- **Recorded ruling — do not re-propose.** Epic **#13892** already carries a
  *"Deliberately out of scope — do not re-propose"* section rejecting exactly this: adopting a
  long-horizon document vision-language model for one-shot multi-page parsing. It lists two
  reasons this analysis reproduced (permanent 6–12 GB GPU residency; CUDA pinning against the
  OpenVINO/NPU direction) and one **stronger** reason this analysis missed: such models emit an
  unanchored markdown blob, **destroying the page provenance** that Wave 2 of that epic exists to
  add. The independent agreement is worth recording; the verdict is not new.
- **What the audit *did* find is a defect — see Gaps item 1.**

### What We Already Do Better

- **Bounded, degradable ingestion.** [ocr.py](autobot-backend/media/document/ocr.py) bounds DPI
  (`MAX_OCR_DPI = 600`), pages (`MAX_OCR_PAGES_CEILING = 500`), total and per-page timeout
  (`MAX_OCR_TIMEOUT = 1800`, `MAX_OCR_PAGE_TIMEOUT`), and per-page pixels
  (`MAX_OCR_PAGE_PIXELS = 40_000_000`) — every one env-var-backed through SSOT, and
  `ocr_availability()` degrades rather than raising. The reference work's batch driver hardcodes
  its parameters, has no resume and no bounds (its own tracker, #17).
- **"Did we look?" is a first-class field.** `OcrResult.attempted`
  ([ocr.py:211-221](autobot-backend/media/document/ocr.py#L211-L221)) and
  `ExtractedDocument.tables_attempted` ([extraction.py:183-187](autobot-backend/media/document/extraction.py#L183-L187))
  exist precisely so an empty result cannot read as a negative finding. The reference work
  publishes a headline number its community measures ~2× worse and leaves the reproduction issue
  unanswered — the failure our `attempted` discipline is built to prevent.
- **Prioritized retention beats tail retention.**
  [context_window_manager.py:352-422](autobot-backend/context_window_manager.py#L352-L422)
  prunes strictly lowest-priority-tier-first, shares proportionally *within* a tier, and
  distributes the rounding remainder deterministically (#13717). The reference work has one
  policy at one plane: keep the last 128 tokens. Our message plane is ahead; only our KV plane
  is behind, and only in the two specifics named in item 1.
- **Provenance survives the read path.** `_merge_ocr_text` rebuilds through `render_pages` so
  OCR'd text carries the same page markers and span arithmetic as text-layer content (#13894).
  The reference work's structured output is a `<|det|>` convention the caller strips with a
  README regex — no parser, no schema, no validation.
- **Revision pinning is a policy we hold.**
  [code_embedding_generator.py:131-132](autobot-backend/code_embedding_generator.py#L131-L132)
  and [ai_hardware_accelerator.py:614-632](autobot-backend/ai_hardware_accelerator.py#L614-L632)
  pass `revision=`. The reference work offers no revision to pin.
- **CPU-only ingestion.** Tesseract + pypdfium2 runs on any node. No GPU is a deployment
  precondition anywhere in the document path.

### Gaps & Opportunities

Prioritized by impact to AutoBot. Items 2–4 fall under existing umbrella **#13030**
("large-model inference on lean hardware is scaffolded but non-functional"); item 1 is new.

| # | Gap | Evidence | Severity | Effort |
|---|---|---|---|---|
| 1 | **A scanned PDF's tables are recorded as "this document has no tables."** `_pdf_tables` runs pdfplumber over every page and returns `(tables, True)` whenever the library ran without raising. On an image-only page pdfplumber finds no lines or rects, so the result is `((), True)` — which the `attempted` contract defines as *"the document has no tables"*. The truth is *"tables were present and this method cannot read them."* This defeats the #13895/#14232 distinction one layer below where it was built, and is `MEASUREMENT_DISCIPLINE` family **F** verbatim: correct, complete, and about a different question. | [extraction.py:390-424](autobot-backend/media/document/extraction.py#L390-L424), [ocr.py:211-221](autobot-backend/media/document/ocr.py#L211-L221) | **P1** | trivial |
| 2 | `forward_pass` accepts `kv_cache` and documents that it does not inspect it; `generate()` keeps no cache at all and re-runs every layer over the full sequence per step. | [layer_inference.py:397,406-408,526-538](autobot-backend/llm_shared/optimization/layer_inference.py#L397) | **P1** | moderate |
| 3 | `trim_to_length` has **zero production callers** — the sliding window is built, corrected, tested, and never runs; and its policy is tail-only, so wiring it unchanged would evict the prompt prefix. | [kv_cache.py:254-305](autobot-backend/llm_shared/optimization/kv_cache.py#L254-L305) + `grep -rn trim_to_length` → tests only | **P2** | moderate |
| 4 | **Re-scoped after cross-reference.** A revision-pinned, integrity-verified registry now exists ([autobot_shared/pinned_model_registry.py](autobot_shared/pinned_model_registry.py), #13034/#17124/#17087) and is wired into the embedding, vision, voice, diarization and hardware-accelerator paths. Repo-wide `# nosec B615` is down from the umbrella's 18 to **5 live suppressions**, 2 of which are documented no-ops (npu-worker loads a *local* directory already verified against its pin). The residual gap is **3 unjustified suppressions, all in the optimization package**, which still resolve a bare model name against a mutable default branch. | [layer_inference.py:198](autobot-backend/llm_shared/optimization/layer_inference.py#L198), [layer_inference.py:565](autobot-backend/llm_shared/optimization/layer_inference.py#L565), [model_inspector.py:260](autobot-backend/llm_shared/optimization/model_inspector.py#L260) | **P2** | trivial |
| 5 | `RECOMMENDED_MODELS["phi-3-mini"]["trust_remote_code"] = True` — a remote-code-execution opt-in sitting in a recommendations table. `vllm.py:73,101` honours the flag if such an entry is passed through as config. **Stated gap:** the only in-repo consumer reads `RECOMMENDED_MODELS.keys()` only (`vllm_base.py:187-189`), so I found no production path that activates it — I did not prove one does not exist. | [providers/vllm.py:271](autobot-backend/llm_shared/providers/vllm.py#L271), [providers/vllm.py:73](autobot-backend/llm_shared/providers/vllm.py#L73), [providers/vllm_base.py:183-189](autobot-backend/llm_shared/providers/vllm_base.py#L183-L189) | **P2** | trivial |
| 6 | No n-gram repetition guard at the token plane. **Already evaluated and deferred by #13892** on the grounds that nothing in AutoBot generates long-form output over documents today. Nothing here changes that; recorded for completeness only, **not** to be filed. | #13892 *"Also evaluated and deferred"*; [llm_shared/models.py:162-163](autobot-backend/llm_shared/models.py#L162-L163) | — | — |

### Specific Code/Files Affected

| File | Change |
|---|---|
| [autobot-backend/media/document/extraction.py](autobot-backend/media/document/extraction.py) | `_pdf_tables` must distinguish "ran and found none" from "ran against pages with no text layer". Simplest honest form: thread the page's text-layer emptiness in and return `attempted=False` (or a third state) for image-only pages, so `has_usable_content` and every downstream consumer stop reading silence as a negative finding. |
| [autobot-backend/llm_shared/optimization/layer_inference.py](autobot-backend/llm_shared/optimization/layer_inference.py) | `forward_pass` actually reads/writes the passed `kv_cache`; `generate()` stops re-concatenating the full sequence and decodes incrementally against it. Delete the "not inspected" paragraph only once that is true. |
| [autobot-backend/llm_shared/optimization/kv_cache.py](autobot-backend/llm_shared/optimization/kv_cache.py) | Add an opt-in retention mode alongside `_retain_tail`: a pinned prefix length plus a fixed ring over positions after it, writing one slot per step instead of cloning the window. Keep `get()`'s existing contract explicit about ordering. |
| [autobot-backend/llm_shared/optimization/model_inspector.py](autobot-backend/llm_shared/optimization/model_inspector.py), `layer_inference.py` | Pass `revision=` from config at the three `# nosec B615` sites, matching `code_embedding_generator.py`. |
| [autobot-backend/llm_shared/providers/vllm.py](autobot-backend/llm_shared/providers/vllm.py) | `trust_remote_code` defaults to `False` in `RECOMMENDED_MODELS`; if a model genuinely needs it, that is an explicit operator decision, not a table default. |

### Not adopted, and why

| Candidate | Reason |
|---|---|
| The model, for layout-aware OCR | GPU-resident, NVIDIA-only, 8–19× slower per page than the CPU path we run today, remote-code model load, no pinnable revision. Hidden costs veto a real capability gap. |
| Eager-attention ring coupling | The source's ring is registered only as `mha_eager`; adopting the pattern must not adopt the attention regression that funds its own latency complaint. |
| Image tiling for vision-token budget | Out of scope for this comparison — AutoBot's vision path (`multimodal_processor/processors/vision.py`) was surveyed but not audited in depth, so no verdict is offered rather than a guessed one. |

### Cross-reference with open issues

Searched open **and** closed issues (`gh issue list --state all --search …`) for every finding
before proposing anything. Two findings were already *ruled on*, three are already *owned*, and
two are new. Net: **2 issues to file, 3 comments to post, 0 re-proposals.**

| # | Finding | Existing issue | Disposition |
|---|---|---|---|
| 1 | Scanned PDF's tables recorded as "no tables" | **none.** Adjacent and distinct: #13895 (CLOSED — the stub that returned `[]`), #14232 (CLOSED — real pdfplumber extraction), #13896 (OPEN/**BLOCKED** — rasterize-then-OCR fallback), #14132 (OPEN — surface unreadable *page numbers*), #15370 (OPEN — tables dropped *downstream* of extraction), #14967, #14971 | **FILED — #17800**, native sub-issue of epic **#13892**, milestone v0.14.0, `bug · priority: high · backend · rag · area: document-ingest`. It sits exactly in the seam #14232 opened and #13896 has not closed: tables became real, the OCR path became real, and the `attempted` flag was never taught that an image-only page is not evidence of absence. |
| 2 | `forward_pass` accepts `kv_cache` and does not inspect it; `generate()` keeps no cache | **#13031** (umbrella #13030 defect **D2**: *"That load sits inside the per-token loop … **No cache anywhere.**"*) | **DO NOT FILE — witness, not a new defect.** Same root, already owned. **Comment posted on #13031** adding the `forward_pass` citation ([layer_inference.py:406-408](autobot-backend/llm_shared/optimization/layer_inference.py#L406-L408)), since the issue frames D2 as checkpoint loading and does not name the ignored parameter. |
| 3 | `trim_to_length` has zero production callers; tail-only policy | **#13033** (D4) — *"retains the oldest window instead of the newest"* | **SPLIT.** D4 itself is **fixed on `origin/main`**: `git show origin/main:…/kv_cache.py` shows `_retain_tail` moving the newest `max_len` positions down to offset 0, and the docstring records the correction. #13033 is **closable on code evidence**; #13030's checklist still shows it `[ ]`. The *residual* — no caller anywhere, and a tail-only policy that would evict the prompt prefix once wired — is **not** in #13033's text → **FILED — #17801**, native sub-issue of **#13030**, `blocked_by` **#13031**, milestone v0.12.0. Evidence comment posted on #13033. |
| 4 | `# nosec B615` suppressions in the optimization package | **#13034** (*"no revision pinning … 18 suppressed B615 findings"*), plus #17087 (CLOSED — 3 further sites) | **DO NOT FILE — owned, and the issue's numbers are stale.** [autobot_shared/pinned_model_registry.py](autobot_shared/pinned_model_registry.py) now exists with integrity verification and is wired into the embedding, vision, voice, diarization and hardware-accelerator paths. Current tree: **29** non-Alembic `revision=` hits (umbrella says *zero*) and **5** live `# nosec B615` (umbrella says *18*), of which the 2 in the npu-worker are documented no-ops — it loads a *local* directory already verified against its pin. **Progress comment posted on #13034** with the remaining 3, and on #13030 for the stale paragraph. |
| 5 | `trust_remote_code: True` as a default in `RECOMMENDED_MODELS` | **none.** #17792 is container/deployment hardening; #17087 (CLOSED) covered unpinned load sites, not this flag | **FILED — #17803**, native sub-issue of **#13034**, milestone v0.9.4 — backend and API, `security · priority: medium · backend · ai-ml · area: lean-hardware`. Carries the *stated gap* verbatim: no production path was found that activates it, and no proof was obtained that none exists. |
| 6 | No n-gram repetition guard at the token plane | **#13892** — *"Also evaluated and deferred: a decode-layer n-gram repetition guard … It only earns its place once something generates long-form output over documents; today nothing does."* | **NOT FILED.** Recorded ruling, better-reasoned than this analysis; re-confirmed in a comment on #13892 so it is not re-derived a third time. Also corrects the audit: `LLMRequest` already carries `frequency_penalty`/`presence_penalty` ([models.py:162-163](autobot-backend/llm_shared/models.py#L162-L163)). |
| — | Adopting the model for layout-aware OCR | **#13892** — *"Deliberately out of scope — do not re-propose"* | **NOT FILED.** Re-confirmed on #13892 with two reasons that section does not list (remote-code model load; no pinnable revision). This analysis reached the same verdict independently and missed the decisive reason: such models emit an unanchored markdown blob, destroying the page provenance that epic's Wave 2 exists to add. Agreement recorded; nothing re-proposed. |

**Two pieces of stale issue metadata found while cross-referencing** (each is a finding in its own
right under the evidence rules, neither is a code defect):

- **#13030's cross-cutting paragraph** asserts *"`grep "revision=" across the backend` → **zero**
  non-Alembic hits … against **18 `# nosec B615`** suppressions … with no mechanism behind it."*
  All three claims are now false — there is a registry, 29 pins and 5 suppressions. The umbrella
  text should be refreshed or it will keep pointing new work at solved ground.
- **#13892's Wave 2 checklist** still shows `#13895 — … PR #14233 open` unticked while #13895 is
  CLOSED, and **#13033** is unticked on #13030 while its defect is fixed in `origin/main`.

**Nothing found was dropped.** Items 2, 4 and 6 and the model verdict are recorded here and
routed to their existing homes rather than refiled — per *ONE defect, ONE fix*, independent
rediscovery raises a finding's priority, never its count.

### Filed — final linkage

| Issue | Title | Parent (native) | Milestone | Labels |
|---|---|---|---|---|
| **#17800** | a scanned page's tables are recorded as "this document has no tables" | **#13892** (epic) | v0.14.0 | bug · priority: high · backend · rag · area: document-ingest |
| **#17801** | the KV sliding window has no caller, and its tail-only policy would evict the prompt prefix | **#13030** (umbrella) · `blocked_by` **#13031** | v0.12.0 | bug · priority: medium · backend · ai-ml · area: lean-hardware |
| **#17803** | `trust_remote_code` defaults to true in the recommended-models table | **#13034** | v0.9.4 — backend and API | security · priority: medium · backend · ai-ml · area: lean-hardware |

Comments routing the findings that are **not** new issues: #13031 (D2 witness), #13033 (D4 fixed
in `origin/main`, closable, residual split to #17801), #13034 (18 → 3 residual suppressions,
registry now exists), #13030 (three stale cross-cutting claims, one closable child), #13892 (new
child; both "do not re-propose" rulings re-confirmed).

Relationships read back with `gh api repos/$REPO/issues/<parent>/sub_issues` and
`.../issues/17801/dependencies/blocked_by` — all four edges present.
