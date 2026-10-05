---
tags:
  - research
---

# Source Analysis: Layout-Aware Document Conversion and Hybrid Chunking

Related: [[document-to-markdown-conversion-pipeline]] (a lighter conversion utility, Phase 2
done) and [[long-horizon-document-parsing-ring-cache]] (a vision-OCR parsing model, Phase 2 done).
This source sits between the two: a full document-understanding pipeline, not a format shim
and not a single model.

## What It Is

An MIT-licensed Python document-understanding toolkit started by a large vendor's research lab
and now hosted by an open-source foundation. ~2 years old, very large user base, daily commits,
~1,000 open issues (158 labelled bug; 89 tagged for stale-closure). It converts ~35 input formats
(PDF, Office, OpenDocument, HTML, EPUB, e-mail, LaTeX, several XML schemas, images, audio,
video) into **one typed document model** that keeps hierarchy, reading order, tables, formulas,
figures and **per-element provenance (page number + bounding box)**, then exports to Markdown,
HTML, lossless JSON or a tag format, and chunks it for RAG. Ships as library, CLI, an HTTP
service and an MCP server; framework adapters exist for the common RAG stacks.

## Architecture & Key Patterns

- **Format option → (backend, pipeline) pair.** `DocumentConverter` maps each input format to a
  `FormatOption` naming a parsing *backend* (format reader) and a *pipeline* (processing
  recipe). ~30 backends; pipelines: simple (declarative formats), standard PDF (layout model +
  OCR + table-structure model), VLM (a page-to-document vision model), ASR, video, extraction.
- **Unified intermediate document model** (in a separate core package): every backend and
  pipeline emits the same typed tree; exporters and chunkers only ever see that model. Format
  quirks stop at the backend.
- **Staged, threaded page pipeline.** The standard PDF pipeline runs per-stage worker threads
  linked by bounded queues (`ThreadedQueue` with blocking `put`, `get_batch(size, timeout)`,
  explicit `close()`), per-run isolated queues, back-pressure, and per-stage batch sizes so GPU
  stages batch while CPU stages stream.
- **Page batching + document timeout.** Pages are processed in batches (default 4); a
  `document_timeout` is checked between batches and yields `PARTIAL_SUCCESS` rather than
  failure. Status is a 4-state enum (success / partial / failure / skipped) with per-item errors.
- **Plugin factories via a hook system.** OCR engines (8 built in), layout, table-structure and
  picture-description models are registered through factories; third-party plugins load only
  when `allow_external_plugins=True`, and API-backed models only when
  `enable_remote_services=True`. Both default off.
- **Enrichment pass.** After assembly, element-level enrichment models (picture description,
  code/formula recognition, chart-to-table) run in element batches over the finished tree.
- **Hybrid chunker.** Chunking first walks the document tree (one chunk per structural element,
  carrying its heading path, captions and provenance as metadata), then a tokenizer-aware pass
  splits oversize chunks and **merges undersized peers that share the same heading context**
  (`merge_peers=True`), bounded by the embedding model's real token limit.
- **Contextualize for embedding.** A chunk exposes a "contextualized" text (heading path +
  body) used for embedding, distinct from the raw text shown to the user.

## Notable Implementation Details

- Provenance is a first-class field on every element, so a chunk can cite page + box and a UI
  can highlight the source region — retrieval citations are structural, not string-matched.
- Reading order and multi-column layout are recovered by a dedicated layout model plus
  post-processing, not by PDF text-stream order — the main reason its PDF output beats
  text-extraction libraries on academic and financial documents.
- Tables are reconstructed into cell grids by a table-structure model, so they export as real
  tables, and the chunker can serialize them row-wise instead of splitting mid-table.
- Model weights can be pre-fetched to an `artifacts_path` for air-gapped runs.

## Strengths

- One document model for every format — a single place to attach provenance, chunking and
  export. This is the core idea worth studying.
- Structure-preserving, token-budget-aware chunking with heading context.
- Explicit partial-success semantics and a document-level time budget.
- Safe defaults on the two dangerous switches (external plugins, remote services).
- Fully local execution path.

## Weaknesses / Limitations

