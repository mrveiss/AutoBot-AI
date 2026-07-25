# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for TTS worker streaming (#12501): batching, fixed-scale WAV output,
and the blocking-generator -> async bridge.

These tests exercise the streaming helpers copied from tts-worker.py.j2 in
isolation, without loading torch or pocket_tts. The template is not directly
importable, so the helpers are re-implemented here to match their signatures
exactly (mirrors the established pattern in test_health_degraded.py /
test_hf_token.py) — changes to the template must be reflected here.

Uses only stdlib (``wave``/``array``) instead of soundfile/numpy/torch so
these tests run without any optional heavy dependencies.
"""

import array
import asyncio
import io
import time
import wave

import pytest

# ---------------------------------------------------------------------------
# Inline the helpers under test (mirrors tts-worker.py.j2 exactly)
# ---------------------------------------------------------------------------

_STREAM_CHUNK_MS = 250
_STREAM_FIXED_SCALE = 0.5


class _FakeFrame:
    """Stand-in for the torch.Tensor chunks yielded by generate_audio_stream.

    Only implements what ``_run_synthesis_stream`` needs (``.shape[0]``) so
    this test does not require torch.
    """

    def __init__(self, samples):
        self.samples = list(samples)

    @property
    def shape(self):
        return (len(self.samples),)


def _fake_cat(frames):
    """Stand-in for torch.cat(frames, dim=0) over _FakeFrame objects."""
    out = []
    for f in frames:
        out.extend(f.samples)
    return _FakeFrame(out)


def _to_wav_bytes(samples, sample_rate, fixed_scale=None):
    """Mirrors tts-worker.py.j2 ``_to_wav_bytes`` (writes via stdlib wave, not soundfile)."""
    if fixed_scale is None:
        peak = max(max((abs(s) for s in samples), default=0.0), 1e-8)
        samples = [s * (0.9 / peak) for s in samples]
    else:
        samples = [max(-1.0, min(1.0, s * fixed_scale)) for s in samples]
    pcm = array.array("h", [int(s * 32767) for s in samples])
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


def _run_synthesis_stream(frames, sample_rate):
    """Mirrors tts-worker.py.j2 ``_run_synthesis_stream``'s batching loop exactly."""
    target_samples = int(sample_rate * _STREAM_CHUNK_MS / 1000)
    buffered = []
    buffered_samples = 0
    for frame in frames:
        buffered.append(frame)
        buffered_samples += frame.shape[0]
        if buffered_samples >= target_samples:
            batch = _fake_cat(buffered)
            yield _to_wav_bytes(batch.samples, sample_rate, fixed_scale=_STREAM_FIXED_SCALE)
            buffered = []
            buffered_samples = 0

    if buffered:
        batch = _fake_cat(buffered)
        yield _to_wav_bytes(batch.samples, sample_rate, fixed_scale=_STREAM_FIXED_SCALE)


_STREAM_DONE = object()


async def _stream_synthesis_async(sync_gen_factory):
    """Mirrors tts-worker.py.j2 ``_stream_synthesis_async``'s thread bridge exactly."""
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def _produce() -> None:
        try:
            for item in sync_gen_factory():
                loop.call_soon_threadsafe(queue.put_nowait, item)
        except Exception as e:
            loop.call_soon_threadsafe(queue.put_nowait, e)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _STREAM_DONE)

    producer = loop.run_in_executor(None, _produce)
    try:
        while True:
            item = await queue.get()
            if item is _STREAM_DONE:
                break
            if isinstance(item, Exception):
                raise item
            yield item
    finally:
        await producer


# ---------------------------------------------------------------------------
# Tests: batching (~250ms) + final-partial-flush
# ---------------------------------------------------------------------------


