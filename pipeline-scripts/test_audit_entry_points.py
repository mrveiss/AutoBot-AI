#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for audit_entry_points and the scripts/ caller search (#22199).

Split from test_audit_unwired_trackers.py, which sits at the 600-line ceiling.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import audit_entry_points
import audit_unwired_trackers as audit
import pytest

MAIN_BLOCK = 'if __name__ == "__main__":\n    pass\n'


def _write(root: Path, rel: str, text: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_scripts_dir_import_counts_as_caller_but_comment_does_not(tmp_path: Path) -> None:
    mod = _write(tmp_path, "autobot-backend/knowledge/vector_repair.py", '"""x"""\n')
    _write(tmp_path, "autobot-backend/knowledge/other.py", "x = 1\n")
    _write(tmp_path, "scripts/repair.py", "from knowledge.vector_repair import run\n")
    with patch.object(audit, "REPO_ROOT", tmp_path):
        assert audit.grep_count_production_callers("vector_repair", mod) == 1
        (tmp_path / "scripts/repair.py").write_text("# see scripts: vector_repair is run by hand\n", encoding="utf-8")
        assert audit.grep_count_production_callers("vector_repair", mod) == 0


def test_scripts_dir_is_searched_for_callers_but_never_scanned() -> None:
    assert "scripts" in audit.CALLER_SEARCH_DIRS
    assert "scripts" not in audit.SCAN_DIRS


def test_package_main_is_entry_point_but_plain_main_block_is_not(tmp_path: Path) -> None:
    pkg = _write(tmp_path, "autobot-backend/acp/__main__.py", "")
    lib = _write(tmp_path, "autobot-backend/lib/helper.py", 'if __name__ == "__main__":\n    pass\n')
    with patch.object(audit, "REPO_ROOT", tmp_path):
        assert audit.is_launched_module(pkg, audit.derive_module_path(pkg))
        assert not audit.is_launched_module(lib, audit.derive_module_path(lib))


def test_python_dash_m_docstring_must_name_the_modules_own_path(tmp_path: Path) -> None:
    own = _write(
        tmp_path,
        "autobot-backend/mcp_server/main_x.py",
        '"""Run:\n    python -m mcp_server.main_x --http\n"""\n' + MAIN_BLOCK,
    )
    other = _write(
        tmp_path, "autobot-backend/mcp_server/main_y.py", '"""Run:\n    python -m mcp_server.main_x\n"""\n' + MAIN_BLOCK
    )
    prefix = _write(
        tmp_path, "autobot-backend/mcp_server/main_z.py", '"""python -m mcp_server.main_zz"""\n' + MAIN_BLOCK
    )
    with patch.object(audit, "REPO_ROOT", tmp_path):
        assert audit.is_launched_module(own, audit.derive_module_path(own))
        assert not audit.is_launched_module(other, audit.derive_module_path(other))
        assert not audit.is_launched_module(prefix, audit.derive_module_path(prefix))


@pytest.mark.parametrize(
    "rel,exempt",
    [
        ("autobot-backend/api/foo_benchmark.py", True),
        ("autobot-backend/api/api_benchmarks.py", True),
        ("autobot-backend/benchmarks/anything.py", True),
        ("autobot-backend/api/benchmark_utils.py", False),
        ("autobot-backend/api/benchmarks_helper.py", False),
    ],
)
def test_benchmark_exemption_is_by_segment_or_suffix(rel: str, exempt: bool) -> None:
    assert audit_entry_points.is_benchmark(Path(rel)) is exempt


def test_python_dash_m_docstring_alone_is_not_exempt_without_a_main_block(tmp_path: Path) -> None:
    doc = '"""Run:\n    python -m mcp_server.main_q\n"""\n'
    bare = _write(tmp_path, "autobot-backend/mcp_server/main_q.py", doc + "X = 1\n")
    runnable = _write(tmp_path, "autobot-backend/mcp_server/main_q2.py", doc.replace("main_q", "main_q2") + MAIN_BLOCK)
    indented = _write(
        tmp_path,
        "autobot-backend/mcp_server/main_q3.py",
        doc.replace("main_q", "main_q3") + "def f():\n    if __name__ == '__main__':\n        pass\n",
    )
    with patch.object(audit, "REPO_ROOT", tmp_path):
        assert not audit.is_launched_module(bare, audit.derive_module_path(bare))
        assert audit.is_launched_module(runnable, audit.derive_module_path(runnable))
        assert not audit.is_launched_module(indented, audit.derive_module_path(indented))


@pytest.mark.parametrize(
    "line,counted",
    [
        ("scripts/a.py:3:from knowledge.vector_repair import run", True),
        ("scripts/a.py:3:    # from knowledge.vector_repair import run", False),
        ("autobot-frontend/a.ts:3:import x from './vector_repair'", True),
        ("autobot-frontend/a.ts:3:  // import x from './vector_repair'", False),
        ("autobot-frontend/a.vue:3:  * import x from './vector_repair'", False),
        ("autobot-frontend/a.py:3:x = 1  # trailing note: import vector_repair", True),
    ],
)
def test_comment_only_grep_hits_are_not_callers(line: str, counted: bool) -> None:
    assert audit._is_production_caller_line(line, "elsewhere.py") is counted


def test_scripts_comment_with_import_text_is_not_a_caller_but_real_import_is(tmp_path: Path) -> None:
    mod = _write(tmp_path, "autobot-backend/knowledge/vector_repair.py", '"""x"""\n')
    script = _write(tmp_path, "scripts/repair.py", "# from knowledge import vector_repair\n")
    with patch.object(audit, "REPO_ROOT", tmp_path):
        assert audit.grep_count_production_callers("vector_repair", mod) == 0
        script.write_text("from knowledge import vector_repair\n", encoding="utf-8")
        assert audit.grep_count_production_callers("vector_repair", mod) == 1


def _scan_tree(tmp_path: Path, files: dict[str, str]) -> list:
    for rel, text in files.items():
        _write(tmp_path, rel, text)
    registry_dir = tmp_path / "autobot-backend/initialization/router_registry"
    registry_dir.mkdir(parents=True, exist_ok=True)
    with (
        patch.object(audit, "REPO_ROOT", tmp_path),
        patch.object(audit, "ROUTER_REGISTRY_DIR", registry_dir),
        patch.object(audit, "fetch_closed_tracker_set", return_value={777}),
        patch.object(audit, "grep_count_production_callers", return_value=0),
    ):
        return audit.scan()


def test_scan_skips_launched_modules_but_flags_a_plain_library(tmp_path: Path) -> None:
    doc = '"""Issue #777: closed tracker."""\n'
    findings = _scan_tree(
        tmp_path,
        {
            "autobot-backend/acp/__main__.py": doc,
            "autobot-backend/benchmarks/x.py": doc,
            "autobot-backend/api/y_benchmark.py": doc,
            "autobot-backend/lib/plain_library.py": doc,
        },
    )
    assert [f.file for f in findings] == ["autobot-backend/lib/plain_library.py"]


def test_main_block_example_inside_the_docstring_is_not_a_main_block(tmp_path: Path) -> None:
    """The docstring quotes an unindented main-block example; only a parsed top-level ``if`` counts."""
    doc = '"""Run:\n    python -m mcp_server.main_d\n\nif __name__ == "__main__":\n    main()\n"""\nX = 1\n'
    fake = _write(tmp_path, "autobot-backend/mcp_server/main_d.py", doc)
    with patch.object(audit, "REPO_ROOT", tmp_path):
        assert not audit.is_launched_module(fake, audit.derive_module_path(fake))


def test_test_prefixed_script_import_is_not_a_production_caller(tmp_path: Path) -> None:
    mod = _write(tmp_path, "autobot-backend/knowledge/vector_repair.py", '"""x"""\n')
    _write(tmp_path, "scripts/test_repair.py", "from knowledge import vector_repair\n")
    with patch.object(audit, "REPO_ROOT", tmp_path):
        assert audit.grep_count_production_callers("vector_repair", mod) == 0
        _write(tmp_path, "scripts/repair.py", "from knowledge import vector_repair\n")
        assert audit.grep_count_production_callers("vector_repair", mod) == 1


def test_shared_package_launcher_keeps_its_package_prefix(tmp_path: Path) -> None:
    doc = '"""Run:\n    python -m autobot_shared.repair\n"""\n' + MAIN_BLOCK
    shared = _write(tmp_path, "autobot_shared/repair.py", doc)
    backend = _write(
        tmp_path, "autobot-backend/mcp_server/main_b.py", doc.replace("autobot_shared.repair", "mcp_server.main_b")
    )
    with patch.object(audit, "REPO_ROOT", tmp_path):
        assert audit.derive_launcher_module_path(shared) == "autobot_shared.repair"
        assert audit.derive_launcher_module_path(backend) == "mcp_server.main_b"
        assert audit.is_launched_module(shared, audit.derive_launcher_module_path(shared))
        assert audit.is_launched_module(backend, audit.derive_launcher_module_path(backend))


def test_a_checkout_under_a_benchmarks_directory_does_not_exempt_every_module(tmp_path: Path) -> None:
    """The ``benchmarks`` segment is judged relative to the repo root, not on the absolute path."""
    root = tmp_path / "benchmarks" / "AutoBot-AI"
    findings = _scan_tree(root, {"autobot-backend/lib/plain_library.py": '"""Issue #777: closed tracker."""\n'})
    assert [f.file for f in findings] == ["autobot-backend/lib/plain_library.py"]
    assert audit_entry_points.is_benchmark(root / "autobot-backend/benchmarks/x.py", root)
    assert not audit_entry_points.is_benchmark(root / "autobot-backend/lib/plain_library.py", root)
