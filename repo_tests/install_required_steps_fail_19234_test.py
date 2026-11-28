# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A failed required install step stops the installer: no success banner, no install marker (#19234).

A backend health timeout, an HTTPS endpoint that never answered, a refused admin login and a
failed node registration each only warned, and `finalize` then wrote the install marker and
printed "AutoBot SLM Installation Complete!". The marker also made a rerun exit 100 unless
`--reinstall` was passed, so the broken install stuck.

These tests run install.sh's real `service_verification`, `register_local_node` and `finalize`,
in that order, with the outside world stubbed: systemctl, nginx, sleep, jq and curl, whose
answers each scenario sets. The marker and credentials paths point into a temp dir.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

_INSTALL = repo_root() / "install.sh"
_BASH = shutil.which("bash")


def _function(source: str, name: str) -> str:
    match = re.search(rf"^{name}\(\) \{{.*?^\}}$", source, re.M | re.S)
    assert match, f"install.sh no longer defines {name}()"
    return match.group(0)


_CURL = r"""
curl() {
    local args="$*"
    case "${args}" in
        *127.0.0.1:8000/api/health*) [[ "${HEALTH}" == ok ]] ;;
        *api/auth/login*) [[ "${LOGIN}" == ok ]] && echo '{"access_token":"t"}' || echo '{}' ;;
        *api/nodes*) printf '%s' "${NODES}" ;;
        *code-source/assign*) printf '200' ;;
        *api/health*) [[ "${HTTPS}" == ok ]] ;;
        *) return 7 ;;
    esac
}
"""


def _run(tmp_path: Path, **answers: str) -> tuple[subprocess.CompletedProcess, Path]:
    if _BASH is None:
        pytest.skip("bash unavailable")
    source = _INSTALL.read_text(encoding="utf-8")
    finalize = _function(source, "finalize").replace("/root/autobot-credentials.txt", str(tmp_path / "credentials.txt"))
    helpers = "\n".join(
        line for line in source.splitlines() if re.match(r"^(log|info|success|warn|error|fatal)\(\)", line)
    )
    marker = tmp_path / "installed"
    env = {"HEALTH": "ok", "HTTPS": "ok", "LOGIN": "ok", "NODES": "201", **answers}
    script = "\n".join(
        [
            "set -euo pipefail",
            'RED="" GREEN="" YELLOW="" BLUE="" CYAN="" NC=""',
            f'LOG_FILE="{tmp_path}/install.log" INSTALL_MARKER="{marker}" IP_CACHE_FILE="{tmp_path}/ip-cache"',
            "SCRIPT_VERSION=t GIT_BRANCH=main AUTOBOT_USER=autobot ADMIN_PASSWORD=x ADMIN_PASSWORD_GENERATED=false ADMIN_PASSWORD_PRESERVED=false SECRETS_FILE=s CODE_SOURCE=c",
            "SLM_NODE_ID=00-SLM-Manager SLM_BACKEND_PORT=8000",
            helpers,
            'phase() { echo "== $*"; }',
            "systemctl() { return 0; }",
            "nginx() { return 0; }",
            "sleep() { :; }",
            "chown() { :; }",
            "detect_local_ip() { echo 127.0.0.1; }",
            'jq() { sed -n \'s/.*"access_token":"\\([^"]*\\)".*/\\1/p\'; }',
            _CURL,
            _function(source, "service_verification"),
            _function(source, "wait_for_https"),
            _function(source, "register_local_node"),
            finalize,
            "service_verification",
            "register_local_node",
            "finalize",
        ]
    )
    done = subprocess.run(
        [_BASH, "-c", script], capture_output=True, text=True, timeout=60, env={"PATH": "/usr/bin:/bin", **env}
    )
    return done, marker


@pytest.mark.parametrize(
    ("answers", "step"),
    [
        ({"HEALTH": "down"}, "SLM backend health"),
        ({"HTTPS": "down"}, "HTTPS endpoint"),
        ({"LOGIN": "refused"}, "admin login"),
        ({"NODES": "500"}, "node registration"),
    ],
)
def test_a_failed_required_step_stops_the_install_without_a_marker(tmp_path, answers, step) -> None:
    done, marker = _run(tmp_path, **answers)
    output = done.stdout + done.stderr
    assert done.returncode != 0, f"the install reported success after '{step}' failed"
    assert f"Step '{step}' failed" in output, output[-600:]
    assert "rerun this installer" in output, "the failure does not say how to recover"
    assert "Installation Complete!" not in output
    assert not marker.exists(), "a marker was written, so a rerun would exit 100 without --reinstall"


def test_a_clean_run_prints_the_banner_and_writes_the_marker(tmp_path) -> None:
    done, marker = _run(tmp_path)
    assert done.returncode == 0, done.stderr[-600:]
    assert "Installation Complete!" in done.stdout and marker.exists()


def test_an_already_registered_node_is_still_a_success(tmp_path) -> None:
    done, marker = _run(tmp_path, NODES="400")
    assert done.returncode == 0 and marker.exists(), done.stderr[-600:]


def test_the_optional_code_source_step_is_labelled_optional() -> None:
    assert "Optional step 'code source'" in _INSTALL.read_text(encoding="utf-8")
