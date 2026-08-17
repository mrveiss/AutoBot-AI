# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""hardened-smoke-test's inline post-mortem must name whichever container
actually failed, not just `autobot-slm` (#14417).

Before this fix, `.github/workflows/hardened-smoke-test.yml`'s failure
diagnostics step was hardcoded to inspect and log `autobot-slm` only (added
for #11516, where SLM happened to be the failing container). On PR #14413 the
`autobot-backend` container died at import instead: the step printed a
healthy SLM and named nothing, so the traceback that explained the failure
appeared nowhere in the inline job output -- only in the uploaded artifact.

These tests execute the step's actual `run:` script (parsed live from the
workflow file, so there is nothing here to drift out of sync with what CI
runs) against a mocked `docker` CLI, and assert on its *behaviour*: which
container(s) it names and dumps, not on its source text. A source-text-only
check ("does it mention 'autobot-slm'?") would still pass for a hardcoded
step that merely added a second name -- the defect is the hardcoding itself.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml", reason="PyYAML needed to parse the workflow")

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "hardened-smoke-test.yml"
STEP_NAME = "Dump diagnostics for unhealthy containers on failure"

# A standalone fake `docker` executable (not a sourced bash function, so
# `subprocess.run` inheriting only `env=` is sufficient -- no exported-function
# plumbing needed). Driven entirely by MOCK_* env vars set per scenario below.
# Assembled from a plain heredoc-free template rather than any of the actual
# hardened-smoke-test container names being pattern-matched against a lint
# banlist -- there is no such lint here, but keeping the mock data-driven
# (service list + status/health come from env, not literals in this file)
# avoids coupling the test to any future ban on repeating infra names.
_DOCKER_MOCK = textwrap.dedent(
    """\
    #!/usr/bin/env bash
    if [ "$1" = "compose" ]; then
      shift
      joined=" $* "
      if [[ "$joined" == *" config "*"--services"* ]]; then
        for s in $MOCK_SERVICES; do echo "$s"; done
        exit 0
      fi
      if [[ "$joined" == *" logs "* ]]; then
        for last in "$@"; do :; done
        if [[ "$joined" == *"--tail 300"* ]]; then
          status_var="MOCK_STATUS_${last//-/_}"
          if [ -z "${!status_var:-}" ]; then exit 1; fi
          echo "FAKE LOG lines for $last"
          exit 0
        fi
        echo "FAKE full compose log dump"
        exit 0
      fi
      exit 0
    fi
    if [ "$1" = "inspect" ]; then
      svc="$2"
      fmt="$4"
      status_var="MOCK_STATUS_${svc//-/_}"
      health_var="MOCK_HEALTH_${svc//-/_}"
      status="${!status_var:-}"
      health="${!health_var:-none}"
      if [ -z "$status" ]; then exit 1; fi
      case "$fmt" in
        *"json .State.Health"*)
          if [ "$health" = "none" ]; then echo "null"; else echo "{\\"Status\\":\\"$health\\"}"; fi
          exit 0 ;;
        *"ExitCode="*)
          echo "Status=$status ExitCode=0 OOMKilled=false Health=$health"
          exit 0 ;;
        "{{.State.Status}}")
          echo "$status"
          exit 0 ;;
        *)
          echo "$health"
          exit 0 ;;
      esac
    fi
    if [ "$1" = "logs" ]; then
      svc="$4"
      status_var="MOCK_STATUS_${svc//-/_}"
      if [ -z "${!status_var:-}" ]; then exit 1; fi
      echo "FAKE docker logs for $svc"
      exit 0
    fi
    exit 0
    """
)


def _postmortem_script() -> str:
    """Extract the step's `run:` block from the real workflow file."""
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = doc["jobs"]["hardened-smoke-test"]["steps"]
    for step in steps:
        if step.get("name") == STEP_NAME:
            return step["run"]
    raise AssertionError(
        f"no step named {STEP_NAME!r} in {WORKFLOW} -- it was renamed or removed, "
        "update STEP_NAME to match"
    )


@pytest.fixture(scope="module")
def bash():
    path = shutil.which("bash")
    if path is None:
        pytest.skip("bash unavailable")
    return path


@pytest.fixture(scope="module")
def postmortem_script(tmp_path_factory) -> Path:
    script_dir = tmp_path_factory.mktemp("postmortem")
    script_path = script_dir / "postmortem.sh"
    script_path.write_text("#!/usr/bin/env bash\n" + _postmortem_script(), encoding="utf-8")
    script_path.chmod(0o755)
    return script_path


@pytest.fixture(scope="module")
def mock_docker_dir(tmp_path_factory) -> Path:
    bin_dir = tmp_path_factory.mktemp("mockbin")
    docker_path = bin_dir / "docker"
    docker_path.write_text(_DOCKER_MOCK, encoding="utf-8")
    docker_path.chmod(0o755)
    return bin_dir


def _run(bash: str, script: Path, mock_bin: Path, mock_env: dict) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update(mock_env)
    env["PATH"] = f"{mock_bin}:{env.get('PATH', '')}"
    return subprocess.run(
        [bash, str(script)],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )


SERVICES = "autobot-backend autobot-slm autobot-frontend"


def test_names_the_actual_failing_container_not_slm(bash, postmortem_script, mock_docker_dir):
    """Denial-shaped case: backend is unhealthy, SLM is healthy. This is the
    exact shape of PR #14413 that #14417 was filed against."""
    result = _run(
        bash,
        postmortem_script,
        mock_docker_dir,
        {
            "MOCK_SERVICES": SERVICES,
            "MOCK_STATUS_autobot_backend": "exited",
            "MOCK_HEALTH_autobot_backend": "unhealthy",
            "MOCK_STATUS_autobot_slm": "running",
            "MOCK_HEALTH_autobot_slm": "healthy",
            "MOCK_STATUS_autobot_frontend": "running",
            "MOCK_HEALTH_autobot_frontend": "none",
        },
    )
    out = result.stdout

    assert "Containers identified as failing: autobot-backend" in out
    assert "::group::autobot-backend diagnostics" in out
    assert "FAKE LOG lines for autobot-backend" in out
    # The historical bug: this step always dumped SLM regardless of which
    # container actually failed. `not in out` alone passes vacuously against
    # the pre-fix script too (it never emitted `::group::` markers at all),
    # so pin the exact count: exactly one group, for autobot-backend only.
    assert out.count("::group::") == 1, (
        f"expected exactly one diagnostics group (autobot-backend), got "
        f"{out.count('::group::')}:\n{out}"
    )
    assert "::group::autobot-slm diagnostics" not in out, (
        "post-mortem dumped the healthy autobot-slm instead of (or as well as) "
        "the actually-failing autobot-backend -- the hardcoding regressed"
    )


def test_names_every_unhealthy_container_when_several_fail(bash, postmortem_script, mock_docker_dir):
    """Multiple unhealthy containers: both must be named and dumped."""
    result = _run(
        bash,
        postmortem_script,
        mock_docker_dir,
        {
            "MOCK_SERVICES": SERVICES,
            "MOCK_STATUS_autobot_backend": "exited",
            "MOCK_HEALTH_autobot_backend": "unhealthy",
            "MOCK_STATUS_autobot_slm": "running",
            "MOCK_HEALTH_autobot_slm": "healthy",
            # autobot-frontend: no MOCK_STATUS -> "container not found"
        },
    )
    out = result.stdout

    assert "Containers identified as failing: autobot-backend autobot-frontend" in out
    assert "::group::autobot-backend diagnostics" in out
    assert "::group::autobot-frontend diagnostics" in out
    assert "autobot-frontend: container not found (never created)" in out
    # Exactly the two unhealthy ones -- not the healthy autobot-slm, and not
    # a count that would also match a "dump everything" fallback.
    assert out.count("::group::") == 2, (
        f"expected exactly two diagnostics groups (backend, frontend), got "
        f"{out.count('::group::')}:\n{out}"
    )
    assert "::group::autobot-slm diagnostics" not in out


def test_falls_back_to_every_service_when_none_look_unhealthy(bash, postmortem_script, mock_docker_dir):
    """The job failed (this step only runs on `if: failure()`) but nothing in
    compose state looks unhealthy -- e.g. a curl assertion failed. An empty
    post-mortem here is exactly the original bug in a new shape."""
    result = _run(
        bash,
        postmortem_script,
        mock_docker_dir,
        {
            "MOCK_SERVICES": SERVICES,
            "MOCK_STATUS_autobot_backend": "running",
            "MOCK_HEALTH_autobot_backend": "healthy",
            "MOCK_STATUS_autobot_slm": "running",
            "MOCK_HEALTH_autobot_slm": "healthy",
            "MOCK_STATUS_autobot_frontend": "running",
            "MOCK_HEALTH_autobot_frontend": "none",
        },
    )
    out = result.stdout

    assert "No container looked unhealthy" in out
    # `out.strip()` alone would pass vacuously against the pre-fix script too
    # (it always printed the hardcoded SLM block regardless of health) -- the
    # discriminating claim is that EVERY service got named and dumped, not
    # merely that something was printed.
    for svc in SERVICES.split():
        assert f"::group::{svc} diagnostics" in out
    assert out.count("::group::") == len(SERVICES.split()), (
        f"expected a diagnostics group for every one of {SERVICES.split()}, "
        f"got {out.count('::group::')} groups:\n{out}"
    )


def test_step_never_aborts_before_printing_anything(bash, postmortem_script, mock_docker_dir):
    """A `docker inspect`/`docker logs` on a container that never started
    exits non-zero. Under GitHub Actions' default `bash -eo pipefail`, that
    must not abort the step before it names anything."""
    result = _run(
        bash,
        postmortem_script,
        mock_docker_dir,
        {
            "MOCK_SERVICES": SERVICES,
            # No MOCK_STATUS_* set for any service -> every `docker inspect`
            # and `docker logs` call fails.
        },
    )
    assert "Containers identified as failing:" in result.stdout
    for svc in SERVICES.split():
        assert f"{svc}: container not found (never created)" in result.stdout
        assert f"::group::{svc} diagnostics" in result.stdout
    assert result.stdout.count("::group::") == len(SERVICES.split()), (
        f"the loop stopped early instead of reporting every never-created "
        f"container -- got {result.stdout.count('::group::')} of "
        f"{len(SERVICES.split())} groups:\n{result.stdout}"
    )
