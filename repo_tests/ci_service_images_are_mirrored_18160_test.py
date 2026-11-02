# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A CI service container pulls from our mirror, with credentials (#18160).

Service containers pulled `redis:7-alpine` and `postgres:16` anonymously. A burst
of runs exhausted the per-IP pull quota and every job needing a service failed
before any step ran -- red across the board with no code at fault.

`ci-image-mirror.yml` copies those images into `ghcr.io/mrveiss/`. This guard
fails when a `services.*.image` anywhere in `.github/workflows` is not from that
registry, or does not authenticate its pull with `credentials`.

The workflow files are listed with `os.listdir`, not a glob: a glob over
`.github/workflows` would enter the glob-declared and guard-reach censuses for no
gain, and the floor below already binds this guard to what it examined.
"""

from __future__ import annotations

import os

import yaml
from repo_tests._paths import repo_root

WORKFLOWS = repo_root() / ".github" / "workflows"

MIRROR_PREFIX = "ghcr.io/mrveiss/"


def _service_problems(workflow: dict) -> list[str]:
    """`job.service: reason` for every service image that is not mirrored and authenticated."""
    problems = []
    for job_name, job in (workflow.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        for svc_name, svc in (job.get("services") or {}).items():
            if not isinstance(svc, dict):
                continue
            image = str(svc.get("image", ""))
            if not image.startswith(MIRROR_PREFIX):
                problems.append(f"{job_name}.{svc_name}: image {image!r} is not under {MIRROR_PREFIX}")
            if not svc.get("credentials"):
                problems.append(f"{job_name}.{svc_name}: no `credentials`")
    return problems


def _scan() -> tuple[int, int, list[str]]:
    """(workflows parsed, services seen, problems)."""
    parsed = services = 0
    problems: list[str] = []
    for name in sorted(os.listdir(WORKFLOWS)):
        if not name.endswith(".yml"):
            continue
        loaded = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            continue
        parsed += 1
        services += sum(
            len(job.get("services") or {}) for job in (loaded.get("jobs") or {}).values() if isinstance(job, dict)
        )
        problems += [f"{name}: {p}" for p in _service_problems(loaded)]
    return parsed, services, problems


def test_every_service_image_is_mirrored_and_authenticated() -> None:
    parsed, services, problems = _scan()
    # Non-vacuity: a scan that parsed nothing prints the same clean line as a clean tree.
    # Six service blocks existed when this was written (#18160).
    assert parsed >= 40, f"only {parsed} workflows parsed -- the path is wrong"
    assert services >= 6, f"only {services} service containers seen -- the scan is looking at nothing"
    assert not problems, (
        "CI service container pulled anonymously or from a non-mirrored registry:\n  "
        + "\n  ".join(problems)
        + "\n\nAnonymous pulls share a per-IP quota that a burst of runs exhausts. Add the image "
        "to ci-image-mirror.yml, point `image:` at ghcr.io/mrveiss/, and add `credentials:` "
        "with the workflow token (#18160)."
    )


#: The shape the defect took: an anonymous Docker Hub image.
_ANONYMOUS = {"jobs": {"t": {"services": {"redis": {"image": "redis:7-alpine"}}}}}
#: The same service, fixed.
_MIRRORED = {
    "jobs": {
        "t": {
            "services": {
                "redis": {
                    "image": "ghcr.io/mrveiss/ci-redis:7-alpine",
                    "credentials": {"username": "${{ github.actor }}", "password": "${{ secrets.GITHUB_TOKEN }}"},
                }
            }
        }
    }
}


def test_contrast_anonymous_image_is_flagged_and_mirrored_one_passes() -> None:
    assert len(_service_problems(_ANONYMOUS)) == 2  # wrong registry AND no credentials
    assert _service_problems(_MIRRORED) == []


def test_mirrored_image_without_credentials_is_still_flagged() -> None:
    bare = {"jobs": {"t": {"services": {"r": {"image": "ghcr.io/mrveiss/ci-redis:7-alpine"}}}}}
    assert _service_problems(bare) == ["t.r: no `credentials`"]
