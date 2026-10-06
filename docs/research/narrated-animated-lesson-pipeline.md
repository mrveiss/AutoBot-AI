# Narrated, Animated Lesson Pipeline (Document → Interactive Web Lesson)

Status: Phase 1 + Phase 2 complete. Filed as umbrella #18024 (children #18015–#18022) + standalone #18023.
Date: 2026-10-05

## Source Analysis: an agent skill that turns a PDF textbook into narrated, animated, interactive static web chapters

### What It Is

An MIT-licensed agent skill (a `SKILL.md` + references + helper scripts + a JS engine) from an
independent developer, published days before this review (~30 commits). Given a PDF, a coding agent
follows a fixed pipeline — intake → split PDF by outline → chapter map → per-chapter storyboard →
TTS narration → hand-authored SVG animation beats + in-picture quizzes → static site. The output is
plain HTML/JS/CSS/MP3 with no backend; progress lives in `localStorage`. Maturity: early; the engine and helpers are
explicitly biased toward maths because that was the first book.
Sample output: two maths books, 68 + 20 chapters, all in English.

### Architecture & Key Patterns

- **Skill-as-pipeline, not app.** The "product" is an instruction file driving an agent; Python
  scripts are small single-purpose tools run via ephemeral `uv run --with <dep>` (no project venv).
- **Beat model.** A chapter is one 1600×900 SVG stage. Each *beat* = one narration clip + a function
  that schedules tweens on a timeline. Beats are deterministic so seeking replays prior beats
  instantly to rebuild state.
- **Word-mark sync.** Narration text carries `[[mark]]` tags before words. TTS (word-boundary
  events) yields per-word timestamps; a `timings.js` maps each mark → start time of the following
  word, plus sentence-level caption cues. Animations call `m('mark', offset)` so motion lands on the
  spoken word.
- **Per-book engine copy.** Each book vendors its own `engine.js/.css` (~108 KB) so later engine
  changes never break earlier books — fork-by-copy versioning.
- **File-based state for multi-agent work.** `BOOK.md` (conventions + helper index),
  `chapters.md` (status table), `chapters/chNN.md` (storyboard, errata). A coordinator runs the
  pilot itself, then dispatches one fresh subagent per chapter sequentially, briefed with paths
  rather than conversation history; the coordinator alone registers results.
- **Agent-run QA.** Headless-browser scripts: 4-up contact-sheet screenshots per beat
  (`shot.py`), an "opening blank" detector that samples visible-element counts over each beat's
  first seconds (`check_blank.py`), a volume-control regression (`check_volume.py`), an e2e
  template for quiz grading.

### Notable Implementation Details

- **TTS cache keyed on spoken text only** (`sha1(voice|rate|clean_text)`): moving `[[marks]]`
  recomputes timings from cached word times without re-synthesis; a legacy raw-text key is accepted
  once then upgraded. Every write is atomic (temp file + `replace`), and the cache is persisted after
  each beat so a mid-run failure loses nothing.
- **Mark resolution** maps a char position in cleaned text to the first located spoken word at/after
  it; an unmatched mark is a hard error rather than a silent drift.
- **Opening lead-in auto-correction:** if a beat clears the stage and nothing appears within 0.8 s,
  the runtime shifts the opening tween group forward — a runtime guard for a common authoring defect.
- **Exact-answer grading:** quiz parser accepts −5, 3/4, 2 1/4, 0.75 as exact rationals using safe
  integers; "lowest terms" is an opt-in constraint; explicit rule never to judge irrationality from
  finite digits.
- **Keyboard-first interaction contract:** every new question type must define a key handler and a
  hint line; help overlay lists global keys.
- **Robust progress loading:** malformed/`null`/non-object `localStorage` → empty progress, only
  arrays of positive integers count as completion; storage key kept stable across a project rename.
- **Content discipline baked into the authoring guide:** "the animation is the argument", one new
  thing at a time, same colour = same meaning, drawings to scale or labelled otherwise,
  approximations written as ≈, show the common mistake crossed out.
