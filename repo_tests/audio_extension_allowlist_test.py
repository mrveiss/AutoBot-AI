# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
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

from autobot_shared.paths import scrubbed_git_env

from repo_tests._reach import declare
from autobot_shared.ssot_constants import SecurityConstants

REPO_ROOT = Path(__file__).resolve().parents[1]

#: The canonical definition itself, which is the one literal that must exist.
_CANONICAL = Path("autobot_shared/ssot_constants.py")


def _literal_string_sets(source: str) -> list[set[str]] | None:
    """Every ``{...}`` set-of-string-literals in *source*.

    Parsed rather than pattern-matched. A regex over braces cannot tell a set
    from a dict and cannot tell this allowlist from the several legitimately
    different extension sets nearby — the video pipeline's, the broad binary set
    in ``file_categorization.py``, and ``EXTENSION_TO_FORMAT``, which is a dict.
    A first attempt at this test flagged all of them.

    Returns ``None`` when the source will not parse, so the caller can tell
    "no offending literal here" from "this file was never read" (#15826 review).
    Returning ``[]`` for both let an unparsed file satisfy the completion floor
    while contributing nothing — a skip counted as coverage, which is the exact
    defect this guard's floor exists to prevent.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Set) and node.elts:
            values = {e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)}
            if len(values) == len(node.elts):
                found.append(values)
    return found


def _tracked_python_files(root: Path = REPO_ROOT) -> list[Path]:
    """Tracked ``.py`` files under *root*.

    Takes a root so the declaration below can be driven against an empty
    directory by ``reach_declarations_test``; without that, nothing can prove
    the floor fires (#15826).
    """
    result = subprocess.run(  # nosec B603 B607
        ["git", "ls-files", "*.py"], cwd=root, capture_output=True, text=True, check=False, env=scrubbed_git_env()
    )
    return [root / line for line in result.stdout.splitlines() if line]


#: This sweep read every tracked file and asserted "no offenders" with no floor
#: at all: a `git ls-files` that returned nothing — wrong cwd, a broken env, a
#: partial checkout — passed having examined zero files (#15826).
REACH = declare(
    "audio-extension-allowlist",
    discover=_tracked_python_files,
    floor=1000,
    what="tracked python files",
)


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
    read = []
    unparsed = []
    for path in REACH.examined(REPO_ROOT):
        rel = path.relative_to(REPO_ROOT)
        if rel == _CANONICAL or rel.parts[0] == "repo_tests":
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        literals = _literal_string_sets(source)
        if literals is None:
            unparsed.append(str(rel))
            continue
        read.append(rel)
        if any(literal == canonical for literal in literals):
            offenders.append(str(rel))

    # Candidates are not coverage: the loop above skips anything it cannot read,
    # so without this the floor measured how many files were LISTED rather than
    # how many were actually inspected (#15826 review).
    # Truncated deliberately: a failure that lists every path buries the count
    # that identifies the cause. Ten names locate it; the number sizes it.
    assert not unparsed, (
        f"{len(unparsed)} tracked files could not be parsed, so this guard cannot speak for them "
        f"and they are not coverage. First: {unparsed[:10]}"
    )
    REACH.completed(read)

    assert not offenders, (
        "audio-extension allowlist written as a literal instead of imported from "
        f"SecurityConstants.ALLOWED_AUDIO_EXTENSIONS (#13512): {offenders}"
    )
