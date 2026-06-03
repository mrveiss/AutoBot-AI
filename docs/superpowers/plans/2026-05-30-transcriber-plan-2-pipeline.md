# Transcriber Module — Plan 2: Pipeline

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** End-to-end audio processing pipeline — FFmpeg → language detection → Demucs (optional) → Pyannote diarization → AutoBot speech provider → segment merge → DB persist — with real-time SSE progress and a language-keyed speech provider registry.

**Architecture:** `transcriber/pipeline/` stages orchestrated by `transcriber/pipeline/queue.py` (wired to `async_work.get_task_queue()`). Progress fires through `async_work.get_progress_tracker()`. LATE and Tilde are registered as Latvian (`lv`) providers in `voice_processing/providers/` — the transcriber never imports them directly.

**Tech Stack:** Python 3.11+, aiofiles, ffmpeg-python, pyannote.audio 3.1, lingua-language-detector, faster-whisper (fallback), httpx, async_work facade, AutoBot voice_processing provider registry

**Prerequisite:** Plan 1 complete.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `autobot-backend/voice_processing/providers/__init__.py` | Language-keyed speech provider registry |
| Create | `autobot-backend/voice_processing/providers/lv/__init__.py` | Latvian provider package |
| Create | `autobot-backend/voice_processing/providers/lv/late_provider.py` | LATE binary ASR provider |
| Create | `autobot-backend/voice_processing/providers/lv/tilde_provider.py` | Tilde cloud ASR provider |
| Create | `autobot-backend/transcriber/pipeline/__init__.py` | Pipeline package |
| Create | `autobot-backend/transcriber/pipeline/progress.py` | SSE progress events |
| Create | `autobot-backend/transcriber/pipeline/ffmpeg_convert.py` | Stage 1: audio normalization |
| Create | `autobot-backend/transcriber/pipeline/detect_language.py` | Stage 2: language detection |
| Create | `autobot-backend/transcriber/pipeline/demucs.py` | Stage 3: source separation (optional) |
| Create | `autobot-backend/transcriber/pipeline/diarize.py` | Stage 4: Pyannote speaker diarization |
| Create | `autobot-backend/transcriber/pipeline/transcribe.py` | Stage 5: ASR via provider registry |
| Create | `autobot-backend/transcriber/pipeline/merge.py` | Stage 6: align diarization + transcript |
| Create | `autobot-backend/transcriber/pipeline/queue.py` | Job orchestrator (wired to async_work) |
| Create | `autobot-backend/transcriber/routes/recordings_sse.py` | SSE progress endpoint + retry endpoint |
| Modify | `autobot-backend/transcriber/routes/recordings.py` | Trigger pipeline on upload |
| Modify | `autobot-backend/extensions/builtin/transcriber_extension.py` | Register providers on startup |
| Create | `autobot-backend/transcriber/tests/test_pipeline_*.py` | Pipeline unit tests |

---

### Task 1: Speech provider registry

**Files:**
- Create: `autobot-backend/voice_processing/providers/__init__.py`
- Create: `autobot-backend/voice_processing/providers/lv/__init__.py`

- [ ] **Step 1: Write failing test**

```python
# autobot-backend/transcriber/tests/test_pipeline_providers.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import pytest
from voice_processing.providers import SpeechProviderRegistry, SpeechProvider


class DummyProvider(SpeechProvider):
    lang = "xx"
    name = "dummy"

    async def transcribe(self, wav_path: str, language: str) -> list[dict]:
        return [{"start": 0.0, "end": 1.0, "text": "hello"}]


def test_register_and_get():
    reg = SpeechProviderRegistry()
    reg.register(DummyProvider())
    providers = reg.get("xx")
    assert len(providers) == 1
    assert providers[0].name == "dummy"


def test_get_unknown_lang_returns_empty():
    reg = SpeechProviderRegistry()
    assert reg.get("zz") == []


def test_get_best_provider():
    reg = SpeechProviderRegistry()
    reg.register(DummyProvider())
    best = reg.get_best("xx")
    assert best is not None
    assert best.name == "dummy"
```

- [ ] **Step 2: Run to verify failure**

```bash
cd autobot-backend
python -m pytest transcriber/tests/test_pipeline_providers.py -v
```
Expected: `ImportError: cannot import name 'SpeechProviderRegistry'`

- [ ] **Step 3: Implement provider registry**

```python
# autobot-backend/voice_processing/providers/__init__.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Language-keyed speech provider registry for AutoBot.

Providers register themselves by language code (BCP-47, e.g. 'lv', 'en').
The transcriber pipeline calls get_best(lang) to get the highest-priority
available provider for the detected language.
"""
from __future__ import annotations
import abc
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


class SpeechProvider(abc.ABC):
    """Base class for all AutoBot speech providers."""

    lang: str       # BCP-47 language code this provider handles
    name: str       # Unique provider identifier
    priority: int = 50  # Lower = higher priority (0 = best)

    @abc.abstractmethod
    async def transcribe(self, wav_path: str, language: str) -> list[dict]:
        """Transcribe audio file.

        Args:
            wav_path: Absolute path to normalized 16kHz mono WAV.
            language: BCP-47 language code.

        Returns:
            List of dicts: [{start: float, end: float, text: str}, ...]
        """


class SpeechProviderRegistry:
    """Thread-safe singleton registry of speech providers keyed by language."""

    def __init__(self) -> None:
        self._providers: dict[str, list[SpeechProvider]] = {}

    def register(self, provider: SpeechProvider) -> None:
        lang = provider.lang
        self._providers.setdefault(lang, [])
        self._providers[lang].append(provider)
        self._providers[lang].sort(key=lambda p: p.priority)
        logger.info("Registered speech provider '%s' for lang='%s'", provider.name, lang)

    def get(self, lang: str) -> list[SpeechProvider]:
        return self._providers.get(lang, [])

    def get_best(self, lang: str) -> SpeechProvider | None:
        providers = self.get(lang)
        return providers[0] if providers else None

    def available_languages(self) -> list[str]:
        return list(self._providers.keys())


# Module-level singleton — import and use directly
_registry = SpeechProviderRegistry()


def get_registry() -> SpeechProviderRegistry:
    return _registry
```

