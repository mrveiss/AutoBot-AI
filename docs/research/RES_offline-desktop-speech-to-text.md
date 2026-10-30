---
tags:
  - research
---

# Research: offline desktop speech-to-text application

Status: Phase 1 and Phase 2 complete; scoped to AutoBot voice functionality, read at `origin/main` 8387179aa2. Issues filed; see Linked issues.

## Source Analysis: open-source offline desktop dictation application

### What It Is

A cross-platform desktop application: press a shortcut, speak, and the transcript is pasted into
whichever application has focus. All speech processing runs on the local machine. It is
permissively licensed, has a compiled native backend with a web-technology UI, and is pre-1.0 and
actively maintained.

### Architecture & Key Patterns

- **Single desktop process plus one supervised worker.** Managers own audio, models, transcription
  and history; the UI talks to them through generated, typed command bindings.
- **Process isolation for native inference.** All native speech-engine code runs in a child process,
  which is the same executable re-launched with a hidden flag. One supervisor owns it behind a framed
  request/response protocol.
- **Pipeline:** microphone capture, voice activity detection, decode, optional LLM post-processing,
  paste into the focused application, history stored in SQLite.
- **One decode-policy module.** Model traits and settings choose between streaming, chunked and
  single-run decoding in one place.
- **Model catalog.** A bundled JSON catalog drives model download and selection.

### Notable Implementation Details

- **Crash containment with fallback.** A GPU driver fault, native assert or hang kills only the
  worker. The supervisor recovers and retries in a CPU-only worker that registers only CPU backends,
  so a driver that crashes during initialisation cannot take the fallback down too. The worker lives
  exactly as long as its loaded model, so unloading returns all CPU and GPU memory to the OS.
- **Pause-aligned chunking.** Audio over 40 s is cut at pauses into chunks of about 30 s, with a 5 s
  minimum, because most models lose accuracy past 30-40 s in one run. Durations are stored in samples
  rather than frames, so any detector's frame size works. A live cut becomes final only after 5 s of
  lookahead audio is scored, so live cuts match the plan for the whole clip.
- **Smoothed voice activity detection.** A wrapper around a boolean detector adds pre-roll, onset and
  hangover frames, which keeps word starts and stops brief noise from triggering speech.
- **Receipt-sequenced clipboard restore (debug-gated).** A fixed restore delay can lose the race with
  the target application, which then pastes the old clipboard. This path publishes a lazy clipboard
  promise and restores only after the OS reports a read that happened after the paste keystroke, only
  while the application still owns the clipboard, and only after a quiet period. Failure leaves the
  transcript on the clipboard longer and never pastes stale content. Windows and macOS only.
- **Input-loss fallback on macOS.** It detects when OS secure input silently stops keyed shortcuts and
  temporarily registers them through a path that still works. Its diagnostic counts event kinds and
  never records key identity.

### Strengths

- A narrow scope: one tool that does one job.
- Failure design: native crashes are contained, and failures degrade to a safe state.
- Local by default for speech processing.
- Scriptable control of a running instance through CLI flags.

### Weaknesses / Limitations

- **Linux input is fragile.** Text injection depends on external tools that vary by display server,
  and Wayland support is described as limited. The project's own notes say one tool fails on a current
  Ubuntu release.
- **Reliable paste is partial.** It is debug-gated and has no Linux implementation.
- **Very large modules.** The model, transcription, settings and supervisor modules are each very
  large single files.
- **Desktop only.** No server or multi-user mode appears in the material read.
- **Limited extension evidence.** "Extensible" is claimed. The evidence seen is CLI flags and one
  third-party launcher integration; no plugin API was found in the material read, though it was not
  searched for exhaustively.

### Visible vs Hidden Metrics

- **Visible:** tens of thousands of stars (independently visible, measuring popularity rather than
  quality); "works completely offline" and "excellent performance" (both
  self-reported, not verified here).
- **Hidden:** native GPU and driver exposure across three operating systems, which is what forced the
  supervisor; a per-platform input and permissions matrix; model catalog upkeep; a bundled detector
  model; a large open issue backlog.
