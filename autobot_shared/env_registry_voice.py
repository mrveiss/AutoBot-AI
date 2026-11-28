# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Voice / speech-to-text AUTOBOT_* environment variable registrations.

Split out of ``env_registry.py`` (#22280) so that file stays under its size limit.
Registration contract (import side effect, ordering): see ``env_registry`` (#16415).
"""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_STT_SILENCE_RMS_THRESHOLD",
        type=float,
        default=0.005,
        description=(
            "Audio RMS below which the waveform is treated as silence, so any STT "
            "transcript over it is a hallucination rather than a user turn (#13104)."
        ),
        component="voice",
        range=(0.0, 1.0),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_STT_NO_SPEECH_PROB_THRESHOLD",
        type=float,
        default=0.8,
        description=(
            "Decoder no-speech probability at or above which an STT transcript is "
            "discarded as a silence hallucination (#13104)."
        ),
        component="voice",
        range=(0.0, 1.0),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_MULTIMODAL_VOICE_CONFIDENCE_THRESHOLD",
        type=float,
        default=0.7,
        description=(
            "Fallback confidence threshold for VoiceProcessor when the multimodal.voice "
            "config section omits it (#13207)."
        ),
        component="voice",
        range=(0.0, 1.0),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_MULTIMODAL_VOICE_PROCESSING_TIMEOUT",
        type=int,
        default=30,
        description=(
            "Fallback processing timeout in seconds for VoiceProcessor when the "
            "multimodal.voice config section omits it (#13207)."
        ),
        component="voice",
    )
)