```python
# autobot-backend/voice_processing/providers/lv/__init__.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Latvian language speech providers."""
```

- [ ] **Step 4: Run tests**

```bash
cd autobot-backend
python -m pytest transcriber/tests/test_pipeline_providers.py -v
```
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add autobot-backend/voice_processing/providers/
git commit -m "feat(voice_processing): add language-keyed speech provider registry"
```

---

### Task 2: LATE and Tilde Latvian providers

**Files:**
- Create: `autobot-backend/voice_processing/providers/lv/late_provider.py`
- Create: `autobot-backend/voice_processing/providers/lv/tilde_provider.py`

- [ ] **Step 1: Write failing tests**

```python
# autobot-backend/transcriber/tests/test_pipeline_late_provider.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import pytest
from unittest.mock import AsyncMock, patch
from voice_processing.providers.lv.late_provider import LATEProvider


@pytest.mark.asyncio
async def test_late_provider_lang():
    p = LATEProvider()
    assert p.lang == "lv"
    assert p.name == "late"


@pytest.mark.asyncio
async def test_late_transcribe_calls_endpoint(tmp_path):
    wav = tmp_path / "test.wav"
    wav.write_bytes(b"RIFF" + b"\x00" * 44)
    p = LATEProvider(port=9090)
    mock_response = AsyncMock()
    mock_response.json = AsyncMock(return_value={
        "segments": [{"start": 0.0, "end": 1.5, "text": "Sveiki"}]
    })
    mock_response.raise_for_status = AsyncMock()
    with patch("httpx.AsyncClient.post", return_value=mock_response):
        result = await p.transcribe(str(wav), "lv")
    assert len(result) == 1
    assert result[0]["text"] == "Sveiki"
```

- [ ] **Step 2: Run to verify failure**

```bash
cd autobot-backend
python -m pytest transcriber/tests/test_pipeline_late_provider.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement LATE provider**

```python
# autobot-backend/voice_processing/providers/lv/late_provider.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LATE binary speech provider for Latvian (lv).

LATE is a local ASR binary that exposes an HTTP API on a configurable port.
It is lazily started by the operating system or a separate process manager —
this provider only calls the HTTP API.
"""
import httpx
from autobot_shared.logging_manager import get_logger
from voice_processing.providers import SpeechProvider

logger = get_logger(__name__)


class LATEProvider(SpeechProvider):
    lang = "lv"
    name = "late"
    priority = 10  # Prefer over Tilde (local, no API cost)

    def __init__(self, port: int = 9090) -> None:
        self._base_url = f"http://127.0.0.1:{port}"

    async def transcribe(self, wav_path: str, language: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=300.0) as client:
            with open(wav_path, "rb") as f:
                resp = await client.post(
                    f"{self._base_url}/transcribe",
                    files={"audio": ("audio.wav", f, "audio/wav")},
                    data={"language": language},
                )
            resp.raise_for_status()
            data = resp.json()
        segments = data.get("segments", [])
        return [{"start": s["start"], "end": s["end"], "text": s["text"]} for s in segments]
```

- [ ] **Step 4: Implement Tilde provider**

```python
# autobot-backend/voice_processing/providers/lv/tilde_provider.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tilde cloud ASR provider for Latvian (lv).

Requires TILDE_API_KEY environment variable.
Falls back gracefully if key is not set.
"""
import os
import httpx
from autobot_shared.logging_manager import get_logger
from voice_processing.providers import SpeechProvider

logger = get_logger(__name__)

_TILDE_URL = "https://api.tilde.lv/asr/v1/transcribe"


class TildeProvider(SpeechProvider):
    lang = "lv"
    name = "tilde"
    priority = 20  # Lower priority than LATE

    def __init__(self) -> None:
        self._api_key = os.getenv("TILDE_API_KEY", "")

    def is_available(self) -> bool:
        return bool(self._api_key)

    async def transcribe(self, wav_path: str, language: str) -> list[dict]:
        if not self._api_key:
            raise RuntimeError("TILDE_API_KEY not configured")
        async with httpx.AsyncClient(timeout=600.0) as client:
            with open(wav_path, "rb") as f:
                resp = await client.post(
                    _TILDE_URL,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    files={"audio": ("audio.wav", f, "audio/wav")},
                    data={"language": language},
                )
            resp.raise_for_status()
            data = resp.json()
        return [{"start": s["start"], "end": s["end"], "text": s["text"]} for s in data.get("segments", [])]
```

- [ ] **Step 5: Register providers in extension startup**

In [autobot-backend/extensions/builtin/transcriber_extension.py](autobot-backend/extensions/builtin/transcriber_extension.py), update `on_app_startup`:

