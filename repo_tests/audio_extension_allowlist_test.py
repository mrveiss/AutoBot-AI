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

#13615 then found two more copies that had already **drifted**, and those are
now derived too: ``api/knowledge.py`` and
``knowledge/connectors/audio_connector.py`` take named supersets from
``SecurityConstants`` instead of writing their own set. Neither reconciliation
changed what either path accepts — the deltas are pinned below, element for
element — because widening the upload boundary is an owner decision and not
something a de-duplication should smuggle in.

**Correcting a claim this file used to make.** The connector was described
here, and on #13615, as *omitting* ``.mp4``/``.webm``. That was true of the
name ``_AUDIO_EXTS`` and false of the connector: both of its gates tested
``_AUDIO_EXTS | _VIDEO_EXTS``, so it accepted a strict **superset** of the
canonical seven. The set that was read was not the set that ran.

These tests hold the consolidation in place. The sweep is the important one —
it fails when a *fourth* literal appears, which is how the first three got
here, and now also when a **near**-copy appears, which is how these two got
here. A near-copy is the dangerous shape: an exact duplicate is harmless until
one side moves, whereas a set that differs by one container is already a
disagreement about what the system accepts.
"""

from __future__ import annotations

import ast
import subprocess  # nosec B404  # fixed argv, no shell, no caller input
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from autobot_shared.paths import scrubbed_git_env
from autobot_shared.ssot_constants import SecurityConstants

REPO_ROOT = repo_root()

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


def _is_near_copy(values: set[str], canonical: set[str]) -> bool:
    """True when *values* is recognisably the audio allowlist, edited.

    Thresholds are measured against this tree rather than chosen. Every set of
    string literals sharing three or more members with the canonical seven was
    enumerated (five of them); the overlap/extras distribution is:

    ====================================  =======  ======
    site                                  overlap  extras
    ====================================  =======  ======
    ssot_constants.py (the canonical one)       7       0
    api/knowledge.py                            7       1
    audio_connector.py (_AUDIO_EXTS)            5       0
    utils/file_categorization.py                5      26
    ====================================  =======  ======

    ``file_categorization.py``'s set is a broad binary-file classifier that
    happens to include media types; #13615 names it out of scope explicitly.
    26 extras against a limit of 2 is a wide margin, not a close call, which is
    why the rule can afford to be this simple.

    Requiring every member to look like an extension keeps the rule from
    reaching sets of unrelated short strings that happen to overlap.
    """
    if not values or values == canonical:
        return False
    if not all(v.startswith(".") and 2 <= len(v) <= 6 for v in values):
        return False
    return len(values & canonical) >= 5 and len(values - canonical) <= 2


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
#: Ratcheted from 1000 (18% of the live population) under #15928. A floor that
#: low fires only against a tree that has almost entirely stopped being read;
#: the loss that actually happens is a narrowed glob or a moved directory,
#: worth hundreds of files, and it cleared 1000 comfortably.
#:
#: `growth` is a maintenance-frequency choice, not a safety one: safety comes
#: from the floor sitting near the population, and the band only decides how
#: often the ratchet asks for a deliberate line. 250 absorbs ordinary churn in
#: both directions -- files are added and deleted every week -- while staying
#: far below the size of any subtree whose loss this exists to catch.
#:
#: `skips=300` is **measured, not estimated**: the pre-push hook reported
#: `completed 5337` against `discover 5599`, a gap of 262, rounded up for churn.
#: `growth=400` is the maintenance interval -- roughly a week of this repo's
#: growth -- and is the only number here chosen by judgement rather than
#: measurement. Splitting them is what makes that sentence possible; with one
#: band nobody could say which part was which.
#:
#: Ratcheted 5100 -> 5450 (#16702): the 2d batch vehicle combines 14
#: independently-reviewed PRs' new/moved files onto one tree, and that alone
#: closed most of the old floor's 700-file runway. `git ls-files "*.py"`
#: (this declaration's own `discover`) measures 5824 on the vehicle branch at
#: this commit -- not estimated, not read off a CI log.
#:
#: 5450, not 5824: the guard's `completed()` bound is a hard floor with no
#: skips/growth allowance (unlike `verify_floor`'s examined-vs-floor check),
#: and the pre-push hook's own actual run of THIS guard reported
#: `completed 5497` against that same 5824 discovered -- 327 files short.
#: Corrected (e5 review): that gap is NOT unparseable files -- `test_no_
#: fourth_literal_copy_exists`'s own loop `continue`s past the canonical
#: file and everything under `repo_tests/` by design before it ever reads a
#: file, which is most of the gap; a genuinely unparseable file fails the
#: test outright via its own `assert not unparsed`, not a silent skip.
#: Setting floor above 5497 would fail every honest run outright, which the
#: first version of this fix did. 5450 leaves a small margin below the
#: measured 5497 for ordinary population fluctuation while using most of
#: the slack `verify_floor` allows (5824-5450=374, within
#: skips=300+growth=400=700). `skips`/`growth` themselves are unchanged --
#: #16724 tracks re-measuring this floor from CI's own log post-merge.
# #17331/#17332 branch: this branch had pinned 5700 and ADOPTED main's 5752 on
# rebase, rather than re-deriving a competing number for one measurement.
# Re-measured here to confirm 5752 actually holds with this branch's files:
#   population = 6154, gap 402 against the 700 allowance      -- OK
#   completed  = 5767, so the floor has 15 files of headroom  -- OK, and thin
# 15 is the number to watch. This declaration's loop skips `repo_tests` outright
# (see the `rel.parts[0] == "repo_tests"` continue below), so `completed` FALLS
# as guards are added -- five sessions added some tonight -- while population
# rises. The two bounds close from opposite directions and only the gap one is
# ever measured. Not re-pinning it here: main's value holds, and one branch
# unilaterally widening a floor another just set is how two correct numbers
# become a conflict. Recorded on #17142 instead.
REACH = declare(
    "audio-extension-allowlist",
    discover=_tracked_python_files,
    # Re-pinned 5450 -> 5752 (#17317), held at 5757 on the parent branch and at
    # 5764 here (#17305/#17306, #17307/#17308): one re-pin measured on three
    # trees a merge apart. #17317 read 6152 tracked python files, the parent
    # branch 6159, and this stack 6166 -- its fourteen new modules. All three
    # are legal in a 700-wide window (skips=300 + growth=400); the highest is
    # kept because a floor only ever ratchets up, asserting the sweep reached
    # MORE, which is the strict direction for a reach floor.
    floor=5764,
    growth=400,
    skips=300,
    what="tracked python files",
)


def test_canonical_set_holds_the_expected_formats():
    """Guards the contents, so consolidation cannot quietly change behaviour.

    Written out element for element rather than recomputed from the constant,
    so this disagrees with it if either moves. The last three are the formats
    the KB route and the connector already admitted before #13615 collapsed
    the three sets into one; no format was lost in the collapse.
    """
    assert SecurityConstants.ALLOWED_AUDIO_EXTENSIONS == {
        ".wav",
        ".mp3",
        ".mp4",
        ".m4a",
        ".ogg",
        ".flac",
        ".webm",
        ".mkv",
        ".avi",
        ".mov",
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

    Two kinds of offender, because #13615 showed the second is the one that
    bites. An **exact** copy is a set equal to the canonical one: harmless
    today, a disagreement the moment either side is edited. A **near** copy is
    a set that is mostly the canonical one and not quite — which is what
    ``api/knowledge.py`` and the audio connector had become, differing from the
    boundary by one and three containers respectively with nothing recording
    that the difference was meant.

    Both now derive from ``SecurityConstants``, so the sweep covers them rather
    than exempting them. ``_is_near_copy``'s thresholds are measured against
    this tree, not guessed — see its docstring.
    """
    canonical = SecurityConstants.ALLOWED_AUDIO_EXTENSIONS
    offenders = []
    near = []
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
            offenders.append(f"{rel} (exact copy)")
        for literal in literals:
            if _is_near_copy(literal, canonical):
                near.append(f"{rel} -- extra {sorted(literal - canonical)}, missing {sorted(canonical - literal)}")

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

    assert not near, (
        "a set that is nearly the audio-extension allowlist, written as a literal "
        "(#13615). This is a drifted copy: say what the difference is by deriving "
        "a named superset/subset in SecurityConstants, so the delta is readable "
        "and moves with the boundary.\n" + "\n".join(near)
    )


