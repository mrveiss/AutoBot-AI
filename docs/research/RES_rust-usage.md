# Research: Rust language usage in AutoBot

**Summary:** AutoBot contains no first-party Rust — 0 tracked `.rs` files, no `Cargo.toml`,
no `pyo3`/`maturin` build. Rust reaches AutoBot only as compiled wheels of Python
dependencies and the ChromaDB 1.x server, and as a language name the code tools recognise
but do not analyse.

## Phase 1 — Source Analysis: Rust in the AutoBot tree (2026-10-25, `main` @ `de1db1431b`)

### What It Is

Rust is an indirect runtime dependency, never a language AutoBot is written in. Audit:
`git ls-files | grep -c '\.rs$'` → `0`; no `Cargo.toml`, `Cargo.lock` or `rust-toolchain`
is tracked.

### Where Rust is present

| # | Path | Kind | What it is |
| --- | --- | --- | --- |
| 1 | `chromadb>=1.5.9` (backend requirements) · `docker-compose.hardened.yml:74` | runtime binary | ChromaDB 1.x server and `chromadb_rust_bindings`; owns the compactor and the `seq_id` BLOB layout handled in `autobot-backend/utils/chromadb_store_repairs.py:293` |
| 2 | `pydantic>=2.14.1` | wheel | `pydantic-core` is Rust; it emits the Rust-regex `\z` anchor that `autobot_shared/openapi_schema.py:19-25` rewrites (#13465) |
| 3 | `tiktoken==0.14.0`, `tokenizers>=0.22.2,<0.24` | wheel | PyO3 extensions; pinned to versions with cp314 wheels so no source build runs (#9825, #10331) |
| 4 | `cryptography`, `bcrypt>=5.0.0` | wheel | Rust-backed crypto primitives |
| 5 | `autobot-backend/code_intelligence/base_analyzer.py:66,249,271` | language label | `Language.RUST` for `.rs`, listed in `CLASSIFICATION_ONLY_LANGUAGES` — classified, no analyzer targets it |
| 6 | `utils/file_categorization.py:378,499`, `api/code_search.py:244`, `api/development_speedup.py:491`, `DevSpeedupView.vue:62` | language label | Rust in extension maps and supported-language lists; `target/` skipped as build output |

### Past incidents caused by the Rust layer

- #1180 — SIGSEGV in `chromadb_rust_bindings` with two concurrent `PersistentClient`s.
- #1390 — ChromaDB multi-worker compactor error broke the doc indexer at startup.
- #13465 — `pydantic-core` `\z` anchor inverted validation in every JS client.
- #9825 — `tiktoken` 0.11 built `pyo3-ffi` from source and capped at Python 3.13.

### Strengths

- Rust performance in hot paths (validation, tokenisation, vector store, crypto) with no
  Rust toolchain in the repo, CI or install path.
- Wheel-only pins keep installs toolchain-free on Python 3.14.

### Weaknesses / Limitations

- Rust failure modes are opaque from Python: segfaults (#1180) and on-disk formats (#1390)
  are seen only through their symptoms.
- A wheel pin that drops below a cp314 wheel brings in a Rust source build with no toolchain
  present (#9825 pattern); nothing guards against that class except the comments on the pins.
- Rust source in a user's codebase is classified but not analysed (`CLASSIFICATION_ONLY_LANGUAGES`).

### Visible vs Hidden Metrics

- **Visible:** speed of the Rust-backed dependencies (self-reported by those projects; not
  benchmarked in AutoBot).
- **Hidden:** native crashes that Python cannot catch, version pins tied to wheel
  availability, and on-disk formats AutoBot has to repair around.
- **Weighing:** taking Rust in as wheels costs far less than writing first-party Rust, which
  would add a toolchain, a `maturin` build, cross-compilation for the NPU/Windows workers and
  a second language for the sole maintainer. Nothing found here justifies first-party Rust.

## Phase 2 — AutoBot Comparison: Rust options → AutoBot

### What We Can Adopt

| # | Candidate | Already-exists audit | Visible benefit | Hidden cost | Verdict | Effort |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Fail the install when a pinned package has no wheel for the target Python, instead of quietly building it from source | `.github/actions/setup-python-ci/action.yml:211` and `install-bare-metal.sh:336` use `--prefer-binary`, which only *prefers* wheels and still falls back to an sdist. No wheel-availability check found (`git grep only-binary\|no-binary` → none). The same thing happened twice: #9825 (tiktoken, Rust) and #14279 (spacy, not Rust) | A missing wheel fails at the pin, with the package name, before deploy | An allowlist for packages that legitimately ship only an sdist; the check has to know the target Python version | **Adopt.** Fix it once for every package, not just the Rust ones | moderate |
| 2 | Rust source analysis in code intelligence via `tree-sitter-rust` | `services/knowledge/code_indexer.py:193,376` parses only Python and JS. `Language.RUST` is in `CLASSIFICATION_ONLY_LANGUAGES` (`base_analyzer.py:271`). `tree-sitter>=0.26.0` is already in `autobot-backend/requirements.txt:97` | Rust repos get indexed symbols, not just a language label | One more grammar wheel to pin (Python 3.14 wheels not verified); a new indexer path to test; no known user asking for it | **Adopt with conditions:** only once multi-language indexing is on the roadmap, then as one class change for every classification-only language, not Rust alone | moderate |
| 3 | Swap a Rust-backed library into a hot path (e.g. `orjson` for `json`) | No `orjson`/`msgspec`/`ujson` import or pin found | Faster serialisation (the library's own claim) | A new native dependency and pin; no profile shows JSON is a bottleneck | **Rejected (hidden costs outweigh the gain)** until a profile names the hot path | trivial |
| 4 | First-party Rust (PyO3/`maturin`) module | 0 `.rs` files; no `Cargo.toml` | Native speed in a chosen hot path | Toolchain in CI and install, cross-builds for the NPU and Windows workers, a second language for the sole maintainer, native crashes that Python can't catch | **Rejected (hidden costs outweigh the gain)** | significant |

### What We Already Do Better

- **ChromaDB concurrent-client crash (#1180):** `utils/chromadb_client.py:88-104` caches one
  `PersistentClient` per path under `_local_open_lock` and runs `prepare_local_store` before
  opening it. That closes the double-client segfault path inside the backend. The
  standalone scripts under `autobot-infrastructure/shared/scripts/` still open their own
  client (`populate_kb_chromadb.py:162`, `utilities/migrate_*_to_chromadb.py`). That only
  matters if one runs while the backend is up; not verified.
- **Rust regex anchor (#13465):** fixed once in `autobot_shared/openapi_schema.py`, guarded by
  `autobot_shared/tests/test_openapi_pattern_anchors.py`.
- **Using Rust through wheels only:** AutoBot gets Rust performance with no Rust toolchain anywhere.

### Gaps & Opportunities (by impact)

1. Install path quietly falls back to building from source (#1). It has broken deploys twice.
2. Rust/C/Java and other source code is classified but never indexed (#2). Low impact until
   multi-language code intelligence is wanted.

### Specific Code/Files Affected

- #1: `.github/actions/setup-python-ci/action.yml`,
  `autobot-infrastructure/shared/scripts/install-bare-metal.sh` (go from `--prefer-binary` to
  wheels-only plus an sdist allowlist, or add a wheel-availability check over the pins in
  `constraints/shared.txt` and the `requirements*.txt` files), plus a repo test.
- #2: `autobot-backend/services/knowledge/code_indexer.py` (a grammar registry in place of
  the per-language imports), `code_intelligence/base_analyzer.py` (shrink
  `CLASSIFICATION_ONLY_LANGUAGES`), `autobot-backend/requirements.txt`.

## Phase 2b — Why AutoBot is Python, and where that actually hurts

No ADR records the language choice (`docs/adr/001`–`010` cover distribution, Redis, NPU,
chat, frontend, planning, OAuth, the browser and role placement). This section rebuilds the
reasoning from the code and the incident record.

### What the workload is

- **Size:** 7,371 tracked `.py` files (4,895 in `autobot-backend`, 604 in
  `autobot-slm-backend`, 506 in `autobot_shared`), against 1,395 `.ts` and 611 `.vue`.
- **Shape:** I/O-bound orchestration. A request waits on an LLM (Ollama), Redis, ChromaDB
  or HTTP. The heavy compute already runs natively: llama.cpp behind Ollama, OpenVINO on
  the NPU worker, torch/transformers/sentence-transformers/onnxruntime for embeddings, and
  the Rust ChromaDB server.
- **Ecosystem lock-in:** `torch`, `transformers`, `sentence-transformers`, `openvino`, `spacy`,
  `llama-index-*`, `langchain-*`, `celery` and `fastapi` are all in the backend/NPU/AI-stack
  requirements. All of them are Python-first; Rust equivalents cover only part of this set.

### Where Python did hurt — the incident record

| Incident | Measured | Actual root cause | Fix that landed | Would Rust have fixed it? |
| --- | --- | --- | --- | --- |
| #12866 GUI "Backend API Unreachable" | `/api/service-monitor/vms/status` p90 = 12 s; 11/40 polls > 5 s on an idle box | A code-analysis scan held the GIL while running in a thread inside the **single** API process (`uvicorn --workers 1`) | `code_intelligence/shared/process_offload.py` moves the scan into a `ProcessPoolExecutor` with its own GIL | Partly: no GIL means no stall, but see #12884 |
| #12884 / #12887 GIL hold in `_check_sql_injection` | 6.9 s per scan at 20k matches | **O(n·m) algorithm:** `content[:match.start()].count("\n")` rescanned the file for every match (23 sites) | Precomputed line offsets: 174× faster, still Python | No. The same algorithm in Rust is still O(n·m) |
| #940 6-minute backend startup | 6 min of 504s after every restart | Model and ChromaDB initialisation in `lifespan` | Lazy / background loading | No. The time is spent loading models |
| #6811 TTS pipeline depth | — | Pocket TTS is GIL-bound | Pipeline depth made configurable | Possibly. The one genuinely CPU-bound Python path found |

**The pattern:** the stalls came from *where* CPU work runs (inside the single-process API
event loop) and from *algorithms*, not from Python's speed. 1,476 `asyncio.to_thread` /
`run_in_executor` call sites push work off the event loop, but a thread does not escape the
GIL. Only 4 modules use `process_offload`.

### "Everyone is writing Rust" — what holds up

- What holds up: new **infrastructure binaries** (package managers and linters, vector
  databases, proxies, CLI agents) and **Rust cores under a Python surface** (`pydantic-core`,
  `tokenizers`, `tiktoken`, `cryptography`, ChromaDB 1.x). AutoBot already uses the second
  pattern in every one of those places (Phase 1 table).
- What doesn't follow: that an LLM-orchestration application gains much by rewriting its
  Python glue. Request time is spent waiting on models, and the model ecosystem AutoBot
  depends on is Python-first.
- Not measured: industry share. This is general knowledge, not a sourced statistic.

### Options, weighed

| Option | Visible | Hidden | Verdict |
| --- | --- | --- | --- |
| Rewrite the backend in Rust | Memory safety, no GIL, one binary | ~4.9k backend files; loses or has to re-bind torch/transformers/OpenVINO/llama-index; a second stack for the sole maintainer; years of feature freeze | **Rejected (hidden costs outweigh the gains)** |
| Rust for a new standalone service (e.g. a gateway or event router) | Low memory, high concurrency | A second toolchain in CI, the builtin updater and Ansible roles; nothing to share with `autobot_shared` | **Rejected** until a service has a measured throughput limit that Python + uvicorn can't meet |
| Targeted PyO3 extension | Native speed in one hot path | A `maturin` build, a wheel per platform (NPU and Windows workers) | **Adopt with conditions:** only after a profile names a pure-Python CPU path that an algorithm fix or an existing native library (tree-sitter, `re2`) can't solve |
| Move remaining CPU-bound work out of the API process | Fixes #12866-class stalls for every endpoint at once | Pickling limits; pool lifecycle (`process_offload.py` already handles both) | **Adopt:** audit the 1,476 thread-offload sites for CPU-bound (not I/O) work and move those to the process pool |
| Free-threaded CPython (3.14t) | Removes the GIL without a language change | Every native dependency needs free-threaded wheels; torch/OpenVINO/ChromaDB support not verified | **Investigate:** check wheel availability before any commitment |

### Discovered problem

- `docs/troubleshooting/COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md:685` tells readers to set
  `export PYTHON_GIL_DISABLED=1`. That is not a runtime switch: free-threaded CPython reads
  `PYTHON_GIL=0` (or `-X gil=0`) on a `t` build, and `Py_GIL_DISABLED` is a build-config
  flag. Needs a doc fix.

## Phase 3 — Slow algorithms and CPU work in the API process (sweep of `main` `de1db1431b`, 2026-10-25)

The owner's direction: when an algorithm is slow, replace the algorithm. Native code comes after that, not instead of it.

| Class | Instances | Home |
| --- | --- | --- |
| Line-number rescan per regex match (O(n·m)); the `utils/line_index.py` fix exists but nothing guards against new sites | 22 sites in 9 files (12 in `cross_language_patterns/extractors.py`) | #12887 (reopened, ratchet added) |
| A list used as an LRU, queue, set or byte buffer: `pop(0)`, a sort every iteration, list membership, `bytes +=`, rebuilding a whole string per match | 13 site groups, incl. the LLM L1 cache `llm_shared/cache.py` | #19564 |
| All-pairs loops where an inverted index, a hub node or one numpy call would do | 7, incl. O(E²·F) entity co-occurrence in `agents/graph_entity_extractor.py:494` | #19565 |
| One regex pass per pattern, and `findall` used only to test for a match | 4, incl. `security/prompt_injection_detector.py:620` on the request path | #19566 |
| Redis `KEYS` on live paths | 5 new sites, incl. a wildcard-prefix `KEYS` on every checkpoint load | #18116 (existing; comment added) |
| Pure-Python CPU work in a thread (or on the event loop) of the `--workers 1` API process | 23 CPU-bound sites + 5 moderate; ~150 sites and 4 wrappers not yet audited | #19567 |

Rust would fix none of the first four classes: an O(n²) algorithm is O(n²) in any language. The sixth class is what a GIL-free runtime would ease; process offload fixes it on today's build.

## Linked issues

- #19559 Umbrella: runtime responsiveness — fix the algorithm first, then move CPU work out of the API process, then consider runtime/native options
- #19560 ci(deps): installs silently build from source when a pin has no cp314 wheel — --prefer-binary falls back to the sdist
- #19561 docs(troubleshooting): PYTHON_GIL_DISABLED=1 and a throwaway-interpreter gc.collect() are presented as fixes and do nothing
- #19562 research(runtime): can the backend run on free-threaded CPython 3.14t — cp314t wheel audit of every native pin
- #19563 feat(code-intelligence): index Rust and the other classification-only languages through one tree-sitter grammar registry
- #12887 perf(code-intel): 19 remaining per-match line rescans still hold the GIL (follow-up to #12884)
- #19564 perf: lists used as LRU, queue, set and buffer — pop(0), per-iteration sort, list membership and bytes += make 13 loops quadratic
- #19565 perf: all-pairs loops where an inverted index, a hub node or one vectorised call would do — 7 sites, incl. O(E²·F) entity co-occurrence
- #19566 perf: regex pattern-per-pass and findall-for-truthiness — prompt-injection detector collects every match on the request path
- #19567 perf(runtime): 23 request paths run pure-Python CPU work in a thread of the single API process — move them to process_offload or Celery (#12866 class)
- #18116 perf(redis): KEYS still scans the whole keyspace on live paths — /kb-conflicts per request, KB clear, analytics cache invalidation