- **Weighing:** the hidden costs are high for anyone adopting the product, because most of the code
  handles desktop integration. They are low for anyone borrowing individual techniques. The isolation,
  chunking and detector-smoothing patterns are portable, while the input-injection layer only pays off
  for an application that types into other applications.

### Limits of this analysis

Read through the remote API without cloning: the README (first 170 lines), the dependency manifest,
the agent guidance file (first 90 lines) and the opening sections of the supervisor, chunking,
detector-smoothing, decode-policy, paste and secure-input modules. Behaviour is taken from their
comments and types. The source was not built or run, so accuracy, latency and crash recovery are
unmeasured. Unread: language detection, text post-processing, the LLM client, history and the UI.

## AutoBot Comparison: scope and verdict

Scope: voice only. The reference work's dictation layer does not fit AutoBot, which has no desktop
client (no desktop-shell files in the tree). Its engine-reliability ideas do fit, because AutoBot runs
speech inference inside the backend process. Nothing here was run; findings come from reading code,
and no crash, latency or accuracy figure was measured on either side.

### What We Can Adopt

| # | Candidate | Already-exists audit | Visible benefit | Hidden cost | Verdict | Effort |
|---|---|---|---|---|---|---|
| 1 | Supervised speech worker process | `media/audio/pipeline.py:175-184` loads in-process; one lock serialises all inference (`:47`, `:204`); the multimodal processor has an `asyncio.wait_for` timeout (`multimodal_processor/processors/voice.py`), but a timeout abandons the worker thread rather than stopping it, so a hung inference would keep the lock; NPU and TTS workers set a precedent | A native fault or hang stops taking chat with it | A new service in every install method and the fleet; audio passed over IPC; recovery code to own | Adopt with conditions: after #17778 consolidates the engines, reusing the existing worker pattern, and once an incident or fault test shows the need | Significant |
| 2 | Retry on CPU when GPU load fails | on load failure, `pipeline.py:190-193` retries the same device (after 60 s by default); `OutOfMemoryError` has 0 hits across the speech paths | Speech survives a bad driver or full GPU | Slower transcription that needs to be visible to users | Adopt | Trivial to moderate |
| 3 | Release the model when idle | The only `_whisper_pipeline = None` is the load-failure path (`pipeline.py:192`); no unload found | Returns memory on shared hosts | Cold start on the next voice turn; only a worker guarantees full release | Adopt with conditions: measure resident memory first | Moderate |
| 4 | Server-side voice detection before decoding | Filtering runs after inference (`whisper_provider.py`, `hallucination_filter.py`); `speech_recognition.py:375-379` is the placeholder tracked in #16807 | Avoids decoding silence and removes a source of phantom text | Another pinned model to provision; risk of clipping quiet speech | Adopt with conditions: deliver inside #16807, and measure on silence-heavy recordings | Moderate |
| 5 | Pre-roll on the energy-based full-duplex path | `public/audio-vad-processor.js:15-23` has an RMS threshold and onset frames, with no pre-roll in that file; callers not checked | Keeps first syllables | Small buffer; barge-in interaction | Adopt with conditions: first confirm clipping occurs | Trivial |
| 6 | User vocabulary for names and terms | 0 hits for prompt, hotword or vocabulary terms in `voice_processing`, `media`, `transcriber`, `multimodal_processor`. The reference work's mechanism was not read | Better recognition of project terms | Wrong substitutions; per-user storage | Adopt with conditions: read the mechanism and choose one that does not rewrite correct text | Moderate |
| 7 | Keyboard shortcut for the mic, inside the web app | `useGlobalShortcuts.ts` has 0 voice, mic or talk hits; `voice_interface.py:242` has a `push_to_talk_key` setting on the backend | Faster voice entry | Key conflicts; i18n and accessibility upkeep | Adopt | Trivial |

**Rejected by hidden metrics**

- **Paste into the focused application, receipt-based clipboard restore, OS-wide shortcuts, secure-input
  fallback.** These need a native desktop client on three operating systems, which is most of the
  reference work's cost. AutoBot has no such client and its positioning does not call for one.
