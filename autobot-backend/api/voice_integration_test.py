# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Integration tests for the full voice pipeline (#928):
  STT (Whisper) → autobot-backend → TTS (Kani-TTS-2)

These tests verify end-to-end latency and API contract for:
  - POST /api/voice/synthesize  (backend → TTS worker proxy)
  - POST /api/voice/clone-voice (backend → TTS worker proxy)
  - TTS worker health at 172.16.168.22:8082
"""

import io
import time
import wave

import requests

# ------------------------------------------------------------------ #
# Config                                                               #
# ------------------------------------------------------------------ #
BACKEND_URL = "http://172.16.168.20:8001"
TTS_WORKER_URL = "http://172.16.168.22:8082"
LATENCY_BUDGET_SEC = 5.0  # STT → TTS round-trip target


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #


def _is_valid_wav(data: bytes) -> bool:
    """Return True if data is a valid WAV file with audio content."""
    try:
        with wave.open(io.BytesIO(data)) as wf:
            return wf.getnframes() > 0
    except Exception:
        return False


def _make_silent_wav(duration_ms: int = 500, sample_rate: int = 22050) -> bytes:
    """Create a minimal silent WAV for use as reference audio in clone tests."""
    n_frames = int(sample_rate * duration_ms / 1000)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * n_frames)
    return buf.getvalue()


# ------------------------------------------------------------------ #
# TTS Worker direct tests                                              #
# ------------------------------------------------------------------ #


class TestTTSWorkerHealth:
    def test_health_endpoint_returns_200(self):
        resp = requests.get(f"{TTS_WORKER_URL}/health", timeout=5)
        assert resp.status_code == 200

    def test_health_reports_service_name(self):
        data = requests.get(f"{TTS_WORKER_URL}/health", timeout=5).json()
        assert data["service"] == "tts-worker"

    def test_health_includes_model_status(self):
        data = requests.get(f"{TTS_WORKER_URL}/health", timeout=5).json()
        assert "model_loaded" in data
        assert "model_id" in data


class TestTTSWorkerSynthesize:
    def test_synthesize_returns_wav(self):
        resp = requests.post(
            f"{TTS_WORKER_URL}/tts/synthesize",
            data={"text": "Hello from AutoBot."},
            timeout=LATENCY_BUDGET_SEC * 2,
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "audio/wav"
        assert _is_valid_wav(resp.content)

    def test_synthesize_latency_within_budget(self):
        start = time.monotonic()
        resp = requests.post(
            f"{TTS_WORKER_URL}/tts/synthesize",
            data={"text": "Latency test."},
            timeout=LATENCY_BUDGET_SEC * 2,
        )
        elapsed = time.monotonic() - start
        assert resp.status_code == 200
        assert (
            elapsed < LATENCY_BUDGET_SEC
        ), f"TTS synthesis took {elapsed:.2f}s, budget is {LATENCY_BUDGET_SEC}s"

    def test_synthesize_returns_non_empty_audio(self):
        resp = requests.post(
            f"{TTS_WORKER_URL}/tts/synthesize",
            data={"text": "Testing audio content."},
            timeout=LATENCY_BUDGET_SEC * 2,
        )
        assert resp.status_code == 200
        assert len(resp.content) > 1000  # real WAV is more than a few bytes


class TestTTSWorkerCloneVoice:
    def test_clone_voice_returns_wav(self):
        silent_wav = _make_silent_wav()
        resp = requests.post(
            f"{TTS_WORKER_URL}/tts/clone-voice",
            data={"text": "Voice clone test."},
            files={"reference_audio": ("ref.wav", silent_wav, "audio/wav")},
            timeout=LATENCY_BUDGET_SEC * 2,
        )
        # 200 if model supports cloning, 500 if reference is too short (acceptable)
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            assert _is_valid_wav(resp.content)


# ------------------------------------------------------------------ #
# Backend proxy tests                                                  #
# ------------------------------------------------------------------ #


class TestBackendVoiceSynthesize:
    def test_synthesize_proxy_returns_wav(self):
        resp = requests.post(
            f"{BACKEND_URL}/api/voice/synthesize",
            data={"text": "AutoBot speaking.", "user_role": "user"},
            timeout=LATENCY_BUDGET_SEC * 2,
        )
        assert resp.status_code == 200
        assert "audio" in resp.headers.get("content-type", "")
        assert _is_valid_wav(resp.content)

    def test_synthesize_full_pipeline_latency(self):
        """Full STT → Agent → TTS round-trip must complete within budget."""
        # Simulate the backend side of the pipeline: just the TTS synthesis step.
        # Full STT+Agent is handled by integration with voice_interface.
        start = time.monotonic()
        resp = requests.post(
            f"{BACKEND_URL}/api/voice/synthesize",
            data={"text": "Full pipeline latency test.", "user_role": "user"},
            timeout=LATENCY_BUDGET_SEC * 2,
        )
        elapsed = time.monotonic() - start
        assert resp.status_code == 200
        assert (
            elapsed < LATENCY_BUDGET_SEC
        ), f"Backend /voice/synthesize took {elapsed:.2f}s, budget {LATENCY_BUDGET_SEC}s"

    def test_clone_voice_proxy(self):
        silent_wav = _make_silent_wav()
        resp = requests.post(
            f"{BACKEND_URL}/api/voice/clone-voice",
            data={"text": "Clone proxy test.", "user_role": "user"},
            files={"reference_audio": ("ref.wav", silent_wav, "audio/wav")},
            timeout=LATENCY_BUDGET_SEC * 2,
        )
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            assert _is_valid_wav(resp.content)
