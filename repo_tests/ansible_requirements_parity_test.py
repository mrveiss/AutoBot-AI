# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Ansible and requirements must not state different versions of one package (#15568).

`openvino` was restated as a literal in seven files, so every dependabot bump went
red until six of them were hand-edited (#15408). #10524 built the mechanism that
fixes that shape -- `constraints/shared.txt` plus `scripts/check_constraint_drift.py`
-- but that guard reads only `requirements*.txt`. Ansible declares packages too, in
four different shapes, and nothing has ever compared the two sides. This test is
that comparison.

The four ansible shapes, all of which really install:

  * an `ansible.builtin.pip` / `pip` task's `name:` (a string or a list);
  * `python_security_updates`, a `package: minimum_version` map that
    `roles/dependency_patching` renders into a requirements file and pip-installs;
  * `packages.python` lists in `inventory/group_vars/*`;
  * `*_python_packages` list vars (`roles/slm_agent`).

Two assertions, deliberately of different strengths:

`test_no_constrained_package_carries_a_version_in_ansible` is absolute. A package
`constraints/shared.txt` pins may never carry a version at an ansible site, for the
reason the constraints file states in its own header: ansible can co-locate roles on
one host, so two floors for one library make pip unsatisfiable and skew the numpy ABI
on embeddings one role writes and another reads. This is the ansible half of
`check_constraint_drift.py`, which cannot see these files.

`test_every_cross_manifest_divergence_is_in_the_baseline` is ratcheted, because the
measured backlog is 55 and asserting it flat would redden the tree rather than
describe it. `ansible_pip_parity_baseline.txt` records every one, grouped by
the issue that owns it (#15596, #15597, #15598); the file only shrinks, and a stale
entry fails just as loudly as a new divergence.

Agreement is compared as specifier text, not as a resolved range. `>=0.115.0` and
`==0.115.0` are treated as different statements of the same version because they are:
one manifest moving to a pin while another keeps a floor is exactly the drift #15408
describes, and a range-aware comparison would call it equal and miss it.
"""

from __future__ import annotations

import pathlib
import re
from typing import NamedTuple

import pytest

yaml = pytest.importorskip("yaml")

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_ANSIBLE_ROOT = _REPO_ROOT / "autobot-slm-backend" / "ansible"
_CONSTRAINTS = _REPO_ROOT / "constraints" / "shared.txt"
# Named `..._pip_parity_...`, NOT `..._requirements_...`: this file RECORDS
# divergences, it does not DECLARE dependencies. `declared_distributions.py`
# globs `*requirements*.txt` to find manifests it must read as declaration
# sources, and `declared_distributions_test.py` fails on any tracked file
# matching that glob which the oracle does not read. A recorder that reads as
# a manifest would have every package name in it counted as "declared here"
# by three downstream guards (#15518). The distinction is the one #15566 is
# about: a recorder holds a name as data, a manifest holds it as a claim.
_BASELINE = pathlib.Path(__file__).with_name("ansible_pip_parity_baseline.txt")

_EXCLUDE_DIRS = ("node_modules", ".worktrees", ".git", "__pycache__")
_PIP_KEYS = ("pip", "ansible.builtin.pip")
_REQUIREMENT = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*(.*)$")
_SPECIFIER = re.compile(r"^(==|>=|<=|~=|!=|>|<)")

# Floors, not censuses: they measure how far the walk REACHES, never how much it
# finds. Fixing a divergence must never trip one -- only a parser that has quietly
# stopped matching the files it claims to read.
_MIN_ANSIBLE_DOCUMENTS = 250  # 327 parsed on 2026-09-04
_MIN_PIP_SITES = 15  # 18 carry at least one name: entry
_MIN_ANSIBLE_DECLARATIONS = 95  # 115, versioned and bare together
_MIN_REQUIREMENT_FILES = 30  # 34
_MIN_REQUIREMENT_PACKAGES = 140  # 161
_MIN_CONSTRAINED_PACKAGES = 2  # numpy, openvino


class Declaration(NamedTuple):
    """One package named at one ansible declaration site."""

    path: str
    context: str
    package: str
    specifier: str  # "" for a bare name, which is the shape the SSOT wants

    @property
    def key(self) -> str:
        return f"{self.path}::{self.package}"


def _normalise(name: str) -> str:
    """PEP 503 normalization so Pillow / pillow and nltk / NLTK compare equal."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _split(text: str) -> tuple[str, str] | None:
    """``'numpy>=2.0  # note'`` -> ``('numpy', '>=2.0')``; a non-requirement -> None."""
    stripped = text.split("#", 1)[0].split(";", 1)[0].strip()
    match = _REQUIREMENT.match(stripped)
    if match is None:
        return None
    remainder = match.group(2).strip()
    if remainder and not _SPECIFIER.match(remainder):
        return None
    return _normalise(match.group(1)), re.sub(r"\s+", "", remainder)


def _strings(value: object) -> list[str]:
    """A pip ``name:`` is a single string or a list of them."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def _sites(key: object, value: object) -> list[tuple[str, list[str]]]:
    """``(context, raw entries)`` for each declaration shape ``key`` opens."""
    found: list[tuple[str, list[str]]] = []
    if key in _PIP_KEYS and isinstance(value, dict):
        found.append((f"{key}:name", _strings(value.get("name"))))
    if key == "packages" and isinstance(value, dict):
        found.append(("packages.python", _strings(value.get("python"))))
    if key == "python_security_updates" and isinstance(value, dict):
        floors = [f"{pkg}>={ver}" for pkg, ver in value.items()]
        found.append(("python_security_updates", floors))
    if isinstance(key, str) and key.endswith("_python_packages") and isinstance(value, list):
        found.append((key, _strings(value)))
    return [(context, entries) for context, entries in found if entries]


def _walk(node: object, path: str, sites: set[tuple[str, str]]) -> list[Declaration]:
    """Every declaration reachable from ``node``, recording the sites it passed."""
    found: list[Declaration] = []
    if isinstance(node, dict):
        for key, value in node.items():
            for context, entries in _sites(key, value):
                sites.add((path, context))
                found.extend(_declarations(path, context, entries))
            found.extend(_walk(value, path, sites))
    elif isinstance(node, list):
        for item in node:
            found.extend(_walk(item, path, sites))
    return found


def _declarations(path: str, context: str, entries: list[str]) -> list[Declaration]:
    parsed = (_split(entry) for entry in entries)
    return [Declaration(path, context, name, spec) for name, spec in filter(None, parsed)]


def ansible_declarations() -> tuple[list[Declaration], set[tuple[str, str]], int]:
    """Every ansible pip declaration, the sites walked, and the documents parsed."""
    declarations: list[Declaration] = []
    sites: set[tuple[str, str]] = set()
    documents = 0
    for path in sorted(_ANSIBLE_ROOT.rglob("*.yml")):
        relative = path.relative_to(_REPO_ROOT).as_posix()
        try:
            loaded = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
        except yaml.YAMLError:
            continue  # a Jinja-templated file ansible renders before parsing
        for document in loaded:
            if document is None:
                continue
            documents += 1
            declarations.extend(_walk(document, relative, sites))
    return declarations, sites, documents


def requirement_files() -> list[pathlib.Path]:
    """The same set ``scripts/check_constraint_drift.py`` guards, plus the SSOT."""
    files: list[pathlib.Path] = []
    seen: set[pathlib.Path] = set()
    for pattern in ("requirements*.txt", "requirements*/*.txt"):
        for path in _REPO_ROOT.rglob(pattern):
            if any(part in _EXCLUDE_DIRS for part in path.parts) or path in seen:
                continue
            seen.add(path)
            files.append(path)
    return sorted(files)


def _specifiers(paths: list[pathlib.Path]) -> dict[str, set[str]]:
    """``package -> every version specifier text stated for it``."""
    stated: dict[str, set[str]] = {}
    for path in paths:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line or line.startswith("-"):
                continue
            parsed = _split(line)
            if parsed is not None and parsed[1]:
                stated.setdefault(parsed[0], set()).add(parsed[1])
    return stated


def requirement_specifiers() -> dict[str, set[str]]:
    return _specifiers(requirement_files() + [_CONSTRAINTS])


def constrained_packages() -> set[str]:
    return set(_specifiers([_CONSTRAINTS]))


def baseline_keys() -> list[str]:
    lines = _BASELINE.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


def divergences() -> dict[str, Declaration]:
    """``path::package -> declaration`` for every ansible version no manifest states."""
    stated = requirement_specifiers()
    found: dict[str, Declaration] = {}
    for declaration in ansible_declarations()[0]:
        versions = stated.get(declaration.package)
        if declaration.specifier and versions and declaration.specifier not in versions:
            found[declaration.key] = declaration
    return found


def test_the_walk_reaches_the_manifests_it_claims_to_read() -> None:
    """A parser that matches nothing would pass every assertion below in silence."""
    declarations, sites, documents = ansible_declarations()
    stated = requirement_specifiers()
    assert documents >= _MIN_ANSIBLE_DOCUMENTS, f"parsed only {documents} ansible documents"
    assert len(sites) >= _MIN_PIP_SITES, f"found only {len(sites)} pip declaration sites"
    assert len(declarations) >= _MIN_ANSIBLE_DECLARATIONS, f"only {len(declarations)} declarations"
    assert len(requirement_files()) >= _MIN_REQUIREMENT_FILES
    assert len(stated) >= _MIN_REQUIREMENT_PACKAGES, f"only {len(stated)} versioned packages"
    assert len(constrained_packages()) >= _MIN_CONSTRAINED_PACKAGES


def test_no_constrained_package_carries_a_version_in_ansible() -> None:
    """`constraints/shared.txt` is the only place a guarded version may be written."""
    guarded = constrained_packages()
    offenders = [
        f"{d.path} [{d.context}] declares {d.package}{d.specifier}"
        for d in ansible_declarations()[0]
        if d.specifier and d.package in guarded
    ]
    assert not offenders, (
        "These ansible sites restate a version constraints/shared.txt already pins.\n  "
        + "\n  ".join(sorted(offenders))
        + "\nFix: drop the specifier and pass "
        "`-c {{ code_source_dir | default('/opt/autobot/code_source') }}/constraints/shared.txt`"
        " in extra_args, as roles/npu-worker and roles/tts-worker do."
    )


def test_every_cross_manifest_divergence_is_in_the_baseline() -> None:
    """A package may not be versioned one way in ansible and another in requirements."""
    stated = requirement_specifiers()
    unlisted = sorted(set(divergences()) - set(baseline_keys()))
    detail = [
        f"{key}: ansible {divergences()[key].specifier}, "
        f"requirements {sorted(stated[divergences()[key].package])}"
        for key in unlisted
    ]
    assert not unlisted, (
        "New ansible/requirements version divergence:\n  "
        + "\n  ".join(detail)
        + f"\nFix the declaration. {_BASELINE.name} only shrinks — adding a line to it"
        " to clear this failure is not the fix (#15568)."
    )


def test_the_baseline_carries_no_stale_entry() -> None:
    """An entry that no longer diverges exempts nothing while looking authoritative."""
    keys = baseline_keys()
    assert len(keys) == len(set(keys)), "duplicate entries in the baseline"
    stale = sorted(set(keys) - set(divergences()))
    assert not stale, (
        "These baseline entries no longer diverge — the declaration was fixed or "
        "removed. Delete them:\n  " + "\n  ".join(stale)
    )