# ---------------------------------------------------------------------------
# #13615 — the two copies that had already drifted, now on the one set
# ---------------------------------------------------------------------------


def test_every_gate_shares_the_one_canonical_object():
    """Identity, not equality, on all five gates.

    Equality would pass for a re-written literal that happens to agree today,
    which is the state #13615 found: copies that matched once and no longer
    did. `is` can only hold if the call site took the object.
    """
    import sys

    sys.path.insert(0, str(REPO_ROOT / "autobot-backend"))
    from api.knowledge import _AUDIO_ALLOWED_EXTS
    from knowledge.connectors.audio_connector import _MEDIA_EXTS
    from media.audio.ffmpeg_service import ALLOWED_EXTENSIONS as _FFMPEG_EXTS
    from transcriber.routes.recordings import _ALLOWED_EXTENSIONS as _ROUTE_EXTS
    from transcriber.upload_security import ALLOWED_EXTENSIONS as _UPLOAD_EXTS

    canonical = SecurityConstants.ALLOWED_AUDIO_EXTENSIONS
    gates = (
        ("api.knowledge", _AUDIO_ALLOWED_EXTS),
        ("audio_connector", _MEDIA_EXTS),
        ("ffmpeg_service", _FFMPEG_EXTS),
        ("routes.recordings", _ROUTE_EXTS),
        ("upload_security", _UPLOAD_EXTS),
    )
    # Collected rather than asserted inside the loop: a loop whose only body is
    # the assertion becomes an empty `for` when guard_reach_meta strips the
    # assertion to check this guard still fails without it, and an
    # IndentationError is not the failure that test is looking for. Reporting
    # every mismatching gate instead of the first is the better verdict anyway.
    mismatched = [name for name, gate in gates if gate is not canonical]
    assert not mismatched, f"these gates do not share the canonical object: {mismatched}"