- **Unbounded by default:** `max_num_pages` and `max_file_size` default to `sys.maxsize`, and
  `document_timeout` defaults to none — a caller that forgets to set them accepts any size.
- The library fetches URLs itself (plain HTTP client) — a URL-ingest path bypasses whatever
  egress policy the host application enforces unless the caller downloads first.
- Heavy dependency and model footprint for the PDF/VLM paths (deep-learning runtime, several
  model checkpoints, optional OCR engines); the default tokenizer for chunking is pulled from a
  model hub.
- Document-level concurrency is marked experimental and expected to give no benefit on a
  GIL-bound interpreter; throughput comes from page-stage threading only.
- Large, fast-moving API surface (two pipeline generations coexist: "legacy" and "threaded"
  standard PDF pipelines; three versions of its own PDF parser backend).
- High issue backlog relative to maintainer capacity (stale-closure automation is busy).

## Visible vs Hidden Metrics

- **Visible:** format breadth (~35), layout/table/formula quality on PDFs (self-reported, plus a
  published technical report on its own layout dataset — not independently reproduced here),
  very large adoption, foundation governance, MIT licence, framework integrations, MCP server.
- **Hidden:** a deep-learning runtime and multiple model checkpoints to pin, download, cache and
  upgrade (model-revision pinning applies to every one); per-page CPU cost on a non-GPU host is
  high; a fast-moving API with parallel pipeline generations means upgrade churn; its own URL
  fetcher sits outside a host's egress guard; unbounded defaults make size limits the caller's
  job; per-model licences differ from the code licence.
- **Weighing:** for a product whose knowledge base ingests mostly text, Markdown and Office
  files, the visible PDF-quality win is concentrated in one format while the hidden costs
  (model ops, footprint, upgrade churn) apply to the whole ingest path. The patterns — a single
  provenance-carrying document model and heading-aware peer-merging chunking — transfer without
  the dependency; adopting the library wholesale pays off only if scanned/complex PDFs are a
  primary corpus and a GPU/NPU worker can host it out of the main backend.

## Phase 2 — AutoBot Comparison (against `origin/main` 12e1a56377)

### What We Can Adopt

