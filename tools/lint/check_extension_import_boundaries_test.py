# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Guards for the extension/skill/plugin import boundary checker (#14329).

The checker used to block only a hand-written list of package names while its
docstring claimed the whole ``autobot-backend`` namespace was closed. Anything
nobody remembered to add — ``media``, ``tools``, ``transcriber`` — was importable
from an extension and the check passed. The namespace is now derived from the
directory listing, so the property worth pinning is that a package *nobody has
heard of* is blocked.

These tests run the checker **in process** against files under ``tmp_path``.
An earlier version wrote probe files into the real ``skills/builtin`` tree and
deleted them afterwards; under xdist another test globbing that directory saw a
probe mid-delete and died with ``FileNotFoundError``. A test must not mutate the
source tree it is checking.
"""

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_CHECKER_PATH = REPO_ROOT / "tools" / "lint" / "check_extension_import_boundaries.py"


def _load_checker():
    """Import the checker by path — tools/lint is not an importable package."""
    spec = importlib.util.spec_from_file_location("_boundary_checker", _CHECKER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def checker():
    return _load_checker()


def _skill_file(tmp_path: Path, source: str) -> Path:
    """A path with the components that put a file in the 'skill' layer.

    Scope is decided by path components (``skills`` + ``builtin``), so a tmp tree
    shaped like the real one is in scope without touching the real one.
    """
    target = tmp_path / "autobot-backend" / "skills" / "builtin" / "probe.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")
    return target


def test_a_newly_added_core_package_is_blocked_without_editing_the_checker(checker, tmp_path, monkeypatch):
    """The whole point of deriving the namespace instead of listing it."""
    monkeypatch.setattr(checker, "_core_packages", lambda: frozenset({"a_package_invented_today"}))
    probe = _skill_file(tmp_path, "from a_package_invented_today.thing import X\n")

    violations = checker._check_file(probe, probe.read_text(encoding="utf-8"))

    assert violations, "a core package absent from any hand-written list must still be blocked"
    assert "a_package_invented_today" in violations[0]


def test_a_plain_import_of_a_core_package_is_caught(checker, tmp_path, monkeypatch):
    """#14742: `import services.x` crossed the layer while `from services.x import y` did not.

    The rule enforced a syntax rather than a boundary, so the plain spelling was
    a silent bypass — and nobody writing it would learn the rule existed.
    """
    monkeypatch.setattr(checker, "_core_packages", lambda: frozenset({"services"}))
    probe = _skill_file(tmp_path, "import services.llm_service\n")

    violations = checker._check_file(probe, probe.read_text(encoding="utf-8"))

    assert violations, "a plain import of a core package must be a violation"
    assert "services.llm_service" in violations[0]


def test_an_aliased_plain_import_is_caught(checker, tmp_path, monkeypatch):
    """`import agents.x as y` is the form that surfaced this."""
    monkeypatch.setattr(checker, "_core_packages", lambda: frozenset({"agents"}))
    probe = _skill_file(tmp_path, "import agents.summarization_agent as agent_mod\n")

    assert checker._check_file(probe, probe.read_text(encoding="utf-8"))


def test_a_plain_import_can_be_waived(checker, tmp_path, monkeypatch):
    """The waiver mechanism must apply to both spellings, not just one."""
    monkeypatch.setattr(checker, "_core_packages", lambda: frozenset({"services"}))
    probe = _skill_file(
        tmp_path,
        "import services.llm_service  # nosemgrep: extension-no-core-internals\n",
    )

    assert checker._check_file(probe, probe.read_text(encoding="utf-8")) == []


def test_both_import_forms_report_identically(checker, tmp_path, monkeypatch):
    """One boundary, one verdict — the spelling must not change the answer."""
    monkeypatch.setattr(checker, "_core_packages", lambda: frozenset({"services"}))

    plain = _skill_file(tmp_path, "import services.llm_service\n")
    plain_violations = checker._check_file(plain, plain.read_text(encoding="utf-8"))

    from_form = _skill_file(tmp_path, "from services.llm_service import get_llm_service\n")
    from_violations = checker._check_file(from_form, from_form.read_text(encoding="utf-8"))

    assert len(plain_violations) == len(from_violations) == 1
    assert "extension-no-core-internals" in plain_violations[0]
    assert "extension-no-core-internals" in from_violations[0]


def test_a_plain_stdlib_or_thirdparty_import_is_untouched(checker, tmp_path, monkeypatch):
    """Only the backend namespace is closed; ordinary imports must stay silent."""
    monkeypatch.setattr(checker, "_core_packages", lambda: frozenset({"services"}))
    probe = _skill_file(tmp_path, "import json\nimport pytest\n")

    assert checker._check_file(probe, probe.read_text(encoding="utf-8")) == []


def test_autobot_shared_is_allowed(checker, tmp_path):
    probe = _skill_file(tmp_path, "from autobot_shared.logging_manager import get_logger\n")
    assert checker._check_file(probe, probe.read_text(encoding="utf-8")) == []


def test_inline_waiver_still_works(checker, tmp_path, monkeypatch):
    monkeypatch.setattr(checker, "_core_packages", lambda: frozenset({"services"}))
    probe = _skill_file(
        tmp_path,
        "from services.llm_service import x  # nosemgrep: extension-no-core-internals\n",
    )
    assert checker._check_file(probe, probe.read_text(encoding="utf-8")) == []


def test_a_file_outside_the_extension_layers_is_not_checked(checker, tmp_path, monkeypatch):
    """Scope is path-based; a core module importing core is not a violation."""
    monkeypatch.setattr(checker, "_core_packages", lambda: frozenset({"services"}))
    plain = tmp_path / "autobot-backend" / "api" / "thing.py"
    plain.parent.mkdir(parents=True, exist_ok=True)
    plain.write_text("from services.llm_service import x\n", encoding="utf-8")

    assert checker._check_file(plain, plain.read_text(encoding="utf-8")) == []


def test_repo_currently_passes_the_boundary_rule(checker):
    """The real tree must be clean under the stricter rule."""
    violations = []
    for rel in ("autobot-backend/middleware/builtin", "autobot-backend/skills/builtin", "plugins/core-plugins"):
        for path in (REPO_ROOT / rel).rglob("*.py"):
            try:
                violations.extend(checker._check_file(path, path.read_text(encoding="utf-8")))
            except (OSError, UnicodeDecodeError):
                continue
    assert violations == [], violations


def test_baseline_has_no_stale_entries(checker):
    """A dormant exemption naming a moved file exempts nothing, silently."""
    assert checker._audit_baseline() == 0
