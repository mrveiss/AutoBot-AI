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

from tools.lint._comment_syntax import code_lines, code_text

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
    """Both SLM-only configs, plain and TLS (#18593), include nothing that names the backend."""
    for conf in {*_closure("nginx-slm.conf"), *_closure("nginx-slm-ssl.conf")}:
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
    for name, top in (
        ("autobot-frontend", "nginx.conf"),
        ("autobot-frontend", "nginx-ssl.conf"),  # the TLS switch must find its includes too (#18593)
        ("autobot-slm-gui", "nginx-slm.conf"),
        ("autobot-slm-gui", "nginx-slm-ssl.conf"),
    ):
        needed = set(_closure(top)) - {top}
        assert needed <= _mounted(services[name]), (name, sorted(needed - _mounted(services[name])))


def test_production_stays_the_default_dockerfile_target() -> None:
    stages = re.findall(
        r"^FROM\s+\S+\s+AS\s+(\S+)", (_ROOT / "docker/frontend/Dockerfile").read_text(encoding="utf-8"), re.M
    )
    assert "slm-gui" in stages
    assert stages[-1] == "production", stages


# --- the SLM-only GUI has a TLS option (#18593) ---


def test_the_slm_gui_switches_to_tls_like_the_frontend() -> None:
    gui = _services()["autobot-slm-gui"]
    volumes = gui["volumes"]
    assert "${AUTOBOT_DOCKER_SLM_NGINX_CONF:-./docker/nginx/nginx-slm.conf}:/etc/nginx/nginx.conf:ro" in volumes
    assert "./docker/certs:/etc/nginx/certs:ro" in volumes, "the TLS config would find no certificate"
    assert "80:80" in gui["ports"]
    assert "${AUTOBOT_DOCKER_SLM_HTTPS_PORT:-443}:443" in gui["ports"], "a taken host port 443 must not block start"


def test_tls_settings_are_defined_once() -> None:
    """Both TLS configs take their settings and port-80 server from the shared includes."""
    for top in ("nginx-ssl.conf", "nginx-slm-ssl.conf"):
        closure = _closure(top)
        assert {"nginx-tls.conf", "nginx-tls-redirect.conf"} <= set(closure), (top, closure)
    served = {
        c for top in ("nginx.conf", "nginx-ssl.conf", "nginx-slm.conf", "nginx-slm-ssl.conf") for c in _closure(top)
    }
    defining = sorted(
        c for c in served if re.search(r"^\s*ssl_protocols\s", (_NGINX / c).read_text(encoding="utf-8"), re.M)
    )
    assert defining == ["nginx-tls.conf"], f"TLS settings copied outside nginx-tls.conf: {defining}"


def test_the_tls_redirect_keeps_the_healthcheck_on_plain_http() -> None:
    """The container healthcheck fetches http://localhost/health; a redirect to a self-signed
    HTTPS endpoint would fail it, so /health is answered on port 80."""
    text = (_NGINX / "nginx-tls-redirect.conf").read_text(encoding="utf-8")
    assert re.search(r"location\s*=\s*/health\s*\{[^}]*return 200", text), text
    assert re.search(r"location\s*/\s*\{\s*return 301 https://", text), text
    for name in ("autobot-frontend", "autobot-slm-gui"):
        assert "http://localhost/health" in " ".join(_services()[name]["healthcheck"]["test"]), name


def _servers(text: str) -> list[str]:
    """The bodies of the `server { ... }` blocks in an nginx config (brace-matched)."""
    out, i = [], 0
    while (m := re.search(r"\bserver\s*\{", text[i:])) is not None:
        start = depth = i + m.end()
        level = 1
        while level:
            level += {"{": 1, "}": -1}.get(text[depth], 0)
            depth += 1
        out.append(text[start : depth - 1])
        i = depth
    return out


def tls_leaks(files: dict[str, str]) -> list[str]:
    """TLS-only material outside a `listen 443 ssl` server (01's review, #18593)."""
    leaks = []
    # Comments stripped first: a comment naming HSTS, ssl_ or holding a brace is not config.
    files = {name: code_text(text, name=name, strip_trailing=True) for name, text in files.items()}
    redirect = files.get("nginx-tls-redirect.conf", "")
    if re.search(r"Strict-Transport-Security|^\s*ssl_", redirect, re.M | re.I):
        leaks.append("nginx-tls-redirect.conf carries HSTS or an ssl_ directive")
    for name, text in files.items():
        for body in _servers(text):
            if "nginx-tls.conf" in body and not re.search(r"listen\s+443\s+ssl", body):
                leaks.append(f"{name}: nginx-tls.conf included in a server without `listen 443 ssl`")
    return leaks


def test_tls_material_never_reaches_a_plain_http_server() -> None:
    files = {p.name: p.read_text(encoding="utf-8") for p in (_NGINX / n for n in _served_closure())}
    assert not tls_leaks(files)


def _served_closure() -> set[str]:
    return {
        c for top in ("nginx.conf", "nginx-ssl.conf", "nginx-slm.conf", "nginx-slm-ssl.conf") for c in _closure(top)
    }


def test_the_tls_leak_check_sees_both_shapes() -> None:
    redirect_bad = "server { listen 80; add_header Strict-Transport-Security $hsts always; }"
    plain_include = "http { server { listen 80; include /etc/nginx/nginx-tls.conf; } }"
    good = "http { server { listen 443 ssl http2; include /etc/nginx/nginx-tls.conf; } }"
    assert tls_leaks({"nginx-tls-redirect.conf": redirect_bad}) == [
        "nginx-tls-redirect.conf carries HSTS or an ssl_ directive"
    ]
    assert tls_leaks({"x.conf": plain_include}) == [
        "x.conf: nginx-tls.conf included in a server without `listen 443 ssl`"
    ]
    assert tls_leaks({"x.conf": good}) == []
    commented = (
        "# the HTTPS server sets Strict-Transport-Security; no ssl_ here { not a block\n"
        "server { listen 80; return 301 https://$host$request_uri; }  # nginx-tls.conf is 443-only }\n"
    )
    assert tls_leaks({"nginx-tls-redirect.conf": commented}) == []
    braces = "http {\n  # a stray } in a comment\n  server { listen 80; include /etc/nginx/nginx-tls.conf; }\n}\n"
    assert tls_leaks({"y.conf": braces}) == ["y.conf: nginx-tls.conf included in a server without `listen 443 ssl`"]


def test_hsts_is_scheme_gated_wherever_a_location_repeats_it() -> None:
    """Locations repeat security headers (nginx does not inherit add_header). HSTS there must be
    the $hsts map, which is empty -- so not sent -- on plain HTTP; a literal value would leak it."""
    common = (_NGINX / "nginx-common.conf").read_text(encoding="utf-8")
    assert re.search(r"map\s+\$scheme\s+\$hsts\s*\{[^}]*https\s+\"max-age=[^}]*default\s+\"\"", common), common
    for name in _served_closure():
        for line in code_lines(_NGINX / name):
            if "Strict-Transport-Security" in line.text:
                assert "$hsts" in line.text, f"{name}: HSTS with a literal value: {line.text.strip()}"
