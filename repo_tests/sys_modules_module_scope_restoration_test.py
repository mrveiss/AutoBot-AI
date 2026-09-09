# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A module-scope ``sys.modules`` write must be undone somewhere (#15800).

``sys.modules["x"] = stub`` at module scope runs at IMPORT time and outlives the
module that wrote it. Whether that is a defect depends on the stub. #15796 was
the dangerous end: the stub's ``check_admin_permission`` returned ``True`` for
everything, so a later test importing ``auth_middleware`` got an allow-all
authentication gate — **and a test written to prove the gate rejects a non-admin
passed, because the gate had been replaced by one that approves everything.**

WHY THE COUNT HERE IS NOT THE COUNT IN THE ISSUE
------------------------------------------------
#15800 reports 60 sites in 34 files, located by grep and — its own honesty note
says so — never audited. Measured by AST against the module-scope boundary:

    all module-scope writes   228 sites in 89 files
    no restoration anywhere    55 sites in 36 files   <- this baseline
    some restoration          173 sites in 53 files

The 55 lands near the issue's 60 by a different route, which is the only reason
either number is worth anything. The 228 does not contradict it: most writes ARE
undone somewhere, and a guard frozen on the raw population would have
grandfathered 173 sites that are already fine.

**Indentation is not scope**, and that is where a text-based count goes wrong. In
``autobot-backend/conftest.py`` a column-0 grep finds 8 writes; there are 23. The
other 15 sit inside module-level ``if`` and ``try`` blocks — indented, and still
executed at import. This module descends through blocks and stops at ``def`` and
``class``, which is the actual import-time boundary.

WHAT THIS CANNOT SEE
--------------------
* **Restoration is detected per FILE, not per key.** A module that restores one
  stub and leaks another reads as restored. That fails toward false negatives —
  the unsafe direction — and is the honest limit of a syntactic check.
* **Whether a stub is dangerous is not judged.** An allow-all auth gate and an
  inert namespace stub are the same to this guard. It asks whether the
  substitution is undone, not what it does.
* **The grandfathered 36 are an inventory, not 36 defects.** None has been
  audited. The list exists to stop the population growing, not to assert that
  everything in it is wrong.
