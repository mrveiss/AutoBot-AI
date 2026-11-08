# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Node venv builders take the floor interpreter from ONE lookup (#20932).

`.python-version` declares the interpreter floor (#13842) and `autobot_shared`
refuses anything below it at import (#20903). A deploy builder that runs a bare
`python3 -m venv` builds on whatever the node ships; one that runs a hard-coded
`python3.14 -m venv` is right today and silently stale on the next floor bump.
Both are the same defect, so the guard rejects both in the deploy paths:

* Ansible: `{{ python_interpreter_binary }}` (roles/python_interpreter,
  tasks/resolve.yml derives it from `.python-version`).
* Shell / Python: `scripts/lib/python_floor.sh`.

A floor bump is then a one-file edit. Exceptions are listed in `_ALLOWED` with a
stated reason; an entry that no longer matches anything fails too, so the list
cannot rot into a blanket exemption.
"""

import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._comment_syntax import code_lines
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOT = repo_root()

#: Deploy and infrastructure paths a node venv is built from.
_SCAN_DIRS = ("autobot-slm-backend/ansible", "autobot-infrastructure", "autobot-backend/code_analysis")
_SCAN_FILES = ("install.sh",)
_SUFFIXES = {".yml", ".yaml", ".sh", ".py", ".j2"}
#: Test fixtures and the guards themselves describe the hazard, they do not build.
_SKIP_PARTS = ("node_modules", "__pycache__", ".worktrees")
_SKIP_PREFIXES = ("autobot-slm-backend/ansible/tests/",)

_HARDCODED = re.compile(
    r"\bpython3(?:\.\d+)?[\"']?\s+-m\s+venv\b"  # python3 -m venv / python3.14 -m venv
    r"|\bvenv_python:\s*[\"']?python3\.\d+\b"  # ensure_venv_version target literal
)

#: path -> why a hard-coded interpreter may stay. Reasons are checked for presence.
_ALLOWED = {
    "autobot-slm-backend/ansible/playbooks/deploy-native-services.yml": (
        "open PRs #20587 and #20777 edit this file; it joins #20932 after they land"
    ),
    "autobot-infrastructure/shared/scripts/setup-runner-python.sh": (
        "line 66 is an echo of the CI runner's venv recipe, not a builder"
    ),
    "autobot-slm-backend/ansible/playbooks/fix-backend-environment.yml": (
        "the only match is a prose hint in a failure message, not a builder"
    ),
}


def _in_scope(rel: str) -> bool:
    return (
        (rel.startswith(_SCAN_DIRS) or rel in _SCAN_FILES)
        and Path(rel).suffix in _SUFFIXES
        and not rel.startswith(_SKIP_PREFIXES)
        and not any(part in rel.split("/") for part in _SKIP_PARTS)
    )


def _scanned(root: Path) -> list[str]:
    """Tracked deploy-path files this guard reads."""
    try:
        listed = tracked_paths(root, *(f"*{s}" for s in sorted(_SUFFIXES)))
    except EmptyEnumeration:
        return []  # an empty tree: the reach's min_fraction raises the typed refusal instead
    return sorted(rel for rel in listed if _in_scope(rel))


def _independent_count(root: Path) -> int:
    """The same population counted from the unfiltered tracked list, so it cannot fail in lockstep."""
    try:
        return sum(1 for rel in tracked_paths(root) if _in_scope(rel))
    except EmptyEnumeration:
        return 0


REACH = declare(
    "venv-builders-use-floor-interpreter-sweep",
    discover=_scanned,
    min_fraction=0.95,
    reference=_independent_count,
    roots=_SCAN_DIRS + _SCAN_FILES,
    what="tracked deploy and infrastructure files searched for a hard-coded venv interpreter",
)


def _candidates():
    return [_ROOT / rel for rel in REACH.examined(_ROOT)]


def hardcoded_builders(files, root: Path = _ROOT) -> list[str]:
    """``path:line: text`` for every non-comment line naming a literal interpreter."""
    hits = []
    for path in files:
        rel = path.relative_to(root).as_posix()
        if path.suffix not in _SUFFIXES or any(part in rel.split("/") for part in _SKIP_PARTS):
            continue
        if rel.startswith(_SKIP_PREFIXES):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in code_lines(text, name=path):
            if _HARDCODED.search(line):
                hits.append(f"{rel}:{number}: {line.strip()}")
    return hits


def test_the_detector_sees_every_hardcoded_form():
    """Control strings: a detector that finds nothing proves nothing."""
    for bad in (
        "python3 -m venv ../venv",
        'cmd: "python3.14 -m venv {{ x }}/venv"',
        'virtualenv_command: "python3 -m venv"',
        "venv_python: python3.14",
        "  shell: python3.15 -m venv venv",
    ):
        assert _HARDCODED.search(bad), bad
    for good in (
        '"$PYTHON_BIN" -m venv venv',
        'cmd: "{{ python_interpreter_binary }} -m venv {{ x }}/venv"',
        'venv_python: "{{ python_interpreter_binary }}"',
        "${py_bin} -m venv ${REMOTE_BACKEND}/venv",
    ):
        assert not _HARDCODED.search(good), good


def test_no_deploy_builder_hardcodes_its_interpreter():
    by_file: dict[str, list[str]] = {}
    for hit in hardcoded_builders(_candidates()):
        by_file.setdefault(hit.split(":", 1)[0], []).append(hit)
    offenders = [h for rel, hits in by_file.items() if rel not in _ALLOWED for h in hits]
    assert not offenders, (
        "venv builders must use the floor interpreter, not a literal (#20932). Ansible: "
        "`{{ python_interpreter_binary }}`; shell/Python: scripts/lib/python_floor.sh.\n" + "\n".join(offenders)
    )


def test_every_allowlist_entry_still_matches_and_states_a_reason():
    """A stale entry is a blanket exemption waiting to happen."""
    matched = {hit.split(":", 1)[0] for hit in hardcoded_builders(_candidates())}
    for rel, reason in _ALLOWED.items():
        assert reason.strip(), f"{rel}: allowlist entry has no reason"
        assert (_ROOT / rel).is_file(), f"{rel}: allowlisted file no longer exists"
        assert rel in matched, f"{rel}: allowlisted but no longer hard-codes an interpreter; remove the entry"


def test_the_shared_sources_still_derive_from_python_version():
    """The one lookup each side relies on must itself read `.python-version`."""
    resolve = (_ROOT / "autobot-slm-backend/ansible/roles/python_interpreter/tasks/resolve.yml").read_text(
        encoding="utf-8"
    )
    assert ".python-version" in resolve and "python_interpreter_binary" in resolve
    helper = (_ROOT / "scripts/lib/python_floor.sh").read_text(encoding="utf-8")
    assert ".python-version" in helper


_INSTALL_SLM = "autobot-infrastructure/shared/scripts/install-slm.sh"


def _install_slm_builds_via_floor(text: str) -> bool:
    """True when the script sources the shared lookup and builds only through it."""
    code = "\n".join(line for _, line in code_lines(text, name=Path(_INSTALL_SLM)))
    return (
        "scripts/lib/python_floor.sh" in code
        and "python_floor_build_venv" in code
        and not _HARDCODED.search(code)
        and not re.search(r"\bpython3?\S*\s+-m\s+venv\b", code)
    )


def test_install_slm_builds_its_venv_only_through_the_floor_lookup():
    """#20932: install-slm.sh uses python_floor.sh, not a bare `python3 -m venv`."""
    text = (_ROOT / _INSTALL_SLM).read_text(encoding="utf-8")
    assert _install_slm_builds_via_floor(text)


def test_the_install_slm_check_fires_on_the_bare_form():
    """Control: the same check must reject the old line and a literal version."""
    bare = 'source "$PROJECT_ROOT/scripts/lib/python_floor.sh"\npython_floor_build_venv x\nsudo -u autobot python3 -m venv "$D/venv"\n'
    literal = 'source "$R/scripts/lib/python_floor.sh"\npython_floor_build_venv x\nsudo -u autobot python3.14 -m venv "$D/venv"\n'
    assert not _install_slm_builds_via_floor(bare)
    assert not _install_slm_builds_via_floor(literal)