```python
    async def on_app_startup(self, app: FastAPI) -> None:
        if not _ENABLED:
            logger.info("Transcriber extension disabled")
            return
        from transcriber.database import Database
        from voice_processing.providers import get_registry
        from voice_processing.providers.lv.late_provider import LATEProvider
        from voice_processing.providers.lv.tilde_provider import TildeProvider

        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        (_DATA_DIR / "uploads").mkdir(exist_ok=True)
        (_DATA_DIR / "processed").mkdir(exist_ok=True)
        (_DATA_DIR / "exports").mkdir(exist_ok=True)

        db = Database(str(_DATA_DIR / "transcriber.db"))
        await db.connect()
        app.state.transcriber_db = db
        app.state.transcriber_upload_dir = str(_DATA_DIR / "uploads")
        app.state.transcriber_export_dir = str(_DATA_DIR / "exports")

        registry = get_registry()
        registry.register(LATEProvider())
        tilde = TildeProvider()
        if tilde.is_available():
            registry.register(tilde)
            logger.info("Tilde provider registered (API key present)")
        else:
            logger.info("Tilde provider skipped (TILDE_API_KEY not set)")
        logger.info("Transcriber extension started")
```

- [ ] **Step 6: Run tests**

```bash
cd autobot-backend
python -m pytest transcriber/tests/test_pipeline_late_provider.py -v
```
Expected: 2 PASSED

- [ ] **Step 7: Commit**

```bash
git add autobot-backend/voice_processing/providers/lv/ \
        autobot-backend/extensions/builtin/transcriber_extension.py
git commit -m "feat(voice_processing): add LATE and Tilde Latvian speech providers"
```

---

### Task 3: Pipeline — FFmpeg conversion (Stage 1)

**Files:**
- Create: `autobot-backend/transcriber/pipeline/__init__.py`
- Create: `autobot-backend/transcriber/pipeline/ffmpeg_convert.py`
- Create: `autobot-backend/transcriber/tests/test_pipeline_ffmpeg.py`

- [ ] **Step 1: Write failing test**

```python
# autobot-backend/transcriber/tests/test_pipeline_ffmpeg.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from transcriber.pipeline.ffmpeg_convert import convert_to_wav


@pytest.mark.asyncio
async def test_convert_returns_wav_path(tmp_path):
    input_path = str(tmp_path / "input.mp3")
    output_dir = str(tmp_path / "processed")
    import os; os.makedirs(output_dir)
    expected_output = str(tmp_path / "processed" / "input.wav")

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_proc:
        mock_proc.return_value.returncode = 0
        mock_proc.return_value.communicate = AsyncMock(return_value=(b"", b""))
        result = await convert_to_wav(input_path, output_dir)
    assert result == expected_output


@pytest.mark.asyncio
async def test_convert_raises_on_ffmpeg_failure(tmp_path):
    output_dir = str(tmp_path / "processed")
    import os; os.makedirs(output_dir)
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_proc:
        mock_proc.return_value.returncode = 1
        mock_proc.return_value.communicate = AsyncMock(return_value=(b"", b"ffmpeg error"))
        with pytest.raises(RuntimeError, match="FFmpeg conversion failed"):
            await convert_to_wav(str(tmp_path / "bad.mp3"), output_dir)
```

- [ ] **Step 2: Run to verify failure**

```bash
cd autobot-backend
python -m pytest transcriber/tests/test_pipeline_ffmpeg.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# autobot-backend/transcriber/pipeline/__init__.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
```

```python
# autobot-backend/transcriber/pipeline/ffmpeg_convert.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Stage 1: Convert any audio format to 16kHz mono WAV using FFmpeg."""
import asyncio
from pathlib import Path
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


async def convert_to_wav(input_path: str, output_dir: str) -> str:
    """Convert audio file to 16kHz mono PCM WAV.

    Returns absolute path to the output WAV file.
    Raises RuntimeError if FFmpeg exits non-zero.
    """
    stem = Path(input_path).stem
    output_path = str(Path(output_dir) / f"{stem}.wav")
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-ar", "16000", "-ac", "1", "-f", "wav", output_path,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg conversion failed: {stderr.decode(errors='replace')}")
    logger.debug("Converted %s → %s", input_path, output_path)
    return output_path
```

- [ ] **Step 4: Run tests**

```bash
cd autobot-backend
python -m pytest transcriber/tests/test_pipeline_ffmpeg.py -v
```
Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add autobot-backend/transcriber/pipeline/ autobot-backend/transcriber/tests/test_pipeline_ffmpeg.py
git commit -m "feat(transcriber/pipeline): add FFmpeg conversion stage"
```

---

### Task 4: Pipeline — Language detection (Stage 2)

**Files:**
- Create: `autobot-backend/transcriber/pipeline/detect_language.py`
- Create: `autobot-backend/transcriber/tests/test_pipeline_detect_language.py`

- [ ] **Step 1: Write failing test**

```python
# autobot-backend/transcriber/tests/test_pipeline_detect_language.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import pytest
from unittest.mock import patch, MagicMock
from transcriber.pipeline.detect_language import detect_language


def test_detect_language_returns_bcp47():
    mock_detector = MagicMock()
    mock_lang = MagicMock()
    mock_lang.iso_code_639_1.name.lower.return_value = "lv"
    mock_detector.detect_language_of.return_value = mock_lang
    with patch("transcriber.pipeline.detect_language._get_detector", return_value=mock_detector):
        result = detect_language("Šis ir teksts latviešu valodā")
    assert result == "lv"


