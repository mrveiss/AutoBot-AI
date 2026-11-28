# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""WAV arithmetic shared by every service that measures audio (#13841).

Two call sites computed ``getnframes() / float(framerate)`` independently
(`services/tts_client.py`, `voice_processing/providers/generic_provider.py`) and
there was no audio module to put it in, which is how it got duplicated.

TAKES AN OPEN HANDLE, deliberately, rather than bytes or a path. The two callers
differ in everything except the arithmetic: one is handed WAV **bytes** from a
streaming worker and must never raise, because telemetry cannot be allowed to
break audio delivery; the other opens a **path** and needs `readframes` and
`getframerate` off the same handle to build an `AudioInput`. A helper taking
bytes would force the second to open the file twice; one taking a path would
not serve the first at all. The shared thing is the arithmetic over an already
open file, so that is where the seam goes — each caller keeps its own input
type and its own error policy.
"""

from __future__ import annotations

import wave


def wav_duration_seconds(wav: wave.Wave_read) -> float:
    """Playable length of an open WAV, or ``0.0`` when the header cannot say.

    A zero or negative frame rate is a malformed header rather than a
    zero-length file, and dividing by it would raise inside a caller that is
    usually measuring something incidental. Returning 0.0 keeps that decision
    here instead of at each call site.
    """
    frame_rate = wav.getframerate()
    if frame_rate <= 0:
        return 0.0
    return wav.getnframes() / float(frame_rate)
