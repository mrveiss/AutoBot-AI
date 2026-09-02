#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Discrimination tests for the #14544 live-install-sys.path-default guard.

The banned literal is assembled from fragments (mirroring
``guard.LIVE_INSTALL_ROOT``) so this file does not trip the guard it tests.
"""

from __future__ import annotations

import logging
import pathlib
import textwrap

from tools.lint import check_no_live_install_sys_path_default as guard

#: The live-install root, built the same way the guard builds it.
LIVE_ROOT = guard.LIVE_INSTALL_ROOT


def _write(base: pathlib.Path, rel: str, body: str) -> pathlib.Path:
    path = base / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def test_sys_path_insert_with_live_install_default_is_reported(tmp_path):
    path = _write(
        tmp_path,
        "debug/tool.py",
        f'''\
        import os
        import sys

        sys.path.insert(0, os.environ.get("AUTOBOT_PROJECT_ROOT", "{LIVE_ROOT}/code_source"))
        ''',
    )

    hits = guard.live_install_default_sites(path)

    assert hits == [(4, hits[0][1])]
    assert "sys.path.insert" in hits[0][1]


def test_sys_path_append_with_live_install_default_is_reported(tmp_path):
    path = _write(
        tmp_path,
        "debug/tool.py",
        f'''\
        import os
        import sys

        sys.path.append(os.getenv("AUTOBOT_PROJECT_ROOT", "{LIVE_ROOT}/code_source"))
        ''',
    )

    hits = guard.live_install_default_sites(path)

    assert len(hits) == 1


def test_the_canonical_resolver_is_not_reported(tmp_path):
    path = _write(
        tmp_path,
        "debug/tool.py",
        """\
        import sys

        from autobot_shared.paths import project_root

        sys.path.insert(0, str(project_root()))
        """,
    )

    assert guard.live_install_default_sites(path) == []


def test_an_env_lookup_default_unrelated_to_the_live_install_is_not_reported(tmp_path):
    """Only the live-install default is banned, not every env-backed sys.path insert."""
    path = _write(
        tmp_path,
        "debug/tool.py",
        """\
        import os
        import sys

        sys.path.insert(0, os.environ.get("AUTOBOT_PROJECT_ROOT", "/srv/checkout"))
        """,
    )

    assert guard.live_install_default_sites(path) == []


def test_a_live_install_default_outside_a_sys_path_call_is_not_reported(tmp_path):
    """The defect is specifically a sys.path mutation; an unrelated env lookup is not."""
    path = _write(
        tmp_path,
        "debug/tool.py",
        f'''\
        import os

        ANSIBLE_DIR = os.environ.get("SLM_ANSIBLE_DIR", "{LIVE_ROOT}/code_source/ansible")
        ''',
    )

    assert guard.live_install_default_sites(path) == []


def test_main_reports_a_nonzero_exit_and_the_resolver_hint(tmp_path, caplog):
    """Uses ``caplog`` (root-logger propagation), not ``capsys`` -- ``main()``'s own
    ``StreamHandler`` binds to ``sys.stderr`` only on its first call in the process
    and stays bound to that reference across every later test in the same pytest
    session, so a second ``capsys``-based assertion would silently capture nothing.
    """
    path = _write(
        tmp_path,
        "debug/tool.py",
        f'''\
        import os
        import sys

        sys.path.insert(0, os.environ.get("AUTOBOT_PROJECT_ROOT", "{LIVE_ROOT}/code_source"))
        ''',
    )

    with caplog.at_level(logging.ERROR):
        exit_code = guard.main(["check_no_live_install_sys_path_default.py", str(path)])

    assert exit_code == 1
    assert guard.RESOLVER in caplog.text


def test_main_is_clean_over_the_fixed_files(tmp_path, caplog):
    path = _write(
        tmp_path,
        "debug/tool.py",
        """\
        import sys

        from autobot_shared.paths import project_root

        sys.path.insert(0, str(project_root()))
        """,
    )

    with caplog.at_level(logging.ERROR):
        exit_code = guard.main(["check_no_live_install_sys_path_default.py", str(path)])

    assert exit_code == 0
    assert caplog.text == ""


def test_the_guard_does_not_need_an_exemption_for_itself():
    """A guard that trips its own rule would need one -- it must not."""
    self_path = pathlib.Path(guard.__file__)
    assert guard.live_install_default_sites(self_path) == []


def test_this_test_file_does_not_need_an_exemption_either():
    """The f-string fixtures above never execute a real sys.path call -- they are
    string arguments to ``_write()``, so no ``ast.Call`` to ``sys.path.insert``/
    ``.append`` exists in this file's own AST for the guard to find.
    """
    this_file = pathlib.Path(__file__)
    assert guard.live_install_default_sites(this_file) == []


def test_the_live_repository_has_no_remaining_sites():
    """#14544 swept all 18; nothing should be left to find at HEAD."""
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    files, _ = guard.scan_python_files([], repo_root)
    total = 0
    for path in files:
        try:
            total += len(guard.live_install_default_sites(path))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue

    assert total == 0