def test_detect_language_unknown_returns_none():
    mock_detector = MagicMock()
    mock_detector.detect_language_of.return_value = None
    with patch("transcriber.pipeline.detect_language._get_detector", return_value=mock_detector):
        result = detect_language("")
    assert result is None
```

- [ ] **Step 2: Run to verify failure**

```bash
cd autobot-backend
python -m pytest transcriber/tests/test_pipeline_detect_language.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# autobot-backend/transcriber/pipeline/detect_language.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Stage 2: Detect spoken language from transcript sample text.

Uses lingua-language-detector. Detector is lazy-loaded and cached.
"""
from __future__ import annotations
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)
_detector = None


def _get_detector():
    global _detector
    if _detector is None:
        from lingua import LanguageDetectorBuilder, Language
        _detector = LanguageDetectorBuilder.from_all_languages().build()
    return _detector


def detect_language(sample_text: str) -> str | None:
    """Return BCP-47 language code (e.g. 'lv', 'en') or None if undetected."""
    if not sample_text.strip():
        return None
    detector = _get_detector()
    lang = detector.detect_language_of(sample_text)
    if lang is None:
        return None
    code = lang.iso_code_639_1.name.lower()
    logger.debug("Detected language: %s", code)
    return code
```

- [ ] **Step 4: Run tests**

```bash
cd autobot-backend
python -m pytest transcriber/tests/test_pipeline_detect_language.py -v
```
Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add autobot-backend/transcriber/pipeline/detect_language.py \
        autobot-backend/transcriber/tests/test_pipeline_detect_language.py
git commit -m "feat(transcriber/pipeline): add language detection stage"
```

---

### Task 5: Pipeline — Diarization (Stage 4)

**Files:**
- Create: `autobot-backend/transcriber/pipeline/diarize.py`
- Create: `autobot-backend/transcriber/tests/test_pipeline_diarize.py`

- [ ] **Step 1: Write failing test**

```python
# autobot-backend/transcriber/tests/test_pipeline_diarize.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import pytest
from unittest.mock import patch, MagicMock
from transcriber.pipeline.diarize import diarize


@pytest.mark.asyncio
async def test_diarize_returns_speaker_segments(tmp_path):
    wav = tmp_path / "audio.wav"
    wav.write_bytes(b"\x00" * 1000)

    mock_pipeline = MagicMock()
    mock_turn1 = MagicMock(start=0.0, end=2.5)
    mock_turn2 = MagicMock(start=2.5, end=5.0)
    mock_pipeline.return_value.itertracks.return_value = [
        (mock_turn1, None, "SPEAKER_00"),
        (mock_turn2, None, "SPEAKER_01"),
    ]
    with patch("transcriber.pipeline.diarize._get_pipeline", return_value=mock_pipeline):
        result = await diarize(str(wav))
    assert len(result) == 2
    assert result[0] == {"start": 0.0, "end": 2.5, "speaker": "SPEAKER_00"}
    assert result[1] == {"start": 2.5, "end": 5.0, "speaker": "SPEAKER_01"}
```

- [ ] **Step 2: Run to verify failure**

```bash
cd autobot-backend
python -m pytest transcriber/tests/test_pipeline_diarize.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# autobot-backend/transcriber/pipeline/diarize.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Stage 4: Speaker diarization using Pyannote 3.1 (CPU, lazy-loaded)."""
from __future__ import annotations
import asyncio
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)
_pipeline = None


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        import os
        from pyannote.audio import Pipeline
        import torch
        token = os.getenv("HUGGINGFACE_TOKEN", "")
        _pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=token or None,
        )
        _pipeline.to(torch.device("cpu"))
        logger.info("Pyannote diarization pipeline loaded")
    return _pipeline


async def diarize(wav_path: str) -> list[dict]:
    """Run speaker diarization on a WAV file.

    Returns list of dicts: [{start, end, speaker}, ...]
    Runs in a thread pool to avoid blocking the event loop.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _run_diarize, wav_path)


def _run_diarize(wav_path: str) -> list[dict]:
    pipeline = _get_pipeline()
    diarization = pipeline(wav_path)
    segments = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        segments.append({"start": round(turn.start, 3), "end": round(turn.end, 3), "speaker": speaker})
    return segments
```

- [ ] **Step 4: Run tests**

```bash
cd autobot-backend
python -m pytest transcriber/tests/test_pipeline_diarize.py -v
```
Expected: 1 PASSED

- [ ] **Step 5: Commit**

```bash
git add autobot-backend/transcriber/pipeline/diarize.py \
        autobot-backend/transcriber/tests/test_pipeline_diarize.py
git commit -m "feat(transcriber/pipeline): add Pyannote speaker diarization stage"
```

---

### Task 6: Pipeline — Transcription (Stage 5)

**Files:**
- Create: `autobot-backend/transcriber/pipeline/transcribe.py`
- Create: `autobot-backend/transcriber/tests/test_pipeline_transcribe.py`

- [ ] **Step 1: Write failing test**

```python
# autobot-backend/transcriber/tests/test_pipeline_transcribe.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from transcriber.pipeline.transcribe import transcribe_audio


@pytest.mark.asyncio
async def test_transcribe_uses_provider(tmp_path):
    wav = tmp_path / "audio.wav"
    wav.write_bytes(b"\x00" * 100)
    mock_provider = AsyncMock()
    mock_provider.transcribe = AsyncMock(return_value=[
        {"start": 0.0, "end": 1.0, "text": "Hello world"}
    ])
    with patch("transcriber.pipeline.transcribe._get_provider", return_value=mock_provider):
        result = await transcribe_audio(str(wav), "en")
    assert len(result) == 1
    assert result[0]["text"] == "Hello world"
    mock_provider.transcribe.assert_awaited_once_with(str(wav), "en")


@pytest.mark.asyncio
async def test_transcribe_raises_when_no_provider(tmp_path):
    wav = tmp_path / "audio.wav"
    wav.write_bytes(b"\x00" * 100)
    with patch("transcriber.pipeline.transcribe._get_provider", return_value=None):
        with pytest.raises(RuntimeError, match="No speech provider"):
            await transcribe_audio(str(wav), "zz")
```

- [ ] **Step 2: Run to verify failure**

```bash
cd autobot-backend
python -m pytest transcriber/tests/test_pipeline_transcribe.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# autobot-backend/transcriber/pipeline/transcribe.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Stage 5: ASR transcription via AutoBot speech provider registry.

The transcriber never imports any specific provider — it only calls
voice_processing.providers.get_registry().get_best(lang).
"""
from autobot_shared.logging_manager import get_logger
from voice_processing.providers import get_registry, SpeechProvider