def test_there_is_exactly_one_named_allowlist():
    """The derived supersets are gone, not renamed.

    `KB_AUDIO_INGEST_EXTENSIONS` and `MEDIA_CONNECTOR_EXTENSIONS` expressed the
    drift as a requirement. Nothing stated a reason for either delta, and the
    pair was incoherent -- the KB endpoint rejected `.avi` while the connector
    it feeds accepted it. Three sets differing for no reason are three copies
    with extra steps (owner, 2026-10-05).
    """
    extra = [n for n in ("KB_AUDIO_INGEST_EXTENSIONS", "MEDIA_CONNECTOR_EXTENSIONS") if hasattr(SecurityConstants, n)]
    assert not extra, f"a per-call-site allowlist came back: {extra}. One set, or state the capability reason."


def test_the_transcriber_widening_is_deliberate_and_visible():
    """The collapse ADMITS three containers the transcriber used to refuse.

    Recorded as a test rather than a comment because it is the one behavioural
    consequence of #13615: `upload_security` gates on extension alone, with no
    magic-byte check, so this set is the only thing standing between a user
    string and a file on disk. If these three are ever meant to be refused
    there, this test is where that decision gets made -- visibly.
    """
    widened = {".mkv", ".avi", ".mov"}
    assert widened < SecurityConstants.ALLOWED_AUDIO_EXTENSIONS
    # Containers already demuxed by ffmpeg and already identified by magic
    # bytes in media/video/pipeline.py, and no more complex than .mp4/.webm,
    # which every one of these gates has always admitted.
    assert {".mp4", ".webm"} < SecurityConstants.ALLOWED_AUDIO_EXTENSIONS


