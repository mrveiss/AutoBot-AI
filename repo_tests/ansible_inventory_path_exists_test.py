# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15659: a shell script's `ansible -i <path>` must name a path that exists.

``sync-frontend.sh`` published the SLM frontend through
``ansible frontend -i ansible/inventory/production.yml -m copy ...``. That
inventory file was deleted from the repository in 2026-02 (#781 -- the same
commit that moved this very script into its current form without updating the
reference) and has not existed at that repo-root-relative path since, so the
command could not have resolved for as long as that has been true. Nothing
caught it because nothing checked it: the path is a plain string argument, not
an include Ansible itself validates ahead of a run, and no test read it.

#15643 is the same class of defect through a different mechanism -- a
``sys.path`` insert naming a directory without the packages it imports. This
module is the shell-side, ``-i``-argument-specific sibling: a script invoking
``ansible``/``ansible-playbook`` with a LITERAL (non-variable) ``-i <path>``
argument is one whose target is statically checkable, and #15659 asks for
exactly that check so a third stale repo-relative path does not survive
unnoticed the way this one did.

Resolution is relative to the invoking SCRIPT's own directory, not the repo
root or the process's cwd: every live invocation in this tree that uses a
literal path (as opposed to a `$VARIABLE` the script resolves itself, which
this module cannot check statically and does not try to) is preceded by a
`cd "$SCRIPT_DIR"` in the same script -- see e.g.
``autobot-slm-backend/ansible/deploy-autobot-native.sh``. That is also
precisely how ``sync-frontend.sh``'s defect is described: relative to a
directory that does not exist FROM THE SCRIPT'S OWN LOCATION.

Echoed hint text (`echo "... ansible-playbook ... -i inventory.yml"`) is
excluded on purpose: it tells an operator to `cd` somewhere first, and that
target directory is not statically inferrable the way the script's own
location is -- checking it needs a human, not this guard. One such hint was
found stale by inspection while writing this module
(``autobot-slm-backend/ansible/verify-grafana-config.sh``, fixed in the same
change) and is not re-litigated here.

Floors bind to the sweep's REACH, never to what it found: a sweep that
collapses to zero files, or a regex that stops matching any real invocation,
passes vacuously. ``test_the_detector_discriminates`` proves the extractor
still recognises both a resolvable and an unresolvable literal path.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

#: Directories excluded from the sweep: not part of this checkout's own tree,
#: or vendored. Matches slm_frontend_shell_publish_test.py's set.
_EXCLUDED_PARTS = {"node_modules", ".worktrees", ".claude", ".git"}

#: This repo carries ~210 tracked shell scripts. Well below this and the sweep
#: collapsed rather than the tree being clean.
_MIN_SHELL_FILES_SWEPT = 150

#: At least this many LIVE (non-echoed, literal-path) `ansible -i <path>`
#: invocations exist in the tree today (autobot-slm-backend/ansible/deploy*.sh
#: alone carries several). A floor of zero would mean the regex stopped
#: matching real invocations, not that every one uses a variable.
_MIN_LIVE_INVOCATIONS_FOUND = 3

#: `ansible`/`ansible-playbook ... -i <path>`, non-greedy so the FIRST `-i` on
#: the line is the one captured.
_ANSIBLE_DASH_I_RE = re.compile(r"\bansible(?:-playbook)?\b.*?-i\s+(\"[^\"]+\"|'[^']+'|\S+)")

#: Characters that make a token dynamic rather than a literal path: shell
#: variable/command substitution or a glob. Such a token cannot be resolved
#: statically and is skipped rather than guessed at.
_DYNAMIC_MARKERS = ("$", "`", "{{", "*")


def _unquote(token: str) -> str:
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ("'", '"'):
        return token[1:-1]
    return token


def _ansible_inventory_refs(text: str) -> list[str]:
    """Literal `-i <path>` arguments on live (non-comment, non-echoed) lines."""
    refs: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("echo"):
            continue
        match = _ANSIBLE_DASH_I_RE.search(stripped)
        if not match:
            continue
        literal = _unquote(match.group(1))
        if literal and not any(marker in literal for marker in _DYNAMIC_MARKERS):
            refs.append(literal)
    return refs


def _shell_files() -> list[Path]:
    """Every tracked-tree shell script, addressed relative to `_REPO_ROOT`.

    Exclusion is checked against the RELATIVE path: this checkout may itself
    live under a `.worktrees/<name>/` directory, so filtering on the absolute
    path's parts would exclude everything.
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
    assert len(_SWEPT) >= _MIN_SHELL_FILES_SWEPT, (
        f"swept only {len(_SWEPT)} shell files (floor {_MIN_SHELL_FILES_SWEPT}) -- the sweep "
        "collapsed rather than the tree being clean."
    )
    found = sum(len(_ansible_inventory_refs(path.read_text(encoding="utf-8", errors="replace"))) for path in _SWEPT)
    assert found >= _MIN_LIVE_INVOCATIONS_FOUND, (
        f"found only {found} literal `ansible -i <path>` invocation(s) (floor "
        f"{_MIN_LIVE_INVOCATIONS_FOUND}) -- the extractor regex stopped matching real "
        "invocations rather than every one having moved onto a variable."
    )


def test_every_literal_ansible_inventory_path_exists() -> None:
    offenders: dict[str, list[str]] = {}
    for path in _SWEPT:
        text = path.read_text(encoding="utf-8", errors="replace")
        for literal in _ansible_inventory_refs(text):
            resolved = (path.parent / literal).resolve()
            if not resolved.is_file():
                offenders.setdefault(str(path.relative_to(_REPO_ROOT)), []).append(literal)
    assert not offenders, (
        f"these scripts invoke ansible with a literal -i path that does not resolve, relative to "
        f"the script's own directory: {offenders}. That is #15659's defect: the command cannot "
        "have run successfully since the named path stopped existing."
    )


def test_the_detector_discriminates() -> None:
    """Contrast pair: a resolvable literal path is left alone, an unresolvable one is caught."""
    bad = "ansible-playbook -i ansible/inventory/production.yml playbooks/site.yml"
    good = "ansible-playbook -i inventory/production.yml playbooks/deploy-native-services.yml"
    dynamic = 'ansible all -i "$INVENTORY_FILE" -m ping'

    assert _ansible_inventory_refs(bad) == ["ansible/inventory/production.yml"]
    assert _ansible_inventory_refs(good) == ["inventory/production.yml"]
    assert _ansible_inventory_refs(dynamic) == [], "a $VARIABLE path must be skipped, not guessed at"

    # `bad`, resolved the way #15659's sync-frontend.sh actually was (relative
    # to the repo root): does not exist -- the exact defect this module exists
    # to catch.
    assert not (_REPO_ROOT / "ansible" / "inventory" / "production.yml").is_file()

    # `good`, resolved relative to the real script that uses it: does exist --
    # proving the detector does not flag a legitimate reference.
    real_caller = _REPO_ROOT / "autobot-slm-backend" / "ansible" / "deploy-autobot-native.sh"
    assert real_caller.is_file(), f"{real_caller} moved -- update this contrast pair"
    assert (real_caller.parent / "inventory" / "production.yml").is_file()