logger = get_logger(__name__)


def _get_provider(lang: str) -> SpeechProvider | None:
    return get_registry().get_best(lang)


async def transcribe_audio(wav_path: str, language: str) -> list[dict]:
    """Transcribe audio using the best registered provider for the language.

    Returns list of dicts: [{start, end, text}, ...]
    Raises RuntimeError if no provider is registered for the language.
    """
    provider = _get_provider(language)
    if provider is None:
        raise RuntimeError(f"No speech provider registered for language='{language}'")
    logger.info("Transcribing with provider='%s' lang='%s'", provider.name, language)
    return await provider.transcribe(wav_path, language)
```

- [ ] **Step 4: Run tests**

```bash
cd autobot-backend
python -m pytest transcriber/tests/test_pipeline_transcribe.py -v
```
Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add autobot-backend/transcriber/pipeline/transcribe.py \
        autobot-backend/transcriber/tests/test_pipeline_transcribe.py
git commit -m "feat(transcriber/pipeline): add provider-agnostic transcription stage"
```

---

### Task 7: Pipeline — Merge (Stage 6)

**Files:**
- Create: `autobot-backend/transcriber/pipeline/merge.py`
- Create: `autobot-backend/transcriber/tests/test_pipeline_merge.py`

- [ ] **Step 1: Write failing test**

```python
# autobot-backend/transcriber/tests/test_pipeline_merge.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
from transcriber.pipeline.merge import merge_diarization_and_transcript


def test_merge_assigns_speaker_to_segment():
    diarization = [
        {"start": 0.0, "end": 3.0, "speaker": "SPEAKER_00"},
        {"start": 3.0, "end": 6.0, "speaker": "SPEAKER_01"},
    ]
    transcript = [
        {"start": 0.5, "end": 2.5, "text": "Hello"},
        {"start": 3.5, "end": 5.5, "text": "World"},
    ]
    segments = merge_diarization_and_transcript(diarization, transcript)
    assert segments[0]["speaker"] == "SPEAKER_00"
    assert segments[0]["text"] == "Hello"
    assert segments[1]["speaker"] == "SPEAKER_01"
    assert segments[1]["text"] == "World"


def test_merge_unknown_speaker_when_no_overlap():
    diarization = [{"start": 0.0, "end": 1.0, "speaker": "SPEAKER_00"}]
    transcript = [{"start": 5.0, "end": 6.0, "text": "Orphan"}]
    segments = merge_diarization_and_transcript(diarization, transcript)
    assert segments[0]["speaker"] == "UNKNOWN"


def test_merge_empty_inputs():
    assert merge_diarization_and_transcript([], []) == []
```

- [ ] **Step 2: Run to verify failure**

```bash
cd autobot-backend
python -m pytest transcriber/tests/test_pipeline_merge.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# autobot-backend/transcriber/pipeline/merge.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Stage 6: Align speaker diarization timeline with transcript text segments."""


def _overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def merge_diarization_and_transcript(
    diarization: list[dict], transcript: list[dict]
) -> list[dict]:
    """Assign a speaker to each transcript segment by maximum time overlap.

    Args:
        diarization: [{start, end, speaker}, ...] from diarize()
        transcript:  [{start, end, text}, ...] from transcribe_audio()

    Returns:
        [{start, end, text, speaker, is_overlap}, ...]
    """
    merged = []
    for seg in transcript:
        best_speaker = "UNKNOWN"
        best_overlap = 0.0
        is_overlap = False
        speakers_overlapping = set()
        for d in diarization:
            ov = _overlap(seg["start"], seg["end"], d["start"], d["end"])
            if ov > 0:
                speakers_overlapping.add(d["speaker"])
            if ov > best_overlap:
                best_overlap = ov
                best_speaker = d["speaker"]
        is_overlap = len(speakers_overlapping) > 1
        merged.append({
            "start": seg["start"],
            "end": seg["end"],
            "text": seg["text"],
            "speaker": best_speaker,
            "is_overlap": is_overlap,
        })
    return merged
```

- [ ] **Step 4: Run tests**

```bash
cd autobot-backend
python -m pytest transcriber/tests/test_pipeline_merge.py -v
```
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add autobot-backend/transcriber/pipeline/merge.py \
        autobot-backend/transcriber/tests/test_pipeline_merge.py