def test_the_near_copy_detector_finds_the_shapes_it_is_for():
    """Positive controls, one per shape — the sweep is clean, so it proves nothing alone.

    A control witnesses only the form it is written in, so there is one for
    each direction a copy can drift: wider, narrower, and both at once.
    """
    canonical = SecurityConstants.ALLOWED_AUDIO_EXTENSIONS

    # The drifted shapes #13615 found were `canonical | {.mkv}` and
    # `canonical | {.mkv,.avi,.mov}`. Those three are now MEMBERS of the one
    # set, so re-using them here would compare the set with itself and the
    # controls would silently stop witnessing anything. Formats outside the
    # allowlist stand in for the same four directions of drift.
    assert _is_near_copy(canonical | {".wma"}, canonical), "one extra: the wider shape"
    assert _is_near_copy(canonical - {".mp4", ".webm"}, canonical), "two missing: the narrower shape"
    assert _is_near_copy((canonical - {".webm"}) | {".wma"}, canonical), "drifted both ways"
    assert _is_near_copy(canonical | {".wma", ".aac"}, canonical), "two extras is still a copy"


def test_the_near_copy_detector_leaves_the_legitimate_sets_alone():
    """Negative controls, including the real set that is closest to tripping it.

    ``utils/file_categorization.py``'s binary-extension set shares five members
    with the allowlist and is explicitly out of scope on #13615. If the rule
    ever flags it, the rule is wrong — not that file.
    """
    canonical = SecurityConstants.ALLOWED_AUDIO_EXTENSIONS

    assert not _is_near_copy(canonical, canonical), "the canonical set is not a copy of itself"
    assert not _is_near_copy(set(), canonical)
    file_categorization_shape = {".mp3", ".mp4", ".ogg", ".wav", ".webm"} | {f".x{i}" for i in range(26)}
    assert not _is_near_copy(file_categorization_shape, canonical), "26 extras is a different concern"
    assert not _is_near_copy({".py", ".ts", ".vue"}, canonical)
    assert not _is_near_copy({"wav", "mp3", "mp4", "m4a", "ogg"}, canonical), "no leading dot: not extensions"


def test_the_detector_reads_set_literals_and_not_the_text_around_them():
    """The trap: a guard that greps is satisfied by the prose describing the bug.

    Every string this guard looks for appears in the fixture below — in a
    docstring, a ``#`` comment and a string constant — and the fixture contains
    no set literal at all. ``_literal_string_sets`` must return an empty list,
    not a match. The companion assertion checks that an honest literal in the
    same file *is* still found, so an empty result cannot be mistaken for a
    detector that stopped working.
    """
    prose_only = '''
"""Historically this module declared {".wav", ".mp3", ".mp4"} inline."""
# allowed: ".wav", ".mp3", ".mp4", ".m4a", ".ogg", ".flac", ".webm"
NOTE = '{".wav", ".mp3", ".mp4", ".m4a", ".ogg", ".flac", ".webm"}'
ALLOWED = SecurityConstants.ALLOWED_AUDIO_EXTENSIONS
'''
    assert prose_only.count(".webm") == 2, "fixture lost its strings; the pass below would be empty"
    assert prose_only.count(".mp4") == 3
    assert _literal_string_sets(prose_only) == []

    with_literal = prose_only + '\nOTHER = {".wav", ".mp3", ".mp4", ".m4a", ".ogg", ".flac", ".webm"}\n'
    found = _literal_string_sets(with_literal)
    # Compared against what the FIXTURE wrote, not against the live constant.
    # This test is about the detector; `test_canonical_set_holds_the_expected_formats`
    # owns the contents. Coupling the two made editing the allowlist fail here,
    # which reads as "the detector broke" when nothing about it changed.
    assert found == [{".wav", ".mp3", ".mp4", ".m4a", ".ogg", ".flac", ".webm"}], f"detector went blind: {found}"


def test_unparseable_source_is_distinguished_from_clean_source():
    """``None`` means "not read"; ``[]`` means "read, nothing found"."""
    assert _literal_string_sets("def f(:\n") is None
    assert _literal_string_sets("x = 1\n") == []
