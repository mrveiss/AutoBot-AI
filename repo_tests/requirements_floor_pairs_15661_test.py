# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Two non-shipping manifests must track their shipped fastapi/uvicorn floor (#15661).

`docs/guides/requirements-local.txt` and
`autobot-npu-worker/resources/windows-npu-worker/requirements.txt` both fell
behind the fastapi/uvicorn security floor every SHIPPED manifest states
(fastapi requires starlette >=0.52.1, the O(n^2) Range-header DoS fix) --
undetected because the per-site ansible/requirements parity guard
(`repo_tests/ansible_requirements_parity_test.py`) and the constrained-package
guard (`scripts/check_constraint_drift.py`) both only ever compare an ansible
site or a `constraints/shared.txt` package, and neither of these two files is
either. This is the general-case guard AC3 asks for: a direct, narrow
comparison of just these two known-risky pairs, not a repo-wide migration of
fastapi/uvicorn onto `constraints/shared.txt` (which would force every
shipped manifest -- a dozen-plus files -- to stop stating its own floor, a
much larger change than this issue's actual defect warrants).

Only the version constraint is compared, not the full declaration line:
`docs/guides/requirements-local.txt` legitimately carries `uvicorn[standard]`
where `autobot-backend/requirements.txt` carries bare `uvicorn` (matching most
other shipped manifests) -- the extras differ on purpose, the FLOOR must not.
"""

from __future__ import annotations

import re

from repo_tests._paths import repo_root

_REPO_ROOT = repo_root()

# (file whose floor must not fall behind, its reference sibling, packages to compare)
_PAIRS = (
    (
        "docs/guides/requirements-local.txt",
        "autobot-backend/requirements.txt",
        ("fastapi", "uvicorn"),
    ),
    (
        "autobot-npu-worker/resources/windows-npu-worker/requirements.txt",
        "autobot-infrastructure/autobot-npu-worker/docker/requirements-npu.txt",
        ("fastapi", "uvicorn"),
    ),
)

_EXTRAS_RE = re.compile(r"\[[^\]]*\]")


def _version_spec(path_text: str, package: str) -> str | None:
    """The version-constraint text for *package* in *path_text*, extras stripped."""
    for raw in path_text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        name_and_rest = _EXTRAS_RE.sub("", line, count=1)
        if not name_and_rest.lower().startswith(package.lower()):
            continue
        rest = name_and_rest[len(package) :]
        if rest and rest[0] not in "><=!~":
            continue  # a different package this one merely prefixes
        return rest.strip()
    return None


def test_the_known_pairs_and_packages_still_exist() -> None:
    """A path or package that stopped existing would make the guard below vacuous."""
    missing = []
    for target, reference, packages in _PAIRS:
        for rel_path in (target, reference):
            if not (_REPO_ROOT / rel_path).is_file():
                missing.append(rel_path)
        text = (_REPO_ROOT / reference).read_text(encoding="utf-8")
        for pkg in packages:
            if _version_spec(text, pkg) is None:
                missing.append(f"{reference}::{pkg}")
    assert not missing, f"expected these to exist: {missing}"


def test_no_pair_falls_behind_its_reference_floor() -> None:
    offenders = []
    for target, reference, packages in _PAIRS:
        target_text = (_REPO_ROOT / target).read_text(encoding="utf-8")
        reference_text = (_REPO_ROOT / reference).read_text(encoding="utf-8")
        for pkg in packages:
            target_spec = _version_spec(target_text, pkg)
            reference_spec = _version_spec(reference_text, pkg)
            if target_spec != reference_spec:
                offenders.append(f"{target}: {pkg}{target_spec!r} vs {reference}: {pkg}{reference_spec!r}")

    assert not offenders, (
        f"{offenders} -- these floors must move together (#15661); a shipped manifest's "
        "security floor bump must be mirrored here, not just where CI happens to look."
    )