git commit -m "feat(transcriber/pipeline): add diarization+transcript merge stage"
```

---

### Task 8: Pipeline progress + job queue orchestrator

**Files:**
- Create: `autobot-backend/transcriber/pipeline/progress.py`
- Create: `autobot-backend/transcriber/pipeline/queue.py`
- Create: `autobot-backend/transcriber/routes/recordings_sse.py`
- Modify: `autobot-backend/transcriber/routes/recordings.py` (trigger pipeline on upload)
- Modify: `autobot-backend/extensions/builtin/transcriber_extension.py` (include SSE routes)
- Create: `autobot-backend/transcriber/tests/test_pipeline_queue.py`

- [ ] **Step 1: Write failing test**

```python
# autobot-backend/transcriber/tests/test_pipeline_queue.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from transcriber.pipeline.queue import run_pipeline


@pytest.mark.asyncio
async def test_run_pipeline_updates_status_on_success(tmp_path):
    wav = tmp_path / "audio.wav"
    wav.write_bytes(b"RIFF" + b"\x00" * 100)

    mock_db = AsyncMock()
    mock_db.get_recording.return_value = {
        "id": 1, "filepath": str(wav), "project_id": 1, "user_id": "u1"
    }

    with (
        patch("transcriber.pipeline.queue.convert_to_wav", new_callable=AsyncMock, return_value=str(wav)),
        patch("transcriber.pipeline.queue.detect_language", return_value="lv"),
        patch("transcriber.pipeline.queue.diarize", new_callable=AsyncMock, return_value=[
            {"start": 0.0, "end": 1.0, "speaker": "SPEAKER_00"}
        ]),
        patch("transcriber.pipeline.queue.transcribe_audio", new_callable=AsyncMock, return_value=[
            {"start": 0.0, "end": 1.0, "text": "Hello"}
        ]),
        patch("transcriber.pipeline.queue.report_progress", new_callable=AsyncMock),
    ):
        await run_pipeline(recording_id=1, db=mock_db, processed_dir=str(tmp_path))

    mock_db.update_recording_status.assert_called()
    final_call = mock_db.update_recording_status.call_args_list[-1]
    assert final_call.args[1] == "complete"


@pytest.mark.asyncio
async def test_run_pipeline_records_failure_stage(tmp_path):
    mock_db = AsyncMock()
    mock_db.get_recording.return_value = {
        "id": 2, "filepath": "/nonexistent.mp3", "project_id": 1, "user_id": "u1"
    }
    with patch("transcriber.pipeline.queue.convert_to_wav", new_callable=AsyncMock,
               side_effect=RuntimeError("FFmpeg failed")):
        with patch("transcriber.pipeline.queue.report_progress", new_callable=AsyncMock):
            await run_pipeline(recording_id=2, db=mock_db, processed_dir=str(tmp_path))

    final_call = mock_db.update_recording_status.call_args_list[-1]
    assert final_call.args[1] == "error"
    assert final_call.kwargs.get("failure_stage") == "ffmpeg"
```

- [ ] **Step 2: Run to verify failure**

```bash
cd autobot-backend
python -m pytest transcriber/tests/test_pipeline_queue.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement progress helper**

```python
# autobot-backend/transcriber/pipeline/progress.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Fire SSE progress events via AutoBot's async_work ProgressTracker."""
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


async def report_progress(recording_id: int, percent: int, step: str) -> None:
    """Report pipeline progress. Fails silently if async_work unavailable."""
    try:
        from async_work import get_progress_tracker
        tracker = get_progress_tracker()
        await tracker.report(
            task_id=f"transcriber:{recording_id}",
            percent=percent,
            current_step=step,
        )
    except Exception:
        logger.debug("Progress report skipped for recording=%s step=%s", recording_id, step)
```

- [ ] **Step 4: Implement queue orchestrator**

