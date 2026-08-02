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

Four independent signals are used, cheapest first:

1. ``no_speech_prob`` — the decoder's own "this frame is not speech" estimate.
   Authoritative when the backend exposes it; most do not.
2. Audio energy (RMS) — if the waveform is below the noise floor there was
   nothing to transcribe, so *any* transcript over it is an artifact. This is
   the language-independent VAD gate.
3. Bracketed audio tags — "[BLANK_AUDIO]", "(silence)", "♪♪". Structural and
   language-independent: no one speaks a bracket.
4. A per-language denylist of known credit-phrase artifacts, for backends that
   give neither of the first two signals.

KEEP THE DENYLIST TIGHT — DO NOT WIDEN IT
-----------------------------------------
Real users answer in one or two words: "okay", "yeah", "no", "so", "bye",
"yes", "stop", "music". A filter that swallows those is far worse than the
phantom turns it prevents, because the assistant then appears to ignore the
user and the failure is invisible in logs.

Entries therefore have to be phrases that are *never* a plausible thing to say
to an assistant — subtitle credits and channel outros. A merely short or
polite phrase ("thank you", "bye", "music") does NOT qualify: those are caught
by the energy and no-speech gates when the audio really was silent, and
correctly kept when it was not. If you are about to add a word a person could
reasonably say out loud, the answer is to tune the gate thresholds instead.
"""

import re
import string
from typing import Dict, FrozenSet, Optional, Set

from autobot_shared.env_utils import env_float
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


# Known credit-phrase artifacts, keyed by BCP-47 language. Matched exactly after
# normalisation — never as a substring — so a real sentence that happens to
# contain one of these survives. Read the module docstring before editing.
_RAW_SILENCE_ARTIFACTS: Dict[str, Set[str]] = {
    "en": {
        "Subtitles by the Amara.org community",
        "Thanks for watching!",
        "Thank you for watching.",
        "Thank you for watching this video.",
        "Please subscribe to my channel.",
        "Like and subscribe!",
        "Transcription by CastingWords",
        "Subtitles by SteamTeamExtra",
        "www.mooji.org",
    },
    "lv": {
        "Paldies par skatīšanos!",
        "Paldies par skatīšanos.",
        "Subtitrus sagatavoja",
    },
    "ru": {
        "Продолжение следует...",
        "Спасибо за просмотр!",
        "Субтитры сделал DimaTorzok",
        "Субтитры и перевод сделал DimaTorzok",
        "Редактор субтитров А.Синецкая Корректор А.Егорова",
    },
    "de": {
        "Untertitelung des ZDF, 2020",
        "Untertitel im Auftrag des ZDF, 2021",
        "Untertitel der Deutschen Welle",
        "Vielen Dank fürs Zuschauen!",
    },
    "es": {
        "Subtítulos realizados por la comunidad de Amara.org",
        "¡Gracias por ver el video!",
        "Gracias por ver el video.",
    },
    "fr": {
        "Sous-titres réalisés par la communauté d'Amara.org",
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


# Normalised once at import so the table above stays readable as real sentences.
_SILENCE_ARTIFACTS: Dict[str, FrozenSet[str]] = {
    lang: frozenset(normalize_transcript(phrase) for phrase in phrases)
    for lang, phrases in _RAW_SILENCE_ARTIFACTS.items()
}


def is_audio_tag(transcript: str) -> bool:
    """Return True when the transcript is only a bracketed tag or musical notes.

    Language-independent: "[BLANK_AUDIO]", "(silence)", "♪♪" are decoder markup
    for "no speech here", and cannot be uttered.
    """
    return bool(transcript.strip()) and bool(_AUDIO_TAG_RE.match(transcript))


def is_known_artifact(transcript: str, language: Optional[str]) -> bool:
    """Return True when *transcript* exactly matches an artifact for *language*.

    An unknown or uncurated language never filters — a denylist for a locale we
    have not reviewed would be guesswork applied to real user speech.
    """
    if not language:
        return False
    artifacts = _SILENCE_ARTIFACTS.get(language.split("-")[0].lower())
    if not artifacts:
        return False
    return normalize_transcript(transcript) in artifacts


def is_silence_hallucination(
    transcript: str,
    language: Optional[str] = None,
    *,
    rms: Optional[float] = None,
    no_speech_prob: Optional[float] = None,
) -> bool:
    """Return True when *transcript* must be discarded instead of becoming a turn.

    Args:
        transcript: Text returned by the STT backend.
        language: BCP-47 code of the detected language; None disables the denylist.
        rms: Root-mean-square energy of the source audio, if measured.
        no_speech_prob: Decoder no-speech probability, if the backend exposes it.
    """
    if not transcript or not transcript.strip():
        return False

    if no_speech_prob is not None and no_speech_prob >= NO_SPEECH_PROB_THRESHOLD:
        logger.info("Discarding STT result: no_speech_prob %.3f at or over threshold", no_speech_prob)
        return True

    if rms is not None and rms < SILENCE_RMS_THRESHOLD:
        logger.info("Discarding STT result: audio RMS %.5f below silence floor", rms)
        return True

    if is_audio_tag(transcript):
        logger.info("Discarding STT result: transcript is a bare audio tag")
        return True

    if is_known_artifact(transcript, language):
        logger.info("Discarding STT result: known %s silence artifact", language)
        return True

    return False
