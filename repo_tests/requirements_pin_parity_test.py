# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15070 — protobuf is declared in both requirements files; catch a divergent pin.

Exercises the exact functions ``code-quality`` calls
(``tools/lint/check_requirements_pin_parity.py --audit``) rather than
paraphrasing the rule, so a test agreeing with a second copy of the decision
proves nothing about the copy that actually blocks a merge.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_CHECKER = REPO_ROOT / "tools" / "lint" / "check_requirements_pin_parity.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_requirements_pin_parity", _CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


def _tree(tmp_path: Path, root_body: str, backend_body: str) -> Path:
    (tmp_path / "requirements.txt").write_text(root_body, encoding="utf-8")
    backend = tmp_path / "autobot-backend"
    backend.mkdir(parents=True, exist_ok=True)
    (backend / "requirements.txt").write_text(backend_body, encoding="utf-8")
    return tmp_path


# --------------------------------------------------------------------------
# The invariant, against synthetic input
# --------------------------------------------------------------------------


def test_compute_divergence_flags_a_package_pinned_differently_in_each_file():
    root = {"protobuf": ">=7.36.0,<8.0.0", "aiosqlite": ">=0.21.0"}
    backend = {"protobuf": "<7.0", "aiosqlite": ">=0.21.0"}
    assert checker.compute_divergence(root, backend) == ["protobuf"]


def test_compute_divergence_accepts_identical_specifiers():
    root = {"protobuf": ">=7.36.0,<8.0.0"}
    backend = {"protobuf": ">=7.36.0,<8.0.0"}
    assert checker.compute_divergence(root, backend) == []


def test_compute_divergence_ignores_a_package_only_one_file_declares():
    root = {"protobuf": ">=7.36.0,<8.0.0", "asyncssh": ">=2.24.0"}
    backend = {"protobuf": ">=7.36.0,<8.0.0"}
    assert checker.compute_divergence(root, backend) == []


def test_parse_direct_requirements_strips_trailing_comment_and_spaces(tmp_path):
    path = tmp_path / "requirements.txt"
    path.write_text("protobuf >= 7.36.0, <8.0.0   # capped, see note\n", encoding="utf-8")
    assert checker.parse_direct_requirements(path) == {"protobuf": ">=7.36.0,<8.0.0"}


def test_parse_direct_requirements_does_not_follow_r_includes(tmp_path):
    """Following the include would fold one file onto the other and hide divergence."""
    (tmp_path / "included.txt").write_text("protobuf<7.0\n", encoding="utf-8")
    path = tmp_path / "requirements.txt"
    path.write_text("-r included.txt\n-e ../autobot_shared\n-c c.txt\naiosqlite>=0.21.0\n", encoding="utf-8")
    assert checker.parse_direct_requirements(path) == {"aiosqlite": ">=0.21.0"}


def test_parse_direct_requirements_normalizes_underscores_and_case(tmp_path):
    path = tmp_path / "requirements.txt"
    path.write_text("Python_DocX>=1.2.0\n", encoding="utf-8")
    assert checker.parse_direct_requirements(path) == {"python-docx": ">=1.2.0"}


# --------------------------------------------------------------------------
# Discrimination — against a real (synthetic) tree on disk
# --------------------------------------------------------------------------


def test_audit_flags_a_reverted_protobuf_cap(tmp_path):
    """The #15070 near miss: the note said <7.0, so someone edits one file back."""
    base = _tree(tmp_path, "protobuf>=7.36.0,<8.0.0\n", "-r ../requirements.txt\nprotobuf<7.0\n")
    compared, problems = checker.audit_parity(base)
    assert compared == 1
    assert len(problems) == 1
    assert "protobuf" in problems[0]


def test_audit_is_clean_when_the_shared_pins_agree(tmp_path):
    base = _tree(tmp_path, "protobuf>=7.36.0,<8.0.0\n", "-r ../requirements.txt\nprotobuf>=7.36.0,<8.0.0\n")
    compared, problems = checker.audit_parity(base)
    assert problems == []
    assert compared == 1


def test_audit_fails_when_a_requirements_file_parses_to_nothing(tmp_path):
    """A rename or an emptied file must not read as a clean comparison."""
    base = _tree(tmp_path, "protobuf>=7.36.0,<8.0.0\n", "# everything moved elsewhere\n")
    compared, problems = checker.audit_parity(base)
    assert compared == 0
    assert len(problems) == 1
    assert "zero packages" in problems[0]


def test_audit_fails_when_the_two_files_share_no_package(tmp_path):
    """An empty overlap asserts nothing — it must fail, not pass (#15087)."""
    base = _tree(tmp_path, "protobuf>=7.36.0,<8.0.0\n", "-r ../requirements.txt\nfastapi>=0.141.1\n")
    compared, problems = checker.audit_parity(base)
    assert compared == 0
    assert len(problems) == 1
    assert "no package in common" in problems[0]


# --------------------------------------------------------------------------
# The real tree
# --------------------------------------------------------------------------


def test_the_repo_itself_has_parity_over_a_non_empty_shared_set():
    compared, problems = checker.audit_parity(REPO_ROOT)
    assert problems == [], "\n\n".join(problems)
    assert compared > 0, "the guard ran over no shared packages — it asserted nothing (#15087)"


def test_protobuf_is_one_of_the_packages_the_guard_actually_compares():
    """The regression this guard exists for must be inside its reach, not merely near it."""
    root = checker.parse_direct_requirements(REPO_ROOT / "requirements.txt")
    backend = checker.parse_direct_requirements(REPO_ROOT / "autobot-backend" / "requirements.txt")
    assert "protobuf" in set(root) & set(backend)
    assert root["protobuf"] == backend["protobuf"] == ">=7.36.0,<8.0.0"


def test_the_protobuf_cap_matches_what_opentelemetry_proto_declares():
    """#15070: the rationale must not outlive the resolution it describes.

    ``opentelemetry-proto`` is the dependency the note names. Its pin lives in
    the same file, and the note's claim is about which protobuf majors that
    version admits. Pinning otel forward without revisiting the protobuf line
    is exactly how the two drifted apart (#10589 moved otel to 1.43.0, #10678
    raised protobuf the next day, the note was updated neither time), so the
    two lines are asserted together here.
    """
    root = checker.parse_direct_requirements(REPO_ROOT / "requirements.txt")
    assert root["opentelemetry-proto"] == "==1.44.0", (
        "opentelemetry-proto moved. Re-read its Requires-Dist for protobuf and "
        "update BOTH the protobuf constraint and its rationale (#15070)."
    )
    assert root["protobuf"] == ">=7.36.0,<8.0.0"