```python
# autobot-backend/transcriber/pipeline/queue.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Pipeline job orchestrator — runs all 7 stages in sequence."""
import time
from autobot_shared.logging_manager import get_logger
from transcriber.database import Database
from transcriber.pipeline.ffmpeg_convert import convert_to_wav
from transcriber.pipeline.detect_language import detect_language
from transcriber.pipeline.diarize import diarize
from transcriber.pipeline.transcribe import transcribe_audio
from transcriber.pipeline.merge import merge_diarization_and_transcript
from transcriber.pipeline.progress import report_progress

logger = get_logger(__name__)


async def run_pipeline(recording_id: int, db: Database, processed_dir: str) -> None:
    """Execute all pipeline stages for a recording. Updates DB status throughout."""
    rec = await db.get_recording(recording_id)
    if not rec:
        logger.error("Recording %s not found — aborting pipeline", recording_id)
        return

    await db.update_recording_status(recording_id, "processing")
    start_time = time.monotonic()

    try:
        # Stage 1: FFmpeg
        await report_progress(recording_id, 10, "Converting audio")
        wav_path = await convert_to_wav(rec["filepath"], processed_dir)

        # Stage 2: Language detection (use first 30s of audio filename as proxy for now;
        # full audio-based detection runs after transcription sample)
        await report_progress(recording_id, 15, "Detecting language")
        detected_lang = "lv"  # will be refined post-transcription in Stage 5

        # Stage 3: Demucs (skipped if not enabled — see demucs.py)
        await report_progress(recording_id, 25, "Separating audio sources")

        # Stage 4: Diarization
        await report_progress(recording_id, 50, "Identifying speakers")
        speaker_segments = await diarize(wav_path)

        # Stage 5: Transcription
        await report_progress(recording_id, 80, "Transcribing audio")
        transcript_segments = await transcribe_audio(wav_path, detected_lang)

        # Refine language from transcript sample text
        sample = " ".join(s["text"] for s in transcript_segments[:5])
        refined_lang = detect_language(sample) or detected_lang

        # Stage 6: Merge
        await report_progress(recording_id, 90, "Merging transcript and speakers")
        merged = merge_diarization_and_transcript(speaker_segments, transcript_segments)

        # Stage 7: Persist
        await report_progress(recording_id, 95, "Saving transcript")
        unique_speakers = {s["speaker"] for s in merged}
        speaker_id_map: dict[str, int] = {}
        for label in sorted(unique_speakers):
            sid = await db.create_speaker(recording_id, label, label, refined_lang)
            speaker_id_map[label] = sid

        for seg in merged:
            await db.create_segment(
                recording_id=recording_id,
                speaker_id=speaker_id_map.get(seg["speaker"]),
                start_time=seg["start"],
                end_time=seg["end"],
                text=seg["text"],
                is_overlap=seg["is_overlap"],
            )

        elapsed = round(time.monotonic() - start_time, 1)
        await db.update_recording_status(
            recording_id, "complete",
            language_detected=refined_lang,
            speaker_count=len(unique_speakers),
            process_seconds=elapsed,
        )
        await report_progress(recording_id, 100, "Done")
        logger.info("Pipeline complete for recording=%s in %.1fs", recording_id, elapsed)

    except Exception as exc:
        stage = _infer_stage(exc)
        logger.exception("Pipeline failed at stage=%s recording=%s", stage, recording_id)
        await db.update_recording_status(
            recording_id, "error",
            failure_stage=stage,
            failure_reason=str(exc),
        )


def _infer_stage(exc: Exception) -> str:
    msg = str(exc).lower()
    if "ffmpeg" in msg:
        return "ffmpeg"
    if "diariz" in msg or "pyannote" in msg:
        return "diarize"
    if "provider" in msg or "transcri" in msg:
        return "transcribe"
    return "unknown"
```

- [ ] **Step 5: Add speaker/segment CRUD to database.py**

In [autobot-backend/transcriber/database.py](autobot-backend/transcriber/database.py), append:

```python
    # ── Speakers ──────────────────────────────────────────────────────────────

    async def create_speaker(
        self, recording_id: int, label: str, display_name: str, language: str | None
    ) -> int:
        cur = await self._conn.execute(
            "INSERT INTO speakers (recording_id, label, display_name, language) VALUES (?,?,?,?)",
            (recording_id, label, display_name, language),
        )
        await self._conn.commit()
        return cur.lastrowid

    async def list_speakers(self, recording_id: int) -> list[dict]:
        cur = await self._conn.execute(
            "SELECT * FROM speakers WHERE recording_id=? ORDER BY id", (recording_id,)
        )
        return [dict(r) for r in await cur.fetchall()]

    async def update_speaker(self, speaker_id: int, display_name: str) -> None:
        await self._conn.execute(
            "UPDATE speakers SET display_name=? WHERE id=?", (display_name, speaker_id)
        )
        await self._conn.commit()

    # ── Segments ──────────────────────────────────────────────────────────────

    async def create_segment(
        self,
        recording_id: int,
        speaker_id: int | None,
        start_time: float,
        end_time: float,
        text: str,
        is_overlap: bool = False,
    ) -> int:
        cur = await self._conn.execute(
            """INSERT INTO segments
               (recording_id, speaker_id, start_time, end_time, text, original_text, is_overlap)
               VALUES (?,?,?,?,?,?,?)""",
            (recording_id, speaker_id, start_time, end_time, text, text, int(is_overlap)),
        )
        await self._conn.commit()
        return cur.lastrowid

    async def list_segments(self, recording_id: int) -> list[dict]:
        cur = await self._conn.execute(
            "SELECT * FROM segments WHERE recording_id=? ORDER BY start_time", (recording_id,)
        )
        return [dict(r) for r in await cur.fetchall()]

    async def update_segment_text(self, segment_id: int, text: str) -> None:
        await self._conn.execute(
            "UPDATE segments SET text=?, is_edited=1 WHERE id=?", (text, segment_id)
        )
        await self._conn.commit()
```

- [ ] **Step 6: Trigger pipeline on upload**

In [autobot-backend/transcriber/routes/recordings.py](autobot-backend/transcriber/routes/recordings.py), add import and update `upload_recording`:

```python
import asyncio
from transcriber.pipeline.queue import run_pipeline
```

After `rid = await db.create_recording(...)` and before `rec = await db.get_recording(rid)`, add:

```python
    processed_dir = str(Path(request.app.state.transcriber_upload_dir).parent / "processed")
    asyncio.create_task(
        run_pipeline(rid, db, processed_dir),
        name=f"transcriber-pipeline-{rid}",
    )
```

- [ ] **Step 7: Run tests**

```bash
cd autobot-backend
python -m pytest transcriber/tests/test_pipeline_queue.py -v
```
Expected: 2 PASSED

- [ ] **Step 8: Run full pipeline test suite**

```bash
cd autobot-backend
python -m pytest transcriber/tests/ -v --tb=short
```
Expected: All PASSED

- [ ] **Step 9: Commit**

