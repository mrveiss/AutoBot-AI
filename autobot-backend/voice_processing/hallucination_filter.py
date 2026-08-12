# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""STT silence-hallucination filter.

Issue #13104: Whisper-family models do not return an empty string when handed
silence or ambient noise — they emit a confident, fluent phrase drawn from
their training data (YouTube captions, subtitle credits). With the mic held
open in hands-free and full-duplex modes, that phrase becomes a **phantom user
turn** and wakes the agent for a run nobody asked for.

Signals, cheapest first:

1. ``no_speech_prob`` — the decoder's own "this frame is not speech" estimate.
   Authoritative, but only openai-whisper surfaces it; the transformers ASR
   pipeline does not, so most call sites cannot supply it.
2. Audio energy — see :func:`peak_window_rms`. Below the floor there was
   nothing to transcribe, so *any* transcript over it is an artifact.
3. Structural audio tags — "[BLANK_AUDIO]", "(silence)", "♪♪". Language
   independent: no one speaks a bracket.
4. Per-language artifact phrases, split into two tiers (see below).

NOTHING IS DISCARDED SILENTLY
-----------------------------
Every gate logs at INFO with the discarded text and the reason. A swallowed
turn that leaves no trace is indistinguishable from a broken microphone, and
the whole point of this module is to make that class of failure diagnosable.

KEEP THE DENYLIST TIGHT — DO NOT WIDEN IT
-----------------------------------------
Real users answer in one or two words: "okay", "yeah", "no", "so", "bye",
"yes", "stop", "music". A filter that swallows those is far worse than the
phantom turns it prevents, because the assistant then appears to ignore the
user.

Hence two tiers:

* **Structural** — subtitle credits and URLs carrying proper nouns
  ("Subtitles by the Amara.org community", "www.mooji.org"). Nobody dictates
  these, so they are discarded whatever the audio says.
* **Outro** — polite sign-offs Whisper also invents ("Thanks for watching!",
  "Please subscribe to my channel."). These *are* plausible dictation, so they
  are discarded only when the audio does not positively show speech energy.
  On a live mic that is the hallucination case; on a dictation upload with
  real energy the words survive.