- **Private-source hygiene:** source PDFs, page images and extracted text are kept outside the
  static output and `.gitignore`d; explanations are re-created, not copied.

### Strengths

- Clear, repeatable pipeline with explicit human approval gates (book map, pilot chapter).
- Deterministic, seekable timeline — enables frame-exact screenshots via `?beat=N&t=S` for review.
- Well-engineered incremental TTS with crash-safe caching.
- Automated visual QA designed for an agent to read (contact sheets, blank detector) — the agent
  checks its own output rather than relying on the human for every defect.
- Context economy for subagents: brief with paths and a map row, not history; workers return a few
  lines.
- Zero-backend output: trivially hostable, offline-capable, no accounts.

### Weaknesses / Limitations

- **Every chapter is hand-coded JS by the model.** No declarative scene format; quality depends
  entirely on the model (README states it targets one specific frontier model only).
- Engine is a ~90 KB global-namespace script; chapter helpers can collide with engine globals
  (documented trap: a redeclaration halts the page).
- Domain bias: helpers are algebra/geometry; humanities, picture books, other languages and image
  generation are listed as future work.
- TTS depends on a free, unofficial cloud speech endpoint (network-bound, ToS/availability risk,
  no offline voice).
- Per-book engine copies mean bug fixes must be re-applied manually to each book (the review doc
  says so explicitly).
- No accessibility story beyond captions and keyboard (no screen-reader semantics for the SVG
  argument, no reduced-motion for lessons beyond cover art).
- QA is heuristic (visible-element counts, eyeballed sheets); pedagogy, pacing and aesthetics are
  explicitly left to the human.
- Very young project; no CI workflow in the tree (only an e2e *template*), no release history.

### Visible vs Hidden Metrics

- **Visible:** polished demo video and live bookshelf; ~190 stars within ~2 days; "one-shot"
  animated lessons from a PDF. All self-reported; no independent evaluation of learning outcomes,
  authoring cost per chapter, or failure rate.
- **Hidden:** token cost — each chapter is a long agent session writing hundreds of lines of
  bespoke SVG/JS plus screenshot review loops; reliance on one frontier model; a third-party TTS
  endpoint with no SLA; per-book engine forks that drift; human review still required for every
  chapter's pacing and pedagogy; content licensing of source books is left to the user.
- **Weighing:** for a one-off showcase or a small curated course the visible win is real. For a
  platform that would generate lessons on demand at scale, the hidden costs (per-chapter token
  spend, model lock-in, forked engines, unofficial TTS) dominate; the *reusable* value is in the
  techniques — word-mark narration sync, text-keyed incremental TTS cache, deterministic seekable
  timelines, agent-readable visual QA, and path-briefed sequential subagents — rather than the
  product as a whole.

---

## AutoBot Comparison: the reference work → AutoBot

Steer from the owner: **if this is new to AutoBot, it ships as a plugin.** Audit run 2026-10-05
against `main` @ `176ce734d8` (read-only; plugin claims spot-checked by hand).

### Verdict

Generating narrated, animated lessons is **new** to AutoBot. The repo has zero hits for `quiz`,
`flashcard`, `storyboard` or `curriculum`. It belongs in a new core plugin,
`plugins/core-plugins/lesson-generation-plugin/`. That plugin needs four things the plugin SDK
or the shared core does not provide today:

1. A way for a plugin to serve the HTML it generates. Plugins have no HTTP routes at all.
2. Word-level timings for narration.
3. Splitting a PDF by its outline.
4. A visual check of generated pages.

These four are core work. Building them inside the plugin would fork shared code, and the
owner's design-system rule forbids a second implementation.

### What We Can Adopt

