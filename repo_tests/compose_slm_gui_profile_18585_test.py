# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The Docker stack can start the SLM web GUI alone, and never pulls its own images (#18584, #18585).

An external install test found no way to bring up only the SLM GUI: the full
stack was the only documented route and it exhausted a small host (#18585). The
same run hit "pull access denied" for autobot/backend, which autobot-celery-beat
named with no `build:` (#18584).

nginx resolves `upstream` hosts at startup, so an SLM-only nginx that names
autobot-backend would never start. The include graph is walked from the real
files: a test that read only nginx-slm.conf would pass while an include it pulls
in named the backend.

**What these do not cover.** That the containers actually start, and what they
use in memory. The hardened-smoke-test workflow starts the slm profile alone and
prints `docker stats` for that.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from repo_tests._paths import repo_root

_ROOT = repo_root()
_NGINX = _ROOT / "docker" / "nginx"
_HEAVY = {"autobot-backend", "autobot-worker", "autobot-celery-beat", "autobot-chromadb", "autobot-frontend"}


def _services() -> dict:
    return yaml.safe_load((_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))["services"]


def _includes(conf: str) -> list[str]:
    text = (_NGINX / conf).read_text(encoding="utf-8")
    return [Path(p).name for p in re.findall(r"^\s*include\s+/etc/nginx/(nginx-[\w-]+\.conf);", text, re.M)]


def _closure(conf: str) -> list[str]:
    seen: list[str] = []
    todo = [conf]
    while todo:
        name = todo.pop()
        if name not in seen:
            seen.append(name)
            todo.extend(_includes(name))
    return seen


def _deps(services: dict, name: str) -> set[str]:
    out: set[str] = set()
    todo = [name]
    while todo:
        for dep in services[todo.pop()].get("depends_on") or {}:
            if dep not in out:
                out.add(dep)
                todo.append(dep)
    return out


def test_every_locally_built_image_is_built_by_the_service_naming_it() -> None:
    services = _services()
    missing = [n for n, s in services.items() if str(s.get("image", "")).startswith("autobot/") and "build" not in s]
    assert not missing, f"these services name an autobot/* image with no build:, so compose may pull it: {missing}"


def test_the_slm_gui_is_profiled_and_pulls_in_no_platform_service() -> None:
    services = _services()
    gui = services["autobot-slm-gui"]
    assert gui["profiles"] == ["slm"]
    assert gui["build"]["target"] == "slm-gui"
    deps = _deps(services, "autobot-slm-gui")
    assert "autobot-slm" in deps
    assert not deps & _HEAVY, f"the SLM-only path starts platform services: {sorted(deps & _HEAVY)}"


def test_the_slm_only_nginx_never_names_the_main_backend() -> None:
    for conf in _closure("nginx-slm.conf"):
        text = (_NGINX / conf).read_text(encoding="utf-8")
        assert "autobot-backend" not in text and "http://backend" not in text, conf


def test_full_stack_configs_still_define_the_backend_upstream() -> None:
    for top in ("nginx.conf", "nginx-ssl.conf"):
        assert "nginx-backend-upstream.conf" in _closure(top), top


def _mounted(service: dict) -> set[str]:
    return {Path(v.rsplit(":", 2)[1]).name for v in service.get("volumes", []) if ":/etc/nginx/nginx" in v}


def test_each_nginx_service_mounts_every_file_its_config_includes() -> None:
    """A compose mount overrides the image copy; a missing one leaves an include stale."""
    services = _services()
    for name, top in (("autobot-frontend", "nginx.conf"), ("autobot-slm-gui", "nginx-slm.conf")):
        needed = set(_closure(top)) - {top}
        assert needed <= _mounted(services[name]), (name, sorted(needed - _mounted(services[name])))


def test_production_stays_the_default_dockerfile_target() -> None:
    stages = re.findall(
        r"^FROM\s+\S+\s+AS\s+(\S+)", (_ROOT / "docker/frontend/Dockerfile").read_text(encoding="utf-8"), re.M
    )
    assert "slm-gui" in stages
    assert stages[-1] == "production", stages
