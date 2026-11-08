# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A backend-image service that runs the migrating entrypoint must know where Postgres is (#18910).

`docker/backend/entrypoint.sh` always runs Alembic before exec'ing its command (#18729). A compose
service on the backend image that keeps that entrypoint but has no `AUTOBOT_POSTGRES_HOST` migrates
against localhost, exits, and crash-loops: `autobot-celery-beat` did exactly that.
"""

from __future__ import annotations

import yaml
from repo_tests._paths import repo_root

_ROOT = repo_root()
_BACKEND_IMAGE = "autobot/backend"
_BACKEND_DOCKERFILE = "docker/backend/Dockerfile"
_MIGRATING_ENTRYPOINT = "/app/entrypoint.sh"
_POSTGRES_HOST = "AUTOBOT_POSTGRES_HOST"


def _on_backend_image(service: dict) -> bool:
    build = service.get("build")
    dockerfile = build.get("dockerfile", "") if isinstance(build, dict) else ""
    return str(service.get("image", "")).startswith(_BACKEND_IMAGE) or dockerfile == _BACKEND_DOCKERFILE


def _migrates(service: dict) -> bool:
    """No `entrypoint:` key inherits the image's migrating one; an override migrates only if it calls it."""
    if "entrypoint" not in service:
        return True
    entrypoint = service["entrypoint"]
    parts = entrypoint if isinstance(entrypoint, list) else str(entrypoint).split()
    return _MIGRATING_ENTRYPOINT in parts


def _knows_postgres(service: dict) -> bool:
    env = service.get("environment") or []
    names = env.keys() if isinstance(env, dict) else (str(e).split("=", 1)[0] for e in env)
    return _POSTGRES_HOST in set(names)


def migrating_without_postgres(services: dict) -> list[str]:
    return sorted(
        name for name, svc in services.items() if _on_backend_image(svc) and _migrates(svc) and not _knows_postgres(svc)
    )


def test_no_backend_image_service_migrates_blind() -> None:
    services = yaml.safe_load((_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))["services"]
    backend_services = [n for n, s in services.items() if _on_backend_image(s)]
    assert len(backend_services) >= 3, f"enumeration collapsed: {backend_services}"
    assert any(_migrates(services[n]) for n in backend_services), "nothing runs the migrations"
    assert migrating_without_postgres(services) == []


def test_the_detector_fires_on_an_inherited_entrypoint_and_not_on_an_override() -> None:
    blind = {"image": "autobot/backend:latest", "environment": ["AUTOBOT_REDIS_HOST=r"]}
    overridden = {**blind, "entrypoint": []}
    wrapped = {**blind, "entrypoint": ["/bin/sh", "/usr/local/bin/with-secrets.sh", _MIGRATING_ENTRYPOINT]}
    informed = {**wrapped, "environment": [f"{_POSTGRES_HOST}=autobot-postgres"]}
    other_image = {"image": "redis:7"}
    services = {"blind": blind, "overridden": overridden, "wrapped": wrapped, "informed": informed, "x": other_image}
    assert migrating_without_postgres(services) == ["blind", "wrapped"]
