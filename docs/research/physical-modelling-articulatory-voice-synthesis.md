# Physical-modelling articulatory voice synthesis

Question: is a physically modelled (non-neural, sample-free) voice synthesizer fit for
AutoBot's voice output?

Status: source analysis and AutoBot comparison complete.

## Source Analysis: a browser-based physical-modelling voice synthesizer

### What It Is

The reference work is an open-source, permissively licensed voice synthesizer from an
individual developer. Every sound comes from a simulated airway (lungs, vocal folds, a branched
vocal tract, lips, nose) rather than from recorded samples or a neural model. The engine is a
native library that also compiles to WebAssembly and runs in a browser audio thread. It is
built as a musical instrument first (play, speak, sing, percussion, animal voices), with
text-to-speech as one mode. It is about a week old, effectively single-maintainer, and has no
releases.

### Architecture & Key Patterns

- An engine library with a three-package dependency surface, a thin C-ABI WebAssembly binding,
  and a command-line tool for offline renders and scoring.
- Signal path: text → pronouncing dictionary with a letter-to-sound fallback → phonemes →
  syllables → a gestural score → damped articulator dynamics → 2D vocal-tract geometry → an
  area function → a branched time-domain acoustic tube simulation at 2–4× the output rate.
- Language split: a per-script front end decides phonology and emits one shared syllable
  format; the back end is language-agnostic physics. Two front ends exist.

### Notable Implementation Details

- Real-time contract: steady-state rendering allocates nothing, state is bounded with counted
  overflow, and output is independent of the host's block size.
- Determinism: transcendental math goes through one pinned pure-software library, and a test
  requires identical samples between the native and WebAssembly builds on one platform.
- A frequency-domain model with the same loss terms serves as a test oracle for the
  time-domain solver.
- A measured tuning loop: every change is scored against real recordings, phone by phone after
  forced alignment, plus a machine word error rate from a speech recogniser. Measures not yet
  shown to rank changes the way a listener does are reported as diagnostics and never scored.

### Strengths

- No model weights, no GPU, no network; the only bundled data is a pronouncing dictionary
  under 1 MB compressed.
- Runs entirely on the client; no audio or text leaves the device.
- Reproducible self-measurement that reports unflattering numbers.
- Audio-thread discipline (allocation-free, deterministic, block-size independent).
- A clean seam between language phonology and synthesis.

### Weaknesses / Limitations

- Intelligibility is far below a usable text-to-speech engine: by its own measurement a speech
  recogniser gets about 37 % of the synthesizer's words wrong, against under 3 % on the real
  recordings of the same sentences.
- A robotic timbre is kept as a stated product goal; naturalness is not the target.
- Two languages only. Characters outside a supported script are skipped. Each new language is
  a hand-written phonology front end needing a native speaker's check.
- Multi-voice dialogue is declared out of scope.
- One voice costs roughly a fifth of a CPU core natively and about a third in WebAssembly.
- No text normalisation, markup or streaming text input was found in the documentation.
- No stable API and no published package.

### Visible vs Hidden Metrics

- **Visible:** fast early popularity (a measure of novelty, not speech quality);
  self-reported zero-weights, deterministic, real-time-safe, browser-native, permissive
  licence. Quality scores are self-reported with the scripts to reproduce them; not re-run here.
- **Hidden:** roughly one word in three is not machine-recognisable; every language is its own
  phonology project; per-voice CPU lands on the client; a week-old single-author codebase has
  no stability to pin against; adoption means owning a second, non-neural speech path with its
  own pronunciation, prosody and normalisation gaps.
- **Weighing:** the visible wins are exactly what an on-host voice stack wants, but they are
  undercut wherever the listener must understand arbitrary text. They survive only where
  intelligibility is not the point: a character voice, non-speech vocal sounds, or a visual
  talking head driven by articulator telemetry.

### Preliminary verdict (source evidence only)

Not fit as a speech-output engine: about 37 % machine word error rate, two supported
languages, and a robotic timbre by design are each sufficient on their own. Adoptable patterns
(the measurement loop, the language front-end seam, the real-time contract) are assessed in the
comparison.

## AutoBot Comparison: the reference work → AutoBot

### What We Can Adopt