- **Pause-aligned chunking for accuracy.** The reference work's own policy exempts Whisper, because it
  keeps accuracy on long audio, and AutoBot's local engine already uses that long-form mode
  (`pipeline.py:209-233`).
- **Replacing the engine with a native runtime.** The speed benefit is unmeasured, and it would have to
  re-earn the pin and integrity path. A benchmark would be needed to reopen this.
- **Bundled model catalog.** `autobot_shared/pinned_model_registry.py` is the better home. The real gap
  is provisioning (#19869).

### What We Already Do Better

- **Model integrity.** Pinned revisions, with a tampered model refusing to serve rather than falling
  through to a cloud provider (`pipeline.py:186-189`).
- **Phantom-text defence.** A layered filter with a rule against silent discards
  (`voice_processing/hallucination_filter.py`).
- **Conversation.** Hands-free and full-duplex modes, one silence setting driving every endpointer, and
  an echo cooldown after speech output (`useVoiceConversation.ts:62-127`).
- **Breadth.** Speech output, a provider chain with Latvian engines, diarization, transcript projects
  and knowledge-base ingest. The reference work does one job, so this is a difference in scope.

Several of these carry open defects, notably #17778 and #18233.

### Gaps & Opportunities

In priority order:

1. **Local speech does not work out of the box.** No install step fetches the model (#19869) and the
   knowledge connector's engine is declared in no requirements file (#19863). Filed.
2. **Local-first is not the default.**
   - Cloud providers outrank local engines (#18233, filed).
   - The conversation path tries the browser's speech engine first and uses local Whisper only when that
     fails (`useVoiceConversation.ts:407-414`, `:490`). Some browsers send this audio to their vendor;
     that is general knowledge, not tested here.
     The fallback was deliberate (#1329, closed), but #18229 records an owner ruling that Google speech
     recognition is off by default and chosen in the setup wizard. #18229 and #18233 cover backend paths
     only, so this browser path has no issue yet.
3. **One long job can delay a live voice turn.** Every caller shares the inference lock
   (`pipeline.py:204`), so a long upload holds up a conversation turn. This is inferred from the code,
   and candidate 1 is the natural place to fix it.
4. **Failure handling.** Candidates 1 to 3.
5. **Input quality.** Candidates 4 to 7.

### Specific Code/Files Affected

| File | Change |
|---|---|
| `autobot-backend/media/audio/pipeline.py` | CPU retry; idle release; later, the call into a worker |
| `autobot-backend/voice_processing/speech_recognition.py` | Real detection in place of the placeholder (#16807) |
| `autobot-frontend/src/composables/useVoiceConversation.ts` | Local-first engine order |
| `autobot-frontend/public/audio-vad-processor.js` | Pre-roll buffer, if clipping is confirmed |
| `autobot-frontend/src/composables/useGlobalShortcuts.ts` | Mic shortcut |
| `autobot-backend/voice_processing/providers/whisper_provider.py` | Vocabulary hint; detection before decode |
| New worker service, plus install and fleet roles | Candidate 1 only |

## Linked issues

- #20093 Umbrella(speech): dependable, private-by-default local speech recognition
- #20094 privacy(voice): voice input uses the browser's speech engine before local Whisper, with no user choice
- #20095 fix(speech): retry Whisper on CPU when GPU load or inference fails
- #20096 feat(speech): run speech inference in a supervised worker so faults and long jobs cannot stall the backend
- #20097 perf(speech): release the Whisper model after an idle period
- #20098 fix(voice): check for clipped first syllables on the full-duplex path and add pre-roll if needed
- #20099 feat(speech): user vocabulary for names and project terms
- #20100 feat(voice): keyboard shortcut for voice input in the web app
- #20110 feat(speech): local Latvian speech recognition that works without the LATE binary
- #20111 privacy(speech): audio reaches a system outside AutoBot only by explicit user choice
- #16807 Server-side VAD in speech_recognition.py is a placeholder, not real detection