If you are about to add a word a person could reasonably say out loud, it goes
in the outro tier at most — or the gate thresholds want tuning instead.
"""

import math
import re
import string
from typing import Dict, FrozenSet, Optional, Sequence, Set

from autobot_shared.env_utils import env_float, env_int
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


# Below this RMS the waveform carries no speech, so any transcript over it is an
# artifact. 0.005 sits well under conversational speech (~0.05-0.2 RMS) and above
# typical mic self-noise. Raise it for a noisy room, lower it for a close mic.
SILENCE_RMS_THRESHOLD = env_float("AUTOBOT_STT_SILENCE_RMS_THRESHOLD", 0.005)

# Whisper's own no-speech estimate. The reference decoder treats >0.6 combined
# with a low average log-prob as silence; used alone here, so kept deliberately
# high to avoid discarding quiet but real speech.
NO_SPEECH_PROB_THRESHOLD = env_float("AUTOBOT_STT_NO_SPEECH_PROB_THRESHOLD", 0.8)

# Energy is measured over short windows, not the whole buffer (#13104 review D).
# A 0.5 s reply inside a 30 s recording averages away to nothing: 0.03 RMS of
# speech over 30 s of silence computes to ~0.0039, under the floor, and the turn
# would be dropped. The loudest 100 ms window keeps short utterances audible to
# the gate while still reading as silence when the buffer really is empty.
PEAK_WINDOW_MS = env_int("AUTOBOT_STT_PEAK_WINDOW_MS", 100)


# Artifact phrases keyed by BCP-47 language. Matched exactly after normalisation
# — never as a substring — so a real sentence that happens to contain one of
# these survives. Read the module docstring before editing either tier.
#
# Tier 1: credit strings and URLs. Never plausible dictation.
_RAW_STRUCTURAL_ARTIFACTS: Dict[str, Set[str]] = {
    "en": {
        "Subtitles by the Amara.org community",
        "Transcription by CastingWords",
        "Subtitles by SteamTeamExtra",
        "www.mooji.org",
    },
    "lv": {
        "Subtitrus sagatavoja",
    },
    "ru": {
        "Субтитры сделал DimaTorzok",
        "Субтитры и перевод сделал DimaTorzok",
        "Редактор субтитров А.Синецкая Корректор А.Егорова",
    },
    "de": {
        "Untertitelung des ZDF, 2020",
        "Untertitel im Auftrag des ZDF, 2021",
        "Untertitel der Deutschen Welle",
    },
    "es": {
        "Subtítulos realizados por la comunidad de Amara.org",
    },
    "fr": {
        "Sous-titres réalisés par la communauté d'Amara.org",
    },
}

# Tier 2: polite sign-offs. Whisper invents these on silence, but a person
# dictating a video script could genuinely say them, so they are only discarded
# when the audio does not show speech energy.
_RAW_OUTRO_ARTIFACTS: Dict[str, Set[str]] = {
    "en": {
        "Thanks for watching!",
        "Thank you for watching.",
        "Thank you for watching this video.",
        "Please subscribe to my channel.",
        "Like and subscribe!",
    },
    "lv": {
        "Paldies par skatīšanos!",
    },
    "ru": {
        "Продолжение следует...",
        "Спасибо за просмотр!",
    },
    "de": {
        "Vielen Dank fürs Zuschauen!",
    },
    "es": {
        "¡Gracias por ver el video!",
    },
    "fr": {
        "Merci d'avoir regardé cette vidéo !",
    },
}

# Punctuation folds to a space, not to nothing: Whisper renders the same artifact
# as both "Amara.org" and "Amara org" across runs, and only a space keeps those
# two spellings normalising to the same key.
_PUNCTUATION = str.maketrans({ch: " " for ch in string.punctuation + "¡¿«»„“”‘’—–…♪"})
_WHITESPACE_RE = re.compile(r"\s+")

# A transcript that is nothing but a bracketed tag or musical notes.
_AUDIO_TAG_RE = re.compile(r"^\s*(?:[\[\(\{].{0,40}?[\]\)\}]|[♪♫\s]+)\s*$")


def normalize_transcript(transcript: str) -> str:
    """Lowercase, strip punctuation and collapse whitespace for exact matching."""
    lowered = transcript.strip().lower()
    stripped = lowered.translate(_PUNCTUATION)
    return _WHITESPACE_RE.sub(" ", stripped).strip()


def _normalize_table(raw: Dict[str, Set[str]]) -> Dict[str, FrozenSet[str]]:
    """Normalise a phrase table once at import so entries stay readable above."""
    return {lang: frozenset(normalize_transcript(p) for p in phrases) for lang, phrases in raw.items()}


_STRUCTURAL_ARTIFACTS = _normalize_table(_RAW_STRUCTURAL_ARTIFACTS)
_OUTRO_ARTIFACTS = _normalize_table(_RAW_OUTRO_ARTIFACTS)


def peak_window_rms(
    samples: Sequence[float],
    sample_rate: int,
    window_ms: int = PEAK_WINDOW_MS,
) -> float:
    """Return the highest RMS found in any *window_ms* slice of *samples*.

    Whole-buffer RMS averages a short utterance away against surrounding
    silence and would discard it as a hallucination (#13104 review D). Taking
    the loudest short window instead answers the question the gate actually
    asks: "was there speech anywhere in here?"
    """
    total = len(samples)
    if total == 0:
        return 0.0

    window = max(1, int(sample_rate * window_ms / 1000)) if sample_rate > 0 else total
    peak = 0.0
    for start in range(0, total, window):
        chunk = samples[start : start + window]
        if not len(chunk):
            continue
        mean_square = sum(float(value) * float(value) for value in chunk) / len(chunk)
        peak = max(peak, math.sqrt(mean_square))
    return peak


def _artifact_tier(transcript: str, language: Optional[str]) -> Optional[str]:
    """Return "structural"/"outro" when *transcript* matches an artifact, else None.

    An unknown or uncurated language never matches — a denylist for a locale we
    have not reviewed would be guesswork applied to real user speech.
    """
    if not language:
        return None
    key = language.split("-")[0].lower()
    normalized = normalize_transcript(transcript)
    if normalized in _STRUCTURAL_ARTIFACTS.get(key, frozenset()):
        return "structural"
    if normalized in _OUTRO_ARTIFACTS.get(key, frozenset()):
        return "outro"
    return None


def is_known_artifact(transcript: str, language: Optional[str]) -> bool:
    """Return True when *transcript* matches any artifact phrase for *language*."""
    return _artifact_tier(transcript, language) is not None


def is_audio_tag(transcript: str) -> bool:
    """Return True when the transcript is only a bracketed tag or musical notes.

    Language-independent: "[BLANK_AUDIO]", "(silence)", "♪♪" are decoder markup
    for "no speech here", and cannot be uttered.
    """
    return bool(transcript.strip()) and bool(_AUDIO_TAG_RE.match(transcript))


def _discard_reason(
    transcript: str,
    language: Optional[str],
    rms: Optional[float],
    no_speech_prob: Optional[float],
) -> Optional[str]:
    """Return a human-readable reason to discard *transcript*, or None to keep it."""
    if no_speech_prob is not None and no_speech_prob >= NO_SPEECH_PROB_THRESHOLD:
        return f"no_speech_prob {no_speech_prob:.3f} >= {NO_SPEECH_PROB_THRESHOLD}"

    if rms is not None and rms < SILENCE_RMS_THRESHOLD:
        return f"peak audio RMS {rms:.5f} < silence floor {SILENCE_RMS_THRESHOLD}"

    if is_audio_tag(transcript):
        return "transcript is a bare audio tag"

    tier = _artifact_tier(transcript, language)
    if tier == "structural":
        return f"known {language} subtitle-credit artifact"
    if tier == "outro" and rms is None:
        # No energy evidence either way; on a live mic this phrase is the
        # classic silence hallucination. With real energy measured it is kept.
        return f"known {language} outro artifact, no audio energy evidence"
    return None


def is_silence_hallucination(
    transcript: str,
    language: Optional[str] = None,
    *,
    rms: Optional[float] = None,
    no_speech_prob: Optional[float] = None,
) -> bool:
    """Return True when *transcript* must be discarded instead of becoming a turn.

    Logs at INFO with the discarded text whenever it returns True — no transcript
    is ever dropped without a diagnosable trace.

    Args:
        transcript: Text returned by the STT backend.
        language: BCP-47 code for the denylist; None disables the phrase tiers.
        rms: Peak short-window energy of the source audio, if measured.
        no_speech_prob: Decoder no-speech probability, if the backend exposes it.
    """
    if not transcript or not transcript.strip():
        return False

    reason = _discard_reason(transcript, language, rms, no_speech_prob)
    if reason is None:
        return False

    logger.info(
        "STT silence filter discarded transcript %r (language=%s): %s",
        transcript,
        language or "unknown",
        reason,
    )
    return True