"""

from __future__ import annotations

import ast
import re
import subprocess  # nosec B404
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from autobot_shared.paths import scrubbed_git_env  # noqa: E402
from repo_tests._paths import repo_root  # noqa: E402

#: Bound to files EXAMINED. A `git ls-files` returning nothing would otherwise
#: pass this module having parsed zero files -- the same green a clean tree gives.
MIN_FILES_PARSED = 3000

_RESTORES = re.compile(
    r"del\s+sys\.modules"
    r"|sys\.modules\.pop"
    r"|monkeypatch\.setitem"
    r"|_ORIGINAL_MODULES"
    r"|restore_modules"
    r"|sys\.modules\.update\("
)

#: Files with a module-scope `sys.modules` write and no restoration anywhere in
#: them. Frozen so a NEW one fails. Shrinks only, and a shrink must be recorded.
GRANDFATHERED = frozenset(
    {
        "autobot-backend/chat_workflow/cot_events_test.py",
        "autobot-backend/chat_workflow/graph_inject_warning_test.py",
        "autobot-backend/chat_workflow/tool_loop_detection_test.py",
        "autobot-backend/code_intelligence/anti_pattern_detector_test.py",
        "autobot-backend/constants/network_constants.py",
        "autobot-backend/knowledge_sync_incremental_test.py",
        "autobot-backend/llc/tests/test_autobot_agent_adapter.py",
        "autobot-backend/onboarding/doctor_test.py",
        "autobot-backend/services/audit_logger_test.py",
        "autobot-backend/services/knowledge/test_contradiction_detector.py",
        "autobot-backend/services/knowledge/test_doc_indexer.py",
        "autobot-backend/services/knowledge/test_doc_indexer_dim_mismatch.py",
        "autobot-backend/tests/agents/test_json_formatter_agent.py",
        "autobot-backend/tests/agents/test_memory_hooks.py",
        "autobot-backend/tests/api/test_onboarding_auth_regression.py",
        "autobot-backend/tests/llm_interface_pkg/test_provider_metadata.py",
        "autobot-backend/tests/security/test_onboarding_auth_regression.py",
        "autobot-backend/tests/test_system_health_registry.py",
        "autobot-backend/tests/test_tool_schema_correction.py",
        "autobot-slm-backend/services/jwks_verifier_test.py",
        "autobot-slm-backend/services/reconciler_check_node_health_test.py",
        "autobot-slm-backend/tests/api/conftest.py",
        "autobot-slm-backend/tests/services/test_deploy_artifacts_lockstep.py",
        "autobot-slm-backend/tests/services/test_llm_secrets.py",
        "autobot-slm-backend/tests/services/test_oidc_token_cache.py",
        "autobot-slm-backend/tests/services/test_rs256_denylist.py",
        "autobot-slm-backend/tests/services/test_sso_vault_client.py",
        "autobot-slm-backend/tests/services/test_step_up_auth.py",
        "autobot-slm-backend/tests/test_api_request_counter.py",
        "autobot-slm-backend/tests/test_claude_api_monitor.py",
        "autobot-slm-backend/tests/test_prometheus_registry_endpoint.py",
        "plugins/core-plugins/video-generation-plugin/tools/providers_test.py",
        "tools/lint/check_no_llm_response_dict_access_test.py",
        "tools/lint/check_no_orphan_refs_test.py",
        "tools/lint/check_no_root_clutter_test.py",
        "tools/lint/check_no_src_mock_path_test.py",
    }
)


def module_scope_sys_modules_writes(tree: ast.Module) -> list[int]:
    """Line numbers of `sys.modules[...] = ...` reachable at import time.

    Descends `if`/`try`/`for`/`with` bodies -- those run on import -- and stops
    at `def`/`class`, which do not.
    """
    found: list[int] = []

    def walk(statements) -> None:
        for stmt in statements:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if (
                        isinstance(target, ast.Subscript)
                        and isinstance(target.value, ast.Attribute)
                        and target.value.attr == "modules"
                    ):
                        found.append(stmt.lineno)
            for field in ("body", "orelse", "finalbody"):
                if hasattr(stmt, field):
                    walk(getattr(stmt, field))
            for handler in getattr(stmt, "handlers", []):
                walk(handler.body)

    walk(tree.body)
    return found


def _tracked_python() -> list[Path]:
    root = repo_root()
    result = subprocess.run(  # nosec B603 B607
        ["git", "ls-files", "*.py"], cwd=root, capture_output=True, text=True, check=False, env=scrubbed_git_env()
    )
    return [root / line for line in result.stdout.splitlines() if line]


def _scan() -> tuple[set[str], int]:
    """(files writing at module scope with no restoration, files parsed)."""
    root = repo_root()
    offenders, parsed = set(), 0
    for path in _tracked_python():
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        parsed += 1
        if module_scope_sys_modules_writes(tree) and not _RESTORES.search(source):
            offenders.add(path.relative_to(root).as_posix())
    return offenders, parsed


def test_the_detector_sees_a_write_inside_a_module_level_try() -> None:
    """Known positive, and the case a column-0 grep misses.

    Indented, and still executed at import -- which is the whole difference
    between indentation and scope.
    """
    src = "import sys\ntry:\n    sys.modules['x'] = object()\nexcept ImportError:\n    pass\n"
    assert module_scope_sys_modules_writes(ast.parse(src)), "detector misses a write inside a module-level try"


def test_the_detector_ignores_a_write_inside_a_function() -> None:
    """The contrast pair. A write inside `def` does not run at import, and a
    detector that cannot tell the two apart would report the whole test suite."""
    src = "import sys\ndef f():\n    sys.modules['x'] = object()\n"
    assert not module_scope_sys_modules_writes(ast.parse(src)), "detector reports a write that never runs at import"


def test_the_sweep_parsed_enough_files_to_mean_anything() -> None:
    _, parsed = _scan()
    assert parsed >= MIN_FILES_PARSED, (
        f"parsed {parsed} files, floor is {MIN_FILES_PARSED}. "
        "A sweep over an empty set reports the same clean result as a clean tree."
    )


def test_no_new_module_leaks_a_sys_modules_substitution() -> None:
    offenders, _ = _scan()
    new = sorted(offenders - GRANDFATHERED)
    assert not new, (
        "module-scope sys.modules write with no restoration in the file:\n  "
        + "\n  ".join(new)
        + "\n\nRestore it in teardown, or use monkeypatch.setitem so pytest undoes it. "
        "A substitution that outlives its module is inherited by every later import."
    )


def test_the_grandfathered_list_has_not_gone_stale() -> None:
    """The direction normally forgotten: an entry that gained a restoration must
    be removed, or the list silently permits the next module to lose one."""
    offenders, _ = _scan()
    stale = sorted(GRANDFATHERED - offenders)
    assert not stale, (
        "GRANDFATHERED entries that now restore -- remove them, the list only shrinks:\n  " + "\n  ".join(stale)
    )