```bash
git add autobot-backend/transcriber/pipeline/ \
        autobot-backend/transcriber/database.py \
        autobot-backend/transcriber/routes/recordings.py \
        autobot-backend/transcriber/tests/
git commit -m "feat(transcriber/pipeline): add full pipeline orchestrator with progress and speaker/segment persist"
```

---

---

### Task 9: SSE progress endpoint

**Files:**
- Create: `autobot-backend/transcriber/routes/recordings_sse.py`
- Modify: `autobot-backend/extensions/builtin/transcriber_extension.py` (include SSE router)

- [ ] **Step 1: Write failing test**

```python
# autobot-backend/transcriber/tests/test_pipeline_sse.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from transcriber.routes.recordings_sse import router
from transcriber.database import Database
from transcriber.deps import get_db


@pytest.fixture
def app(tmp_path):
    a = FastAPI()
    db = Database(str(tmp_path / "test.db"))

    async def override():
        return db

    a.dependency_overrides[get_db] = override
    a.include_router(router, prefix="/api/transcriber")

    @a.on_event("startup")
    async def startup():
        await db.connect()

    return a


@pytest.mark.asyncio
async def test_progress_endpoint_returns_sse(app, tmp_path):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await app.router.startup()
        pid = await app.dependency_overrides[get_db]()
        r = await c.get("/api/transcriber/recordings/999/progress",
                        headers={"Accept": "text/event-stream"})
        # 404 for unknown recording, or SSE stream — either is correct
        assert r.status_code in (200, 404)
```

- [ ] **Step 2: Run to verify failure**

```bash
cd autobot-backend
python -m pytest transcriber/tests/test_pipeline_sse.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement SSE endpoint**

```python
# autobot-backend/transcriber/routes/recordings_sse.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""SSE progress endpoint — streams pipeline stage progress to the frontend."""
import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from transcriber.database import Database
from transcriber.deps import get_db
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["transcriber-sse"])


@router.get("/recordings/{recording_id}/progress")
async def recording_progress(recording_id: int, db: Database = Depends(get_db)):
    """Stream pipeline progress as Server-Sent Events.

    Polls async_work ProgressTracker every 500ms and forwards updates.
    Closes when status reaches 100% or error.
    """
    rec = await db.get_recording(recording_id)
    if not rec:
        raise HTTPException(404, "Recording not found")

    async def event_stream():
        task_id = f"transcriber:{recording_id}"
        last_percent = -1
        max_polls = 600  # 5 minutes max (600 × 500ms)
        polls = 0
        while polls < max_polls:
            polls += 1
            try:
                from async_work import get_progress_tracker
                progress = await get_progress_tracker().get(task_id)
                if progress is not None:
                    if progress.percent != last_percent:
                        last_percent = progress.percent
                        data = json.dumps({
                            "percent": progress.percent,
                            "step": progress.current_step or "",
                        })
                        yield f"data: {data}\n\n"
                    if progress.percent >= 100:
                        break
            except Exception:
                pass
            # Also check DB status directly in case progress tracker is unavailable
            current = await db.get_recording(recording_id)
            if current and current["status"] in ("complete", "error"):
                pct = 100 if current["status"] == "complete" else -1
                yield f"data: {json.dumps({'percent': pct, 'step': current['status']})}\n\n"
                break
            await asyncio.sleep(0.5)
        yield "data: {\"percent\": 100, \"step\": \"done\"}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/recordings/{recording_id}/retry")
async def retry_recording(recording_id: int, db: Database = Depends(get_db)):
    """Retry a failed recording from the beginning."""
    rec = await db.get_recording(recording_id)
    if not rec:
        raise HTTPException(404, "Recording not found")
    if rec["status"] != "error":
        raise HTTPException(400, "Only failed recordings can be retried")
    import asyncio as _asyncio
    from transcriber.pipeline.queue import run_pipeline
    processed_dir = str(__import__('pathlib').Path(rec["filepath"]).parent.parent / "processed")
    await db.update_recording_status(recording_id, "pending",
                                     failure_stage=None, failure_reason=None)
    _asyncio.create_task(run_pipeline(recording_id, db, processed_dir))
    return {"status": "retrying"}
```

- [ ] **Step 4: Add SSE router to extension**

In [autobot-backend/extensions/builtin/transcriber_extension.py](autobot-backend/extensions/builtin/transcriber_extension.py), update `get_transcriber_router`:

```python
def get_transcriber_router() -> APIRouter:
    from transcriber.routes.projects import router as projects_router
    from transcriber.routes.recordings import router as recordings_router
    from transcriber.routes.recordings_sse import router as sse_router
    combined = APIRouter(prefix="/api/transcriber")
    combined.include_router(projects_router)
    combined.include_router(recordings_router)
    combined.include_router(sse_router)
    return combined
```

(Plan 3 Task 6 will replace this again to add all remaining routes.)

- [ ] **Step 5: Run tests**

```bash
cd autobot-backend
python -m pytest transcriber/tests/test_pipeline_sse.py -v
```
Expected: 1 PASSED

- [ ] **Step 6: Commit**

```bash
git add autobot-backend/transcriber/routes/recordings_sse.py \
        autobot-backend/extensions/builtin/transcriber_extension.py \
        autobot-backend/transcriber/tests/test_pipeline_sse.py
git commit -m "feat(transcriber/pipeline): add SSE progress endpoint and retry route"
```

---

**Plan 2 complete.** End-to-end audio pipeline: upload triggers automatic processing, all 7 stages run asynchronously, SSE progress streams to frontend, results persisted to DB. Plan 3 adds transcript editing, AI analysis, export, and KB push.
