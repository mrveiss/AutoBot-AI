# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15650, #15689: the shell path builds and publishes the SLM frontend the same way Ansible does.

``repo_tests/slm_frontend_staged_publish_15557_test.py`` and
``repo_tests/slm_frontend_atomic_publish_15610_test.py`` sweep Ansible YAML only.
A shell script was outside that reach, so ``bootstrap-slm.sh`` kept the
pre-#15430 shape long after every Ansible entry point was fixed: it built with
a plain ``npm run build`` (bakes the wrong ``VITE_API_URL`` in, #9563/#9710/
#10435), downgraded a build failure to a warning and continued (`` || warn
... continuing``, the #15462 outage in miniature), and published by
symlinking the served ``current`` straight at ``dist`` -- never a fresh
per-build directory, never gated on the build having produced anything.
``sync-frontend.sh`` carried the same first defect plus a third: it published
through an ``ansible ... -i ansible/inventory/production.yml`` inventory path
deleted from this repository in 2026-02 (#781) that could not have resolved
since (see ``repo_tests/ansible_inventory_path_exists_test.py`` for that half).

Both are fixed by installing and running the SAME shell helper --
``autobot-infrastructure/autobot-slm-frontend/templates/build-publish-slm-frontend.sh``
-- rather than each carrying its own copy of the build:slm / atomic-flip idiom.
This module asserts three things that together make a silent divergence back
to the pre-fix shape impossible:

1. both known shell entry points delegate to the shared helper (a real
   ``./build-publish.sh`` invocation), rather than building or publishing the
   SLM frontend inline;
2. the shared helper itself carries every part of the fix -- ``build:slm``,
   a hard abort on a nonzero build rc, an index.html proof, and the
   ``.current.next`` / ``mv -T`` atomic-flip idiom, never a direct
   ``ln -sfn dist current``;
3. **no** shell script in the tree still builds the SLM frontend inline or
   publishes it unstaged -- the catcher for a fifth entry point (or a
   regression in one of the first two) arriving with a fresh copy.

Floors bind to the sweep's REACH (how many ``*.sh`` files were parsed), never
to what it found -- a sweep that collapses to zero files passes vacuously, and
``test_the_detectors_discriminate`` re-runs both detectors over the pre-fix
``bootstrap-slm.sh`` text so a clean sweep means something rather than meaning
the detectors match nothing.

Lives in ``repo_tests/`` for the same reason its Ansible-side siblings do:
CI's shard command passes an explicit path list and neither
``autobot-infrastructure/`` nor the repo root script is on it.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator

_REPO_ROOT = Path(__file__).resolve().parents[1]

_SHARED_HELPER = (
    _REPO_ROOT / "autobot-infrastructure" / "autobot-slm-frontend" / "templates" / "build-publish-slm-frontend.sh"
)

#: Every shell entry point that builds/publishes the SLM frontend, as named by
#: #15650, #15689 and #15659.
_ENTRY_POINTS: dict[str, Path] = {
    "bootstrap-slm": _REPO_ROOT / "autobot-infrastructure" / "autobot-slm-backend" / "scripts" / "bootstrap-slm.sh",
    "sync-frontend": _REPO_ROOT / "sync-frontend.sh",
}

#: The vacuity floor for _ENTRY_POINTS. A set that has shrunk means a caller
#: was dropped or renamed without this guard being told, not that the defect
#: is gone.
_EXPECTED_ENTRY_POINTS = 2

#: Directories excluded from the repo-wide shell sweep: not part of this
#: checkout's own tree, or vendored.
_EXCLUDED_PARTS = {"node_modules", ".worktrees", ".claude", ".git"}

#: This repo carries ~210 tracked shell scripts. Well below this and the sweep
#: collapsed (a moved directory, a broken glob) rather than the tree being
#: clean.
_MIN_SHELL_FILES_SWEPT = 150

#: #15718: three more sites carry the SAME wrong-build-target defect this
#: module's sweep is built to catch, discovered BY widening that sweep to the
#: whole tree. They are out of scope for #15650/#15689/#15659 (which named
#: `bootstrap-slm.sh` and `sync-frontend.sh` specifically) and the two
#: `bulletproof-frontend` scripts publish through a wholly separate mechanism
#: (`/opt/autobot/src/autobot-slm-frontend{,-primary,-staging}`) that #15718
#: has to establish is even still called before anyone touches it -- the same
#: "never delete, never assume" question #15659 answered for `sync-frontend.sh`.
#: Listed explicitly, not silently swallowed: closing #15718 must remove
#: entries here, and this list growing on its own is itself a finding.
_GRANDFATHERED_OFFENDERS = frozenset(
    {
        "run_agent.sh",
        "autobot-infrastructure/shared/scripts/bulletproof-frontend/zero-downtime-update.sh",
        "autobot-infrastructure/shared/scripts/bulletproof-frontend/deploy-bulletproof-frontend.sh",
    }
)

#: The marker that scopes both sweep detectors to the SLM frontend
#: specifically -- `autobot-frontend` (the user-facing UI) carries the same
#: unstaged shape and is tracked separately (see
#: `build_publish_slm_frontend.yml`'s own module docstring); this string is
#: not a substring of that name, so the two never collide.
_SLM_FRONTEND_MARKER = "autobot-slm-frontend"

#: `npm run build` without the `:slm` suffix. The lookahead means
#: `npm run build:slm` itself never matches -- `\b` sits between the "d" of
#: "build" and the ":", so a plain negative string check would miscount.
_WRONG_BUILD_RE = re.compile(r"\bnpm run build\b(?!:slm)")

#: A build command whose failure is downgraded to a warning and continues,
#: rather than aborting -- the exact #15430/#15462 shape.
_WARN_CONTINUE_RE = re.compile(r"\|\|\s*(warn|true)\b")

#: `ln -sfn dist current` -- pointing the served pointer straight at a fixed
#: `dist/` name rather than a fresh per-build directory. The pre-#15610 shape,
#: in shell.
_UNSTAGED_PUBLISH_RE = re.compile(r"\bln\s+-sfn\s+dist\s+current\b")

#: The historical `bootstrap-slm.sh` shape (pre-#15650/#15689), kept ONLY as
#: the contrast-mutation input for the detectors below -- never as a value
#: under test. Verbatim from the file before this fix, with just enough
#: surrounding context (the REMOTE_FRONTEND definition) for the SLM-frontend
#: marker check to see it, the same way the real file does.
_HISTORICAL_BOOTSTRAP_FRONTEND_SETUP = """
REMOTE_BASE="/opt/autobot"
REMOTE_FRONTEND="${REMOTE_BASE}/autobot-slm-frontend"

frontend_setup() {
    info "Building frontend..."
    remote_exec_sudo "cd ${REMOTE_FRONTEND} && npm run build --silent 2>/dev/null" || \\
        warn "Frontend build may have warnings, continuing..."
    remote_exec_sudo "cd ${REMOTE_FRONTEND} && ln -sfn dist current"
    success "Frontend built"
}
"""


def _logical_lines(text: str) -> list[str]:
    """Join `\\`-continued shell lines so a detector sees one logical command.

    `bootstrap-slm.sh`'s historical build-failure downgrade split `|| warn`
    onto the line after the build command; scanning physical lines alone
    would never see the `||` and the word on the same line.
    """
    logical: list[str] = []
    buf = ""
    for line in text.splitlines():
        combined = f"{buf} {line.strip()}" if buf else line
        if combined.rstrip().endswith("\\"):
            buf = combined.rstrip()[:-1].rstrip()
            continue
        buf = ""
        logical.append(combined)
    if buf:
        logical.append(buf)
    return logical


def _non_comment_logical_lines(text: str) -> Iterator[str]:
    for line in _logical_lines(text):
        if line.strip().startswith("#"):
            continue
        yield line


def _builds_slm_frontend_wrong(text: str) -> list[str]:
    """Command lines that build the SLM frontend with a plain `npm run build`."""
    if _SLM_FRONTEND_MARKER not in text:
        return []
    return [line.strip() for line in _non_comment_logical_lines(text) if _WRONG_BUILD_RE.search(line)]


def _downgrades_build_failure(text: str) -> list[str]:
    """Command lines where a build's failure is warned about and continued past."""
    if _SLM_FRONTEND_MARKER not in text:
        return []
    hits = []
    for line in _non_comment_logical_lines(text):
        if ("npm run build" in line or "vite build" in line) and _WARN_CONTINUE_RE.search(line):
            hits.append(line.strip())
    return hits


def _publishes_unstaged(text: str) -> list[str]:
    """Command lines that flip the served pointer straight at a fixed `dist/`."""
    if _SLM_FRONTEND_MARKER not in text:
        return []
    return [line.strip() for line in _non_comment_logical_lines(text) if _UNSTAGED_PUBLISH_RE.search(line)]


def _shell_files() -> list[Path]:
    """Every tracked-tree shell script, addressed relative to `_REPO_ROOT`.

    Exclusion is checked against the RELATIVE path, not the absolute one: this
    checkout itself may live under a `.worktrees/<name>/` directory (every
    session's does), so filtering on `path.parts` directly would match that
    ancestor segment and exclude everything -- the #15650 review found exactly
    this bug in an earlier draft of this sweep.
    """
    kept: list[Path] = []
    for path in _REPO_ROOT.rglob("*.sh"):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(_REPO_ROOT).parts
        if _EXCLUDED_PARTS.intersection(rel_parts):
            continue
        if any(part.startswith("venv") or part.endswith(".venv") for part in rel_parts):
            continue
        kept.append(path)
    return sorted(kept)


_SWEPT = _shell_files()


def test_the_sweep_is_not_vacuous() -> None:
    """Floors under every count this module draws a conclusion from."""
    assert len(_ENTRY_POINTS) == _EXPECTED_ENTRY_POINTS, (
        f"expected {_EXPECTED_ENTRY_POINTS} shell SLM-frontend entry points, the set names "
        f"{len(_ENTRY_POINTS)}. Shrinking the set is how a caller stops being checked."
    )
    missing = [name for name, path in _ENTRY_POINTS.items() if not path.is_file()]
    assert not missing, f"entry points moved or were renamed: {missing}"
    assert _SHARED_HELPER.is_file(), f"{_SHARED_HELPER} is missing -- nothing to delegate to"
    assert len(_SWEPT) >= _MIN_SHELL_FILES_SWEPT, (
        f"swept only {len(_SWEPT)} shell files (floor {_MIN_SHELL_FILES_SWEPT}) -- the sweep "
        "collapsed rather than the tree being clean."
    )
    still_present = sorted(
        str(p.relative_to(_REPO_ROOT)) for p in _SWEPT if str(p.relative_to(_REPO_ROOT)) in _GRANDFATHERED_OFFENDERS
    )
    assert len(still_present) == len(_GRANDFATHERED_OFFENDERS), (
        f"only found {still_present} of the #15718 grandfathered offenders -- one moved or was "
        "removed; update this module's exclusion list rather than let it point at nothing."
    )


def test_every_entry_point_delegates_to_the_shared_helper() -> None:
    for name, path in _ENTRY_POINTS.items():
        text = path.read_text(encoding="utf-8")
        assert "build-publish.sh" in text, (
            f"{path.relative_to(_REPO_ROOT)} does not invoke build-publish.sh. Building or "
            "publishing the SLM frontend any other way risks the #15430/#15462/#15557/#15610 "
            f"outage this helper exists to prevent (entry point: {name})."
        )


def test_no_entry_point_builds_or_publishes_inline() -> None:
    for name, path in _ENTRY_POINTS.items():
        text = path.read_text(encoding="utf-8")
        wrong_build = _builds_slm_frontend_wrong(text)
        warned_through = _downgrades_build_failure(text)
        unstaged = _publishes_unstaged(text)
        assert not wrong_build, f"{name} builds the SLM frontend inline: {wrong_build}"
        assert not warned_through, f"{name} downgrades a build failure to a warning: {warned_through}"
        assert not unstaged, f"{name} publishes into a fixed, unstaged path: {unstaged}"


def test_the_shared_helper_carries_every_part_of_the_fix() -> None:
    text = _SHARED_HELPER.read_text(encoding="utf-8")
    assert "npm run build:slm" in text, f"{_SHARED_HELPER} does not build with build:slm"
    assert not _builds_slm_frontend_wrong(
        f"{_SLM_FRONTEND_MARKER}\n{text}"
    ), "the shared helper contains a plain `npm run build` invocation alongside build:slm"
    assert re.search(r"exit 1", text), f"{_SHARED_HELPER} has no hard-abort path for a failed build"
    assert re.search(
        r'-s\s+"\$\{?build_dir\}?/index\.html"', text
    ), f"{_SHARED_HELPER} does not prove the build produced a non-empty index.html"
    assert re.search(r"ln\s+-sfn\s+\S+\s+\.current\.next", text) and re.search(
        r"mv\s+-T\s+\.current\.next\s+current", text
    ), (
        f"{_SHARED_HELPER} does not stage the flip through `.current.next` and `mv -T` -- "
        "`ln -sfn <target> current` unlinks the name before recreating it, which is the window "
        "#15610 removed."
    )
    assert not _UNSTAGED_PUBLISH_RE.search(text), f"{_SHARED_HELPER} still flips `current` straight at a fixed `dist/`"


def test_no_shell_script_builds_or_publishes_the_slm_frontend_inline() -> None:
    """The catcher for a NEW entry point (or a regression) copying the old shape."""
    offenders: dict[str, list[str]] = {}
    for path in _SWEPT:
        rel = str(path.relative_to(_REPO_ROOT))
        if path.resolve() == _SHARED_HELPER.resolve() or rel in _GRANDFATHERED_OFFENDERS:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        found = _builds_slm_frontend_wrong(text) + _downgrades_build_failure(text) + _publishes_unstaged(text)
        if found:
            offenders[rel] = found
    assert not offenders, (
        f"these shell scripts build or publish the SLM frontend outside the shared helper: "
        f"{offenders}. Either route them through {_SHARED_HELPER.relative_to(_REPO_ROOT)}, or file "
        "and grandfather them the way #15718 was."
    )


def test_the_detectors_discriminate() -> None:
    """Contrast mutation: the pre-fix bootstrap-slm.sh shape must still be flagged.

    Without this, `test_no_shell_script_builds_or_publishes_the_slm_frontend_inline`
    passing would be indistinguishable from detectors that match nothing at all.
    """
    wrong_build = _builds_slm_frontend_wrong(_HISTORICAL_BOOTSTRAP_FRONTEND_SETUP)
    warned_through = _downgrades_build_failure(_HISTORICAL_BOOTSTRAP_FRONTEND_SETUP)
    unstaged = _publishes_unstaged(_HISTORICAL_BOOTSTRAP_FRONTEND_SETUP)
    assert wrong_build, "the wrong-build detector no longer recognises the pre-#15650 shape"
    assert warned_through, "the warn-and-continue detector no longer recognises the pre-#15650 shape"
    assert unstaged, "the unstaged-publish detector no longer recognises the pre-#15610-in-shell shape"
