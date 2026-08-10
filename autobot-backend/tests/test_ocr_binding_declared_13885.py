# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
OCR dependency-pairing guard (#13885).

Ansible installs the tesseract **system** packages on every backend host, but the
Python binding that calls them lived in no requirements file. The binary shipped
everywhere and no Python caller could reach it: ``/api/vision/ocr``, ``vnc_manager``,
``gui_controller.read_text_from_region`` and the CAPTCHA solver each guard-import
``pytesseract`` and degrade to a "not installed" message, so the features were
permanently off with no crash and no alert.

Half a dependency is the failure mode, so this guards the *pair* in both
directions: the system packages without the binding is the original bug, and the
binding without the system packages is a runtime failure at the first OCR call.

Deliberately a declaration test, not an import test. The bug was a packaging gap —
once ``pytesseract`` is declared, the resolver enforces its presence, and an import
test would only re-assert what the installer already guarantees while failing in any
environment that installs a subset of requirements.
"""

import pathlib
import re

import pytest

_BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

_REQUIREMENTS = _BACKEND_ROOT / "requirements.txt"
_ANSIBLE_BACKEND_TASKS = _REPO_ROOT / "autobot-slm-backend" / "ansible" / "roles" / "backend" / "tasks" / "main.yml"

# System packages ansible installs for OCR, and the binding that reaches them.
_SYSTEM_PACKAGES = ("tesseract-ocr", "libtesseract-dev")
_BINDING = "pytesseract"


def _declared_requirements(path: pathlib.Path) -> list[str]:
    """Return requirement lines with comments and blanks stripped."""
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            lines.append(line)
    return lines


def _requirement_names(lines: list[str]) -> set[str]:
    """Extract the distribution name from each requirement line, lowercased."""
    names = set()
    for line in lines:
        match = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)", line)
        if match:
            names.add(match.group(1).lower())
    return names


@pytest.fixture(scope="module")
def declared_names() -> set[str]:
    assert _REQUIREMENTS.is_file(), f"missing requirements file: {_REQUIREMENTS}"
    return _requirement_names(_declared_requirements(_REQUIREMENTS))


@pytest.fixture(scope="module")
def ansible_tasks() -> str:
    assert _ANSIBLE_BACKEND_TASKS.is_file(), f"missing ansible tasks: {_ANSIBLE_BACKEND_TASKS}"
    return _ANSIBLE_BACKEND_TASKS.read_text(encoding="utf-8")


def test_binding_is_declared_in_backend_requirements(declared_names):
    """The Python binding must be declared, or every OCR call site is dead code."""
    assert _BINDING in declared_names, (
        f"{_BINDING} is not declared in {_REQUIREMENTS}. Ansible installs "
        f"{', '.join(_SYSTEM_PACKAGES)} on every host, but without this binding no "
        "Python caller can reach tesseract and every OCR surface silently degrades "
        "to its 'not installed' branch (#13885)."
    )


def test_system_packages_still_installed_by_ansible(ansible_tasks):
    """The binding is useless without the system packages it wraps."""
    missing = [pkg for pkg in _SYSTEM_PACKAGES if f"- {pkg}" not in ansible_tasks]
    assert not missing, (
        f"ansible no longer installs {missing} in {_ANSIBLE_BACKEND_TASKS}, but "
        f"{_BINDING} is declared in backend requirements. The binding wraps the "
        "tesseract binary — dropping the system packages makes every OCR call fail "
        "at runtime instead of at install time (#13885)."
    )
