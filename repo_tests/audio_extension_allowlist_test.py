# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""The audio-extension allowlist has exactly one definition (#13512).

The set that decides which audio uploads are accepted was declared three times,
byte-identical, with nothing keeping the copies in step:

* ``transcriber/upload_security.py`` — the upload **security boundary**
* ``transcriber/routes/recordings.py`` — the route guard
* ``media/audio/ffmpeg_service.py`` — the processing guard

The third even carried the comment *"must match upload_security.py"*, which
states the invariant without enforcing it. Three copies of a security-relevant
allowlist drift independently, and the drift is silent in the dangerous
direction: a format added to the route guard alone is admitted by a validator
that was never taught to accept it.

These tests hold the consolidation in place. The last one is the important one —
it fails when a *fourth* literal appears, which is how the first three got here.
"""

from __future__ import annotations

import ast
import subprocess  # nosec B404  # fixed argv, no shell, no caller input
from pathlib import Path

from autobot_shared.ssot_constants import SecurityConstants

REPO_ROOT = Path(__file__).resolve().parents[1]

#: The canonical definition itself, which is the one literal that must exist.
_CANONICAL = Path("autobot_shared/ssot_constants.py")


def _literal_string_sets(source: str) -> list[set[str]]:
    """Every ``{...}`` set-of-string-literals in *source*.

    Parsed rather than pattern-matched. A regex over braces cannot tell a set
    from a dict and cannot tell this allowlist from the several legitimately
    different extension sets nearby — the video pipeline's, the broad binary set
    in ``file_categorization.py``, and ``EXTENSION_TO_FORMAT``, which is a dict.
    A first attempt at this test flagged all of them.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Set) and node.elts:
            values = {
                e.value
                for e in node.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            }
            if len(values) == len(node.elts):
                found.append(values)
    return found


def _tracked_python_files() -> list[Path]:
    result = subprocess.run(  # nosec B603 B607
        ["git", "ls-files", "*.py"], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )
    return [REPO_ROOT / line for line in result.stdout.splitlines() if line]


def test_canonical_set_holds_the_expected_formats():
    """Guards the contents, so consolidation cannot quietly change behaviour."""
    assert SecurityConstants.ALLOWED_AUDIO_EXTENSIONS == {
        ".wav",
        ".mp3",
        ".mp4",
        ".m4a",
        ".ogg",
        ".flac",
        ".webm",
    }


def test_all_three_guards_share_one_object():
    """Identity, not equality — equal-but-separate sets are what drifted before."""
    from media.audio.ffmpeg_service import ALLOWED_EXTENSIONS as ffmpeg_set
    from transcriber.routes.recordings import _ALLOWED_EXTENSIONS as route_set
    from transcriber.upload_security import ALLOWED_EXTENSIONS as security_set

    canonical = SecurityConstants.ALLOWED_AUDIO_EXTENSIONS
    assert security_set is canonical
    assert route_set is canonical
    assert ffmpeg_set is canonical


def test_ffmpeg_format_map_covers_exactly_the_allowlist():
    """A format the pipeline accepts but cannot convert would fail after upload.

    ``EXTENSION_TO_FORMAT`` is the ffmpeg ``-f`` mapping. If the allowlist grows
    without it, a file passes every guard and then breaks in processing; if the
    map grows without the allowlist, the entry is unreachable.
    """
    from media.audio.ffmpeg_service import EXTENSION_TO_FORMAT

    assert set(EXTENSION_TO_FORMAT) == SecurityConstants.ALLOWED_AUDIO_EXTENSIONS


def test_no_fourth_literal_copy_exists():
    """Fail when the allowlist is written as a literal anywhere but its home.

    This is the regression that matters. The three original copies were each
    added by someone reasonably writing the set they needed; nothing told them a
    canonical one existed. This does.

    Scoped to sets **equal** to the canonical one. Two nearby sets deliberately
    differ — ``api/knowledge.py`` accepts ``.mkv`` and
    ``knowledge/connectors/audio_connector.py`` omits ``.mp4``/``.webm`` — and
    reconciling those changes what the upload boundary admits, which is a
    decision rather than a refactor. Tracked separately; not failed here.
    """
    canonical = SecurityConstants.ALLOWED_AUDIO_EXTENSIONS
    offenders = []
    for path in _tracked_python_files():
        rel = path.relative_to(REPO_ROOT)
        if rel == _CANONICAL or rel.parts[0] == "repo_tests":
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if any(literal == canonical for literal in _literal_string_sets(source)):
            offenders.append(str(rel))

    assert not offenders, (
        "audio-extension allowlist written as a literal instead of imported from "
        f"SecurityConstants.ALLOWED_AUDIO_EXTENSIONS (#13512): {offenders}"
    )