| # | Technique | Lands in | Already-exists audit | Visible benefit | Hidden cost | Verdict | Effort |
|---|---|---|---|---|---|---|---|
| A1 (#18022) | **Lessons as a plugin**: a `generate_lesson` tool takes a document, produces a storyboard, then narration, then a static lesson bundle | new `plugins/core-plugins/lesson-generation-plugin/` (manifest in the `image-generation-plugin/plugin.json` style; tool registered via `tool_sdk` `ToolSDKRegistry.register`, as `image-generation-plugin/main.py:56`) | grep `quiz\|flashcard\|storyboard\|curriculum\|education` → 0; the nearest thing is canvas `CellType` (`canvas/models.py:35`): text/code/chart/image, no animation | a new product capability, isolated, can be enabled or disabled | each chapter is a long LLM run | adopt-with-conditions (see A2) | significant |
| A2 (#18020) | **Declarative beats instead of LLM-written JavaScript**: the model emits a JSON beat spec (stage objects, tweens tied to `[[marks]]`, questions); one engine in the plugin renders every lesson | inside the plugin | no beat/timeline concept anywhere (same grep) | far fewer tokens per chapter; any model can produce it; the spec can be checked against a schema | the engine needs a fixed set of primitives, so some subjects need new ones | adopt; this replaces the reference work's per-chapter hand-written JS, which the hidden-cost review rejects | significant |
| A3 (#18016) | **Word-mark narration timing**: `[[mark]]` in the script → the time the next spoken word starts, plus sentence captions | core `services/tts_client.py` (+ the worker). Word times come from a forced-alignment pass through the existing Whisper pipeline (`media/audio/pipeline.py` `transcribe_bytes`, via `api/voice.py:449`). The transformers ASR pipeline accepts word-level timestamps; not yet verified against our pinned version | grep `word_boundar\|word_timestamps\|WebVTT\|subtitle\|caption` → only YouTube caption *ingestion* (`content_reach/sources/youtube.py`). Whether Pocket TTS (`autobot-tts-worker/main.py`) can emit word timings itself: **I don't know**, not checked | captions and accurate sync for any spoken output, including chat read-aloud | an extra ASR pass per clip (GPU/NPU time) | adopt in core; the plugin consumes it | moderate |
| A4 (#18017) | **Incremental TTS cache keyed on the spoken text** (`hash(voice\|rate\|clean_text)`), atomic writes, saved after every clip | core `tts_client.py` | the only cache in the TTS client is a negative-probe TTL (`tts_client.py:54`) | resuming after a crash costs nothing; editing a mark does not re-synthesize | the TTL and eviction must follow the cache-TTL convention (an env-backed constant) | adopt | trivial–moderate |
| A5 (#18018) | **Split a PDF by its outline/bookmarks** into sections with page ranges | core `media/document/extraction.py` (beside `extract_pdf` :331); pypdf exposes the outline, so no new dependency | grep `get_toc\|outline\|bookmark` → 0; `SemanticChunker` splits by tokens, not chapters | chapter-aware document ingestion, which also improves KB provenance | PDFs without an outline need a fallback (TOC page heuristics) | adopt | moderate |
| A6 (#18019) | **Agent-readable visual QA**: open a deterministic frame (`?beat=N&t=S`), make contact sheets, run an "opening blank" detector | core `services/playwright_service.py` (`capture_screenshot` :308) plus a check in the plugin | grep `contact.?sheet\|visual_qa\|screenshot_diff` → 0; Storybook pixel-diff exists, but on manual dispatch only (`.github/workflows/visual-regression.yml`) | the generator catches its own layout defects before a human sees them | browser-worker load; the heuristics produce false positives | adopt-with-conditions (needs the deterministic, seekable renderer from A2) | moderate |
| A7 (#18021) | **Exact-answer quiz grading** (integers, fractions, mixed numbers, decimals as exact rationals; lowest terms as an opt-in) | inside the plugin; stdlib `fractions` | grep `Fraction\(\|from fractions\|grade_answer` → 0 | correct grading with no float drift | none worth noting | adopt | trivial |
| A8 (#18015) | **A plugin can serve its own bundle and route** | core `autobot_shared/plugin_sdk/` | `APIRouter\|include_router\|add_api_route` under `plugin_sdk/` and `plugins/` → 0; the frontend plugin mount is a hard-coded list (`autobot-frontend/src/plugins/registry.ts`) | unblocks A1 and any future plugin with UI | a new attack surface; the threat model says there is no load-time sandbox (`THREAT_MODEL.md:71-94`); must be admin-gated and must wait for capability enforcement (#17459) | adopt-with-conditions; blocked by #17459 | moderate–significant |

### Rejected by hidden metrics

- **The unofficial cloud TTS endpoint the reference work uses.** It has no SLA and is outbound
  egress outside our guarded-fetch policy (core rule 8). We already run our own TTS worker.
- **A copy of the engine per book.** Fixes then have to be applied to every copy by hand. One
  engine with a versioned spec (an `engine_version` field in the beat JSON) gives the same
  stability.
- **Lessons hand-coded by one specific frontier model.** That is model lock-in plus a per-chapter
  token cost, and it conflicts with conserving the weekly limit. A2 replaces it.
- **Progress kept only in the browser.** Acceptable for a static export. Inside AutoBot, progress
  and scores belong in a system-of-record store (`store_authority.system_of_record`).

### Path-briefed sequential subagents (a dev-process pattern, not a product feature)

The reference work's coordinator runs the pilot chapter itself, then hands one fresh worker per
chapter a brief made of file paths and returns only a few lines. In the product, the nearest thing
is LLC `claude_code_adapter.py`, whose state is on disk (`_state_path` :89) but whose briefs come
from the KB (`llc/kb/handoff_brief.py`). The plugin's chapter loop should follow the same shape:
the coordinator holds the book map and each worker gets one chapter's spec path. Verdict: adopt
as the plugin's internal orchestration; no core change.

### What We Already Do Better

- **Self-hosted TTS with voice cloning and streaming**: `autobot-tts-worker`, `api/voice.py`
  `/clone-voice` :337 and WS `/stream`. The reference work depends on a third-party endpoint.
- **Document extraction with OCR recovery**: `media/document/pipeline.py`, `ocr.py`
  `ocr_pdf_pages` :270. The reference work needs a text layer.
- **The plugin lifecycle**: manifests, a JSON-schema config, declared env/secrets, trust tiers,
  admin install, and an audit log. The reference work has no packaging beyond a skill folder.
- **Canvas export to HTML/PDF** (`api/canvas.py:346`). Once a lesson's static frames exist, they
  can be exported through it.

### Gaps & Opportunities (impact order)

1. A8 (plugins serving routes and bundles), after #17459. Every UI-bearing plugin needs it, not
   only this one.
2. A3 + A4 (word timings and a TTS cache). This also benefits chat read-aloud and accessibility.
3. A5 (outline split). This also benefits KB ingestion.
4. A1 + A2 + A7 (the plugin itself, its declarative engine, and grading).
5. A6 (visual QA of generated output).

### Specific Code/Files Affected

- `plugins/core-plugins/lesson-generation-plugin/{plugin.json,main.py,engine/,schema/}` (new)
- `autobot_shared/plugin_sdk/{base.py,loader.py,plugin_manager.py}`: an optional route or
  static-bundle contribution in the manifest
- `autobot-frontend/src/plugins/registry.ts`: replace the hard-coded mount list with one
  driven by the manifest
- `autobot-backend/services/tts_client.py` plus a word-alignment helper over `media/audio/pipeline.py`
- `autobot-backend/media/document/extraction.py`: outline sections
- `autobot-backend/services/playwright_service.py`: frame capture plus contact sheets

### Side finding

- `plugins/core-plugins/image-generation-plugin/main.py` `shutdown()` has a bare
  `except Exception: pass` around `unregister`, which silently swallows the error. Filed as
  #18023, together with the identical case in `video-generation-plugin`.