| # | Pattern | Already-exists audit | Visible benefit | Hidden cost | Verdict | Effort |
| --- | --- | --- | --- | --- | --- | --- |
| A1 | **Structure-carrying extraction for DOCX** — keep heading level from paragraph style and keep tables *in position* instead of appended | `media/document/extraction.py:469` `extract_docx` keeps `p.text` only (style dropped) and returns tables as a separate tuple; `provenance.render_text_and_tables` appends them after the body. No open/closed issue covers it (searched "docx heading", "reading order table docx"). | Heading-aware chunkers (`autobot_shared/doc_chunking.py`, #17209) get real structure from Office files; a table stays under the heading that introduces it | Small: python-docx already pinned; style names vary by locale/template (`Heading 1` vs localized) — needs an outline-level fallback | **adopt** — filed as #17985 (child of #14967) | moderate |
| A2 | **Heading-path context on every chunk + contextualized embedding text** (embed `heading path + body`, display body) | `doc_chunking.create_chunk` stores `section`/`subsection` as metadata only; nothing prepends them to the embedded text; upload path does not chunk at all (#17830) | Better recall for short chunks whose meaning lives in the heading | Re-embedding the corpus when enabled; changes ranking → needs a benchmark (`knowledge/rag_benchmarks.py` exists) | **adopt-with-conditions** — after #17830, behind the RAG benchmark; belongs under #14967 | moderate |
| A3 | **Undersized-peer merging bounded by the embedder's real token limit** | `doc_chunking.chunk_large_content` splits oversize sections; `utils/text_chunking.chunk_text` packs paragraphs; neither merges small sibling sections sharing a heading, and sizes use `estimate_tokens` not the embedding model's tokenizer | Fewer one-line chunks; no silent truncation at the embedder | Tokenizer coupling to the configured embedding model | **adopt-with-conditions** — same home as A2 | moderate |
| A4 | **Partial-success status + per-document time budget for ingest** | `ocr.py` has per-page/total OCR timeouts and `max_ocr_pages`; `add_document` has one `wait_for` that returns `timeout` and stores nothing — no partial state | A 400-page PDF that runs out of time keeps the 300 pages it read | A third status to surface in UI and retry logic | **adopt-with-conditions** — only once #17830 chunks, since partial only means something per chunk | moderate |

Not adopted: **the library itself** — rejected on hidden metrics (model runtime and checkpoint
pinning on the main backend, its own URL fetcher outside rule 8's egress guard, unbounded size
defaults, two coexisting pipeline generations). Reconsider only as an isolated worker for
scanned/complex PDFs if #13892 shows tesseract quality is the bottleneck. **Bounding-box
provenance** — rejected for now: page-level provenance is built and not yet wired (#15374);
boxes add nothing until pages reach the chunk.

### What We Already Do Better

- **One canonical extractor already exists** — `media/document/extraction.py` replaced five
  forked PDF extractors (#13893) with typed `ExtractedDocument` / `PageText` / `PageSpan`, the
  same "one model, many readers" idea at a fraction of the footprint.
- **Bounded by default** — OCR has env-backed page caps and timeouts (`ocr.py:83-136`), table
  extraction is capped (`max_table_pages`, `max_table_chars`); the source defaults to unbounded.
- **Egress** — connectors fetch through the guarded path; the source's URL input fetches with a
  bare HTTP client.
- **Redaction at extraction** — `knowledge/connectors/content_extraction.py:40,76` redacts
  before text leaves the extractor; the source has no redaction stage.
- **Scanned-PDF detection is explicit** — `has_usable_text_layer` / `empty_page_numbers` say
  which pages are empty instead of silently emitting nothing.

### Gaps & Opportunities (by impact)

1. **Upload never chunks** — #17830 (open). Blocks A2–A4; the source's whole RAG value is chunking.
2. **Page provenance computed, never attached to chunks** — #15374 (open): `chunk_page_map`
   (`provenance.py:75`) has zero production callers. The source's core differentiator is exactly
   this wire. Feeds #17828 (citations).
3. **DOCX structure discarded** — A1, filed as #17985 (child of #14967).
4. **Hierarchical retrieval / table ingest** — #14967 (open) is the home for A2/A3.
5. **Scanned PDFs** — #13892 (open); a layout model is the heavyweight answer, held behind it.

### Specific Code/Files Affected

- `autobot-backend/media/document/extraction.py` — `extract_docx` emits heading-marked text with
  tables interleaved (A1).
- `autobot-backend/media/document/provenance.py` — `render_text_and_tables` gains an in-order
  mode; `chunk_page_map` gets its caller (#15374).
- `autobot-backend/knowledge/documents.py` — `add_document` chunks (#17830), records partial
  status (A4).
- `autobot_shared/doc_chunking.py` — heading-path contextualized text and peer merging (A2, A3).

### Cross-reference with the backlog

Searched open and closed issues in the backlog's vocabulary (25 queries; closest bodies read:
#14967, #14971, #13245, #13246, #14485, #15370, #17209).

| Finding | Existing home | Coverage | Action |
| --- | --- | --- | --- |
| A1 DOCX headings dropped, tables relocated | none — #14971 is column-header binding *inside* a table, #15370 is table-only upload rejection | **not covered** | file new, child of #14967; relate #17209 (clause chunker needs DOCX structure), #14971, #17058 |
| A2 heading path in embedded text | #17209 puts clause path in **metadata** only; #13245 compares chunkers | partial | comment on #13245: add a "contextualized text" arm |
| A3 peer merging + real tokenizer | #13246 step 3 already covers the real tokenizer; merging not mentioned | partial (tokenizer covered) | comment on #13246: add min-size peer merging to the sweep |
| A4 partial-success ingest | #17830 (chunking) is the prerequisite; nothing tracks partial state | **not covered** | file new, `blocked_by` #17830, child of #17527 |
| Page provenance unwired | #15374 | covered | witness comment on #15374 (the source's core differentiator is this wire) |
| Upload never chunks | #17830 | covered | none |
| Two semantic chunkers | #14485 | covered | none |
| Scanned / complex PDFs, layout model | #13892, #16519 | covered | note the heavyweight option on #13892 only if tesseract quality is shown to be the bottleneck |
| Retrieval quality unmeasurable | #13251 (epic over #13244/#13245/#13246) | covered | gates A2/A3 |
