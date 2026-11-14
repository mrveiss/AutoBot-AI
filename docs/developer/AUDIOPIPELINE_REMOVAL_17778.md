# AudioPipeline removal record (#17778)

`media.audio.pipeline.AudioPipeline` was removed in f3d8a61ea1 (zero callers). The owner's rule,
given in the de-fork master session on 2026-10-09 when asked about the compat question:

> "if the code is usless we remove it, but if ithas usefull functionality we integrate it by refactoring"

The old class (`git show f3d8a61ea1^:autobot-backend/media/audio/pipeline.py`) was compared method by
method with the canonical path (`media/audio/pipeline.py` `transcribe_*`, `VoiceProcessor`,
`api/voice.py`). No behaviour was unique and still useful, so the deletion stands.

| Old method | Canonical equivalent | Unique and useful? |
|---|---|---|
| `_process_impl` and the media `ProcessingResult` wrapper | `VoiceProcessor.process` (timeout, confidence threshold, #13207) | No. The wrapper had zero callers. |
| `_process_audio` | `VoiceProcessor._process_audio` | No. Same flow; the canonical one also decodes containers and drops silence hallucinations. |
| `_run_whisper` | `transcribe_bytes` / `transcribe_path` / `transcribe_array` | No. These are the surviving inference code. |
| `_transcription_result` (word_count, chunks, language, confidence 0.9/0.5) | `VoiceProcessor._build_voice_result` (0.9, or 0.0 when empty) | No. `chunks` was always empty (`return_timestamps=False`), `language` always "unknown", `word_count` is `len(text.split())`; the 0.5 for empty text contradicts the 0.0 policy of #13207. |
| `_decode_input` (bytes, base64 string, or file path) | `decode_audio_bytes_async`; `_prepare_audio_data` loads a path | No. Nothing passed base64; reading an arbitrary path from the input is a liability, and a path can itself be valid base64. |
| `_suffix_from_mime` | `suffix_for_mime` | Already kept. |
| `_unavailable_result`, `_error_result` (success with a `processing_status` field) | `_validate_audio_models_available`, then `_failure_result(success=False, error_message)` | No. The canonical path states the failure properly. |
| `_calculate_confidence` | `VoiceProcessor.calculate_confidence` | No. |

`MediaPipelineManager` no longer registers an audio pipeline; the manager itself has zero callers and
was left alone (a separate decision).
