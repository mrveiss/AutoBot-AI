# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The install root is written once, as `autobot.base_dir` (#15632; #18587 part 1, #18880).

`/opt/autobot` stays the folder AutoBot deploys to; the point is one definition. The literal
elsewhere in Ansible code is frozen per file in opt_autobot_literal_ratchet_18880_baseline.py
and only goes down. install.sh's AUTOBOT_BASE must equal it: `-e` cannot set one key of the
`autobot:` mapping without replacing the mapping, and that mapping must stay template-free
for controller plays (#15731), so equality is pinned here instead of passed at run time.
"""

from __future__ import annotations

import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare
from repo_tests.opt_autobot_literal_ratchet_18880_baseline import BASELINE

from tools.lint._comment_syntax import code_lines
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOT = repo_root()
_ANSIBLE = "autobot-slm-backend/ansible"
_DEFINITION_FILE = f"{_ANSIBLE}/inventory/group_vars/all.yml"
_DEFINITION = 'base_dir: "/opt/autobot"'


def _ansible_files(root: Path) -> list[str]:
    try:
        return tracked_paths(root, _ANSIBLE)
    except EmptyEnumeration:
        return []


REACH = declare(
    "opt-autobot-literal-ratchet-18880",
    discover=_ansible_files,
    floor=458,  # mid-window: population 478, window (438, 478)
    growth=40,
    what="tracked ansible files",
    roots=(_ANSIBLE,),
)


def literal_counts(files: dict[str, str]) -> dict[str, int]:
    """{path: code occurrences of /opt/autobot}, the one definition excluded, zeros dropped."""
    counts = {}
    for path, text in files.items():
        lines = code_lines(text, name=path, strip_trailing=True)
        n = sum(
            line.text.count("/opt/autobot")
            for line in lines
            if not (path == _DEFINITION_FILE and line.text.strip() == _DEFINITION)
        )
        if n:
            counts[path] = n
    return counts


def _live() -> dict[str, int]:
    files = {}
    for rel in REACH.examined(_ROOT):
        try:
            files[rel] = (_ROOT / rel).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue  # binary assets carry no path literal
    return literal_counts(files)


def test_the_literal_count_only_goes_down() -> None:
    live = _live()
    grown = {p: (BASELINE.get(p, 0), n) for p, n in live.items() if n > BASELINE.get(p, 0)}
    assert not grown, f"new /opt/autobot literals -- use {{{{ autobot.base_dir }}}}: {grown}"
    shrunk = {p: (b, live.get(p, 0)) for p, b in BASELINE.items() if live.get(p, 0) < b}
    assert not shrunk, f"literals removed -- lower BASELINE to match, so the slack is not re-spent: {shrunk}"


def _group_vars_all() -> dict:
    import yaml

    return yaml.safe_load((_ROOT / _DEFINITION_FILE).read_text(encoding="utf-8"))


def test_the_install_root_is_defined_once() -> None:
    """autobot.base_dir is the one root; a second name for it (the retired top-level
    autobot_base_dir) must not come back."""
    assert _group_vars_all()["autobot"]["base_dir"] == "/opt/autobot"
    seconds = [
        rel
        for rel in REACH.examined(_ROOT)
        if rel.endswith((".yml", ".yaml"))
        and re.search(r"^\s*autobot_base_dir\s*:", (_ROOT / rel).read_text(encoding="utf-8"), re.M)
    ]
    assert not seconds, f"a second install-root variable: {seconds}"


def test_install_sh_and_ansible_agree_on_the_root() -> None:
    install = (_ROOT / "install.sh").read_text(encoding="utf-8")
    m = re.search(r'^readonly AUTOBOT_BASE="([^"]+)"', install, re.M)
    assert m, "install.sh no longer declares AUTOBOT_BASE"
    root = _group_vars_all()["autobot"]["base_dir"]
    assert m.group(1) == root, (
        f"install.sh AUTOBOT_BASE={m.group(1)!r} != autobot.base_dir={root!r} in {_DEFINITION_FILE}; "
        "change both together"
    )


def test_no_role_default_or_group_var_restates_the_root() -> None:
    """#18880 AC: every role default / vars / group_vars path under the root derives from it."""
    leftover = [p for p in BASELINE if re.search(r"/(defaults|vars|group_vars)/", p)]
    assert not leftover, leftover


def test_the_counter_sees_code_and_ignores_comments_and_the_definition() -> None:
    files = {
        _DEFINITION_FILE: 'autobot:\n  base_dir: "/opt/autobot"\n# lives in /opt/autobot\nx: /opt/autobot/y\n',
        "a.yml": "dest: /opt/autobot/a  # under /opt/autobot\n",
        "b.j2": "ExecStart={{ autobot.base_dir }}/run\n",
    }
    assert literal_counts(files) == {_DEFINITION_FILE: 1, "a.yml": 1}
