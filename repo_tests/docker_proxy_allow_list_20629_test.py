# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20629: the proxy allows only the listed actions, on this stack's containers only."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("_docker_proxy", _ROOT / "docker" / "docker-proxy" / "proxy.py")
proxy = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(proxy)

_OURS = {
    "Name": "/autobot-redis",
    "Config": {"Labels": {proxy.PROJECT_LABEL: "stack"}, "Image": "i"},
    "State": {"Status": "running", "Health": {"Status": "healthy"}},
}
_THEIRS = {"Name": "/other", "Config": {"Labels": {proxy.PROJECT_LABEL: "other"}}, "State": {}}


class _Docker:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def __call__(self, method: str, path: str):
        self.calls.append((method, path))
        if method == "POST":
            return 204, b""
        if path.endswith("/logs?stdout=1&stderr=1&tail=200"):
            return 200, b"a line"
        if "/containers/autobot-" in path:
            return 200, json.dumps(_OURS).encode()
        if "/containers/other/" in path:
            return 200, json.dumps(_THEIRS).encode()
        return 404, b""


def _ask(method: str, path: str):
    docker = _Docker()
    return *proxy.handle(docker, "stack", "autobot-docker-proxy", method, path), docker.calls


@pytest.mark.parametrize("action", ["start", "stop", "restart"])
def test_listed_actions_reach_docker_on_our_container(action) -> None:
    status, _, calls = _ask("POST", f"/containers/autobot-backend/{action}")
    assert status == 200 and ("POST", f"/containers/autobot-backend/{action}") in calls


def test_inspect_gives_only_a_summary_never_the_environment() -> None:
    status, payload, _ = _ask("GET", "/containers/autobot-redis")
    assert status == 200 and payload == {
        "name": "autobot-redis",
        "status": "running",
        "health": "healthy",
        "image": "i",
    }


def test_logs_are_bounded() -> None:
    assert _ask("GET", "/containers/autobot-redis/logs")[1] == {"logs": "a line"}


@pytest.mark.parametrize(
    "method, path",
    [
        ("POST", "/containers/create"),
        ("POST", "/containers/autobot-redis/exec"),
        ("POST", "/containers/autobot-redis/kill"),
        ("POST", "/containers/autobot-redis/update"),
        ("DELETE", "/containers/autobot-redis"),
        ("GET", "/containers/autobot-redis/archive"),
        ("POST", "/images/create"),
        ("POST", "/volumes/create"),
        ("GET", "/containers/json"),
        ("POST", "/containers/autobot-redis/../other/restart"),
        ("GET", "/version"),
    ],
)
def test_everything_else_is_refused_before_a_write_reaches_docker(method, path) -> None:
    status, _, calls = _ask(method, path)
    assert status in (403, 404)
    assert not [call for call in calls if call[0] != "GET"]


def test_another_projects_container_is_refused() -> None:
    status, _, calls = _ask("POST", "/containers/other/restart")
    assert status == 404 and ("POST", "/containers/other/restart") not in calls


@pytest.mark.parametrize("name", sorted(proxy.NEVER_STOP))
def test_what_runs_the_slm_can_be_restarted_but_not_stopped(name) -> None:
    assert _ask("POST", f"/containers/{name}/stop")[0] == 403
    assert _ask("POST", f"/containers/{name}/restart")[0] == 200


def test_the_proxy_does_not_act_on_itself() -> None:
    assert _ask("POST", "/containers/autobot-docker-proxy/stop")[0] == 403


@pytest.mark.parametrize("header", [None, "", "wrong"])
def test_a_wrong_token_is_refused(header) -> None:
    assert proxy.authorized("right", header) is False
    assert proxy.authorized("", header) is False


def test_only_the_proxy_has_the_socket_and_only_the_slm_shares_its_network() -> None:
    services = yaml.safe_load((_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))["services"]
    with_socket = [n for n, s in services.items() if any("docker.sock" in str(v) for v in s.get("volumes", []))]
    assert with_socket == ["autobot-docker-proxy"]
    sharing = [n for n, s in services.items() if "autobot-docker-control" in (s.get("networks") or [])]
    assert sorted(sharing) == ["autobot-docker-proxy", "autobot-slm"]
    assert "ports" not in services["autobot-docker-proxy"]