**1. An automated intelligibility measure for speech output (speech-recogniser round trip, word error rate)**
- Applies to: `autobot-tts-worker/` and the backend path `autobot-backend/services/tts_client.py`; the recogniser side can reuse `transcribe_bytes` in `autobot-backend/media/audio/pipeline.py`.
- Already-exists audit: no hit for `jiwer`, `word_error`, `wer`, `round.?trip`, `intelligib`, `golden.*\.wav`, `mcd`, `MOS`, `forced.?align`, `pesq|stoi|dnsmos|utmos` in speech code; zero `.wav` files in the tree. The only quality check is a manual listening script, `autobot-frontend/scripts/tts-listening-test.mjs:7-14`, where a person judges by ear.
- Visible benefit: a number that moves when a voice, chunking threshold, gain stage or engine changes, and an objective bar for qualifying a Latvian voice (#18443).
- Hidden cost: needs the synthesis model and a recogniser loaded together, which is too heavy for a per-PR check on scarce CI slots; neural output is not sample-deterministic, so the threshold is a band, not an equality; the default recogniser (`openai/whisper-base`, `autobot_shared/ssot_hf_models.py:15`) is weak on Latvian, so Latvian scoring must go through the Latvian-first provider order in `autobot-backend/voice_processing/providers/registry_init.py:68-97`; context-predictable sentences flatter the score, so the sentence set must include semantically unpredictable ones.
- Borrowed discipline: a measure joins the pass/fail score only after it is shown to rank changes the way a listener does; until then it is a reported diagnostic.
- Verdict: **adopt-with-conditions** (a scheduled or on-demand host-side measurement, not a per-PR gate). Effort: moderate.

**2. A per-language text front end ahead of synthesis**
- Applies to: `autobot-frontend/src/utils/ttsSentences.ts` (today's only shaping) and the backend routes `autobot-backend/api/voice.py:187,255`.
- Already-exists audit (partial): `shapeProse` (`ttsSentences.ts:93-107`) strips markdown and replaces URLs and paths; `createSpeechShaper` (`:186-229`) drops code blocks. Missing delta: number, date and abbreviation expansion, and any per-language seam. No hit for `ssml|phonemi[sz]|g2p|num2words|inflect|text_normali`. The worker passes text through raw (`tts-worker.py.j2:326`), and shaping lives only in the browser, so the HTTP routes speak unshaped text.
- Visible benefit: numbers, dates and abbreviations read correctly per language; the same text sounds the same on every route.
- Hidden cost: every language is a rule set someone maintains; moving shaping server-side touches the streaming sentence splitter. Not established: whether the current engine already normalises English numbers internally, which would shrink the English delta to nothing.
- Verdict: **adopt-with-conditions** (start with the one-format seam and Latvian rules when #18443 lands a voice; do not build English rules before measuring that they are needed). Effort: moderate.

**3. The physical-modelling engine as a speech-output backend**
- Applies to: would be a second implementation behind `TTSProtocol` (`autobot-backend/integrations/protocols.py:60-80`).
- Already-exists audit: AutoBot has a neural engine in production and a non-neural formant synthesizer (espeak-ng) already provisioned on the backend host (`autobot-slm-backend/ansible/roles/backend/tasks/main.yml:563-566`).
- Visible benefit: zero weights, deterministic, client-side, permissive licence.
- Hidden cost: about 37 % machine word error rate, two languages (not Latvian), robotic by design, a fifth to a third of a core per voice, a week-old single-author codebase, and a fifth synthesis implementation against the consolidation umbrella #17778.
- Verdict: **rejected** (visible and hidden metrics both). Effort: n/a.

**4. The same engine in the browser as an offline fallback voice**
- Already-exists audit: no output-side AudioWorklet or WASM synthesizer in `autobot-frontend` (the only worklet is input-side VAD, `public/audio-vad-processor.js:25`). The SLM admin tool already uses the browser's built-in `speechSynthesis` (`autobot-slm-frontend/src/views/tools/admin/VoiceTool.vue:192-247`).
- Verdict: **rejected-by-hidden-metrics**: a fallback that is understood two words in three is worse than the browser's built-in voice or no audio, and it adds a WASM binary and a dictionary download to the client.

**5. Articulator telemetry driving a talking head**
- Already-exists audit: no hit for `viseme`, `lip.?sync`, `talking.?head`; `avatar` hits are profile pictures only.
- Verdict: **rejected for now**: no avatar feature exists or is planned for it to serve, and the telemetry only describes the rejected engine's own audio, not AutoBot's neural voice.

### What We Already Do Better

- **Intelligible, natural speech**: a neural engine (Kyutai Pocket TTS, `tts-worker.py.j2:210-214`) with 8 built-in voices and voice cloning (`:247-261`, `:555`).
- **Streaming with barge-in**: ~250 ms framed chunks (`tts-worker.py.j2:59`, `:541-544`), a cancel flag (`:330-368`), a per-sentence WebSocket queue and drain (`autobot-backend/api/voice_stream.py:140-163`, `:226-241`).
- **Playback engineering**: gapless Web Audio scheduling and an adaptive pre-roll derived from the measured real-time factor (`autobot-frontend/src/composables/useVoiceOutput.ts:56-105`, `:629-695`).
- **Latency contract under test**: first audio must leave after exactly one worker chunk, counted not timed (`autobot-backend/api/voice_latency_test.py:202-228`); real-time-factor metrics with a floor (`autobot_shared/monitoring/metrics/tts.py:22`, `:65-84`).
- **Speech-first text shaping** for chat output (markdown, code, URLs), which the reference work has no need for.
- **Sample determinism and allocation-free rendering** are properties of a hand-written DSP engine; they do not transfer to a neural worker, and AutoBot's chunk-count tests are the right equivalent for its architecture.

### Gaps & Opportunities

Ordered by impact. Items 2 to 6 are AutoBot findings this comparison surfaced; they do not depend on the reference work.

1. **No automated measure of whether speech output is understood** (adopt item 1). New; no existing issue found.
2. **Speech language is not the conversation's language.** The worker takes no language parameter (`tts-worker.py.j2:490-493`), the backend's `language` field is silently ignored, and the frontend sends the UI preference (`useVoiceOutput.ts:883-891`). Already tracked: #20113 (open), #18443 (open).
3. **The TTS seam has no consumer.** `TTSProtocol` is registered once (`capability_registry.py:52,149-156`) and nothing resolves it; routes call the client directly. Speech-to-text has a per-language provider registry and speech output does not. Falls under umbrella #17778 (open).
4. **Text shaping is browser-only** (adopt item 2), so the same text is spoken differently by route.
5. **Worker tests exercise copies of the template's helpers**, not the template (`autobot-tts-worker/tests/test_streaming.py:8-9,28`), so the tests can pass while the deployed code differs.
6. **Stale documentation**: `autobot-tts-worker/README.md:11` names a previous engine, and the README and the inventory disagree on which host runs the worker.

### Specific Code/Files Affected

| File | Change |
|---|---|
| `autobot-tts-worker/` (new measurement script + sentence set) | Render a fixed sentence set through the worker, transcribe, report word error rate per voice and language |
| `autobot-backend/media/audio/pipeline.py` | Reused as the recogniser (`transcribe_bytes`); no change expected |
| `autobot-frontend/src/utils/ttsSentences.ts`, `autobot-backend/api/voice.py` | One shaping step shared by every route, with a per-language hook |
| `autobot-slm-backend/ansible/roles/tts-worker/templates/tts-worker.py.j2` | Accept and honour `language` (under #18443 / #20113) |
| `autobot-backend/integrations/capability_registry.py`, `api/voice.py`, `api/voice_stream.py` | Resolve speech output through the registered seam (under #17778) |
| `autobot-tts-worker/tests/test_streaming.py` | Test the rendered template, not a copy |
| `autobot-tts-worker/README.md` | Correct the engine name and host |

### Verdict

**Not fit.** AutoBot's current neural worker is ahead of the reference work on every axis that matters for a voice assistant (intelligibility, naturalness, languages, streaming). What is worth taking is its method, not its engine: measure speech output against a recogniser, and keep unvalidated measures out of the pass/fail score.

Not verified in this comparison: nothing was run, so AutoBot's own word error rate is unknown; which host runs the worker; whether the legacy server-speaker path is installed in production.

## Linked issues

- #21362 feat(voice): measure speech-output intelligibility with a recogniser round trip — nothing checks that synthesised speech is understood
- #21363 test(tts-worker): the worker's tests exercise copies of the template's helpers, not the template
- #21364 feat(voice): one text front end for speech on every route — shaping is browser-only and nothing expands numbers, dates or abbreviations
- #21365 perf(voice): time-to-first-audio is unmeasured end to end, and seven waits on the path have no owner
- #21372 Umbrella(voice): speech-output quality and speed — measure intelligibility and first-audio time, test the real worker, one text front end
- #18443 feat(voice): Latvian speech synthesis — the TTS worker engine does not support lv
- #20113 feat(voice): keep the transcript, reply and speech output of a conversation in one language
- #17778 Umbrella(speech): five transcription implementations and four synthesis implementations — two forks are reachable in production