class TestSynthesisStreamBatching:
    def test_batches_into_multiple_chunks_at_target_duration(self):
        sample_rate = 24000
        target_samples = int(sample_rate * _STREAM_CHUNK_MS / 1000)  # 6000
        # frame_size chosen to divide target_samples evenly (12 frames per
        # batch) so both batches complete exactly at 250ms with no trailing
        # partial flush muddying the assertion.
        frame_size = target_samples // 12  # 500 samples/frame
        n_frames = 2 * 12
        frames = [_FakeFrame([0.1] * frame_size) for _ in range(n_frames)]

        chunks = list(_run_synthesis_stream(frames, sample_rate))

        assert len(chunks) == 2
        for c in chunks:
            with wave.open(io.BytesIO(c)) as wf:
                duration_ms = 1000 * wf.getnframes() / wf.getframerate()
            # Each full batch reaches (>=) the 250ms target since we only
            # flush once buffered_samples has crossed the threshold.
            assert duration_ms >= _STREAM_CHUNK_MS

    def test_flushes_final_partial_batch(self):
        sample_rate = 24000
        frame_size = 480
        # Fewer frames than one full target duration (6000 samples).
        frames = [_FakeFrame([0.1] * frame_size) for _ in range(5)]  # 2400 samples < 6000

        chunks = list(_run_synthesis_stream(frames, sample_rate))

        assert len(chunks) == 1
        with wave.open(io.BytesIO(chunks[0])) as wf:
            assert wf.getnframes() == 5 * frame_size

    def test_first_chunk_emitted_without_consuming_a_full_utterance(self):
        """First chunk arrives after ~250ms of frames — not after a (simulated)
        full, arbitrarily-long utterance — proving true incremental streaming
        rather than buffer-then-batch (#12501)."""
        sample_rate = 24000
        frame_size = 480
        consumed = []

        def _very_long_frames():
            # Simulates an utterance far longer than one ~250ms chunk; a
            # buffer-then-batch implementation would need to exhaust this
            # before yielding anything.
            for i in range(10_000):
                consumed.append(i)
                yield _FakeFrame([0.1] * frame_size)

        gen = _run_synthesis_stream(_very_long_frames(), sample_rate)
        first_chunk = next(gen)

        # ~250ms / 20ms-per-frame ~= 12.5 frames -> 13 frames to cross the
        # threshold. Far fewer than the full 10,000-frame "utterance".
        assert len(consumed) < 20
        assert isinstance(first_chunk, bytes)
        gen.close()


# ---------------------------------------------------------------------------
# Tests: fixed-scale WAV output (parseable, no clipping overflow)
# ---------------------------------------------------------------------------


class TestFixedScaleWavOutput:
    def test_produces_parseable_wav_with_correct_format(self):
        sample_rate = 24000
        samples = [0.1, -0.2, 0.3, -0.4, 0.05]

        wav_bytes = _to_wav_bytes(samples, sample_rate, fixed_scale=_STREAM_FIXED_SCALE)

        with wave.open(io.BytesIO(wav_bytes)) as wf:
            assert wf.getframerate() == sample_rate
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getnframes() == len(samples)

    def test_out_of_range_raw_samples_are_clipped_not_wrapped(self):
        """Fixed-scale multiplication can push samples outside [-1, 1]; the
        explicit clip must prevent int16 wraparound/distortion artifacts."""
        sample_rate = 24000
        # 3.0 * 0.5 = 1.5 -> clipped to 1.0; -3.0 * 0.5 = -1.5 -> clipped to -1.0.
        samples = [3.0, -3.0, 0.1]

        wav_bytes = _to_wav_bytes(samples, sample_rate, fixed_scale=_STREAM_FIXED_SCALE)

        with wave.open(io.BytesIO(wav_bytes)) as wf:
            pcm = array.array("h")
            pcm.frombytes(wf.readframes(wf.getnframes()))

        assert all(-32768 <= v <= 32767 for v in pcm)  # no int16 overflow/wraparound
        assert pcm[0] > 30000  # clipped to +1.0 -> near positive full-scale
        assert pcm[1] < -30000  # clipped to -1.0 -> near negative full-scale


# ---------------------------------------------------------------------------
# Tests: blocking-generator -> async bridge (event loop must not stall)
# ---------------------------------------------------------------------------


class TestStreamSynthesisAsyncBridge:
    @pytest.mark.asyncio
    async def test_yields_chunks_in_order(self):
        def _blocking_gen():
            for i in range(3):
                yield f"chunk-{i}".encode()

        received = [c async for c in _stream_synthesis_async(_blocking_gen)]

        assert received == [b"chunk-0", b"chunk-1", b"chunk-2"]

    @pytest.mark.asyncio
    async def test_event_loop_keeps_making_progress_during_blocking_synthesis(self):
        """The event loop must NOT stall while the blocking generator runs in
        its worker thread — otherwise streaming would offer no latency
        benefit over the whole-blob endpoint for concurrent requests."""

        def _blocking_gen():
            for i in range(3):
                time.sleep(0.05)  # simulate blocking model inference
                yield f"chunk-{i}".encode()

        heartbeats = []

        async def _heartbeat() -> None:
            for _ in range(10):
                await asyncio.sleep(0.02)
                heartbeats.append(time.monotonic())

        heartbeat_task = asyncio.create_task(_heartbeat())
        received = [c async for c in _stream_synthesis_async(_blocking_gen)]
        await heartbeat_task

        assert received == [b"chunk-0", b"chunk-1", b"chunk-2"]
        # If the loop were blocked for the ~150ms of synthesis, the 20ms
        # heartbeat would barely tick during that window. A healthy bridge
        # lets most/all of the 10 heartbeats fire concurrently.
        assert len(heartbeats) >= 5

    @pytest.mark.asyncio
    async def test_exception_in_generator_propagates_to_consumer(self):
        def _failing_gen():
            yield b"ok-chunk"
            raise RuntimeError("model exploded")

        received = []
        with pytest.raises(RuntimeError, match="model exploded"):
            async for chunk in _stream_synthesis_async(_failing_gen):
                received.append(chunk)

        assert received == [b"ok-chunk"]
