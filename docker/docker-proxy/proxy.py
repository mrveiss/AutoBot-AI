# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The only thing that touches the Docker socket on a compose stack (#20629).

Access to Docker amounts to root on the host, so the SLM doesn't get the socket. It gets this: a
fixed list of actions, on containers of this compose project only. Anything else is refused,
including create and exec, which are what would make it root. Standard library only, so what it can
do is all in this file.
"""

from __future__ import annotations

import hmac
import http.client
import json
import logging
import os
import re
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional
from urllib.parse import quote, urlsplit

logger = logging.getLogger("docker-proxy")  # standard library only: this file ships alone in its image

SOCKET_PATH = os.environ.get("DOCKER_PROXY_SOCKET", "/var/run/docker.sock")
PROJECT_LABEL = "com.docker.compose.project"
ACTIONS = {"start", "stop", "restart"}
#: The SLM and what it needs to run: stopping one from the SLM could leave nobody to start it again.
NEVER_STOP = {"autobot-slm", "autobot-slm-gui", "autobot-slm-postgres", "autobot-postgres", "autobot-redis"}


#: How long a client may take to send or read one request, so a stalled one can't hold a thread.
def _env_seconds(name: str, default: int) -> int:
    """An env value in seconds; a malformed one falls back rather than stopping the proxy at import."""
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


REQUEST_TIMEOUT_SECONDS = _env_seconds("DOCKER_PROXY_REQUEST_TIMEOUT", 30)
_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$")

#: (method, docker path) -> (status, body)
Docker = Callable[[str, str], "tuple[int, bytes]"]


def call_docker(method: str, path: str) -> "tuple[int, bytes]":
    """One request to the Docker API over its socket."""

    class _UnixConnection(http.client.HTTPConnection):
        def connect(self) -> None:
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.sock.settimeout(60)
            self.sock.connect(SOCKET_PATH)

    connection = _UnixConnection("localhost")
    try:
        connection.request(method, path)
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def own_project(docker: Docker, own_id: str) -> str:
    """This stack's project name, from this container's own label. No project, no service."""
    status, body = docker("GET", f"/containers/{quote(own_id)}/json")
    if status != 200:
        raise RuntimeError(f"cannot inspect this container: HTTP {status}")
    project = json.loads(body).get("Config", {}).get("Labels", {}).get(PROJECT_LABEL)
    if not project:
        raise RuntimeError("this container has no compose project label")
    return project


class DockerRefused(Exception):
    """Docker answered an inspect with something other than 200 or 404: not 'no such container'."""

    def __init__(self, status: int) -> None:
        super().__init__(f"docker answered {status}")
        self.status = status


def _inspect_ours(docker: Docker, project: str, name: str) -> Optional[dict]:
    """The container's details if it is in this project; None if absent or not ours."""
    status, body = docker("GET", f"/containers/{quote(name)}/json")
    if status == 404:
        return None
    if status != 200:
        raise DockerRefused(status)
    details = json.loads(body)
    return details if details.get("Config", {}).get("Labels", {}).get(PROJECT_LABEL) == project else None


def _summary(details: dict) -> dict:
    state = details.get("State", {})
    return {
        "name": details.get("Name", "").lstrip("/"),
        "status": state.get("Status"),
        "health": state.get("Health", {}).get("Status"),
        "image": details.get("Config", {}).get("Image"),
    }


def handle(docker: Docker, project: str, own_name: str, method: str, path: str) -> "tuple[int, dict]":
    """The whole allow-list: what a request becomes, or a refusal."""
    parts = path.split("?", 1)[0].strip("/").split("/")
    if parts[0] != "containers" or len(parts) not in (2, 3) or not _NAME.match(parts[1]):
        return 403, {"error": "not allowed"}
    name, verb = parts[1], parts[2] if len(parts) == 3 else None
    if (method, verb) == ("GET", None):
        action = "inspect"
    elif method == "POST" and verb in ACTIONS:
        action = verb
    else:
        return 403, {"error": "not allowed"}
    try:
        details = _inspect_ours(docker, project, name)
    except DockerRefused as refused:
        logger.error("inspect of %s: docker answered %s", name, refused.status)
        return 502, {"error": f"docker answered {refused.status}"}
    if details is None:
        return 404, {"error": "no such container in this stack"}
    if action == "inspect":
        return 200, _summary(details)
    # The name Docker reports, not the URL's: a container id would otherwise skip both checks below.
    resolved = details.get("Name", "").lstrip("/")
    if resolved == own_name:  # it could not answer afterwards, and the SLM would lose its way back
        return 403, {"error": "the proxy does not act on itself"}
    if action == "stop" and resolved in NEVER_STOP:
        return 403, {"error": "this container runs the SLM and can only be restarted"}
    # The id that was just checked, not the name: the name could name another container by the time of the POST.
    container_id = details.get("Id")
    if not container_id:
        return 502, {"error": "docker did not report the container id"}
    status, _body = docker("POST", f"/containers/{quote(container_id)}/{action}")
    if status in (204, 304):  # 304: already in that state
        return 200, {"name": name, "action": action}
    return 502, {"error": f"docker answered {status}"}


def _handled(docker: Docker, project: str, own_name: str, method: str, path: str) -> "tuple[int, dict]":
    """Docker being stopped, or closing the socket mid-answer, is an answer, not a dropped connection.

    #20757: ``http.client.IncompleteRead`` (Docker closed the socket mid-body) is an ``HTTPException``,
    not an ``OSError``; uncaught, the handler sent nothing and the SLM read the proxy as unreachable.
    """
    try:
        return handle(docker, project, own_name, method, path)
    except (OSError, http.client.HTTPException):
        return 503, {"error": "Docker isn't answering"}


def authorized(expected: str, header: Optional[str]) -> bool:
    return bool(expected) and bool(header) and hmac.compare_digest(expected.encode(), header.encode())


def make_handler(token: str, project: str, own_name: str, docker: Docker = call_docker):
    class Handler(BaseHTTPRequestHandler):
        timeout = REQUEST_TIMEOUT_SECONDS

        def _answer(self) -> None:
            if not authorized(token, self.headers.get("X-Docker-Proxy-Token")):
                status, payload = 401, {"error": "token required"}
            else:
                status, payload = _handled(docker, project, own_name, self.command, self.path)
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = _answer
        do_POST = _answer
        do_PUT = _answer
        do_DELETE = _answer

    return Handler


def main() -> None:
    token = os.environ["AUTOBOT_DOCKER_PROXY_TOKEN"]
    own_id = socket.gethostname()
    project = own_project(call_docker, own_id)
    _status, body = call_docker("GET", f"/containers/{quote(own_id)}/json")
    own_name = json.loads(body).get("Name", "").lstrip("/")
    port = urlsplit(os.environ["AUTOBOT_DOCKER_PROXY_URL"]).port
    ThreadingHTTPServer(("", port), make_handler(token, project, own_name)).serve_forever()


if __name__ == "__main__":
    main()
