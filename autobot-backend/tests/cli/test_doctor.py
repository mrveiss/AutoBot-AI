# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for autobot doctor health checks.

Issue #7371: each repair is a discrete idempotent function with a unit test.
"""

from autobot_shared.paths import project_root
from cli.doctor import (
    DoctorCheckResult,
    check_env_file,
    check_redis_schemas,
    run_environment_doctor,
)


def test_check_result_ok():
    r = DoctorCheckResult(name="test", ok=True, message="OK")
    assert r.ok
    assert not r.fixable


def test_check_result_fixable():
    fixed = []
    r = DoctorCheckResult(name="test", ok=False, message="broken", fixable=True, fix=lambda: fixed.append(1))
    assert r.fixable
    r.fix()
    assert fixed == [1]


def test_check_env_file_missing(tmp_path):
    result = check_env_file(str(tmp_path / "nonexistent.env"))
    assert not result.ok
    assert "not found" in result.message


def test_check_env_file_default_is_not_the_live_install():
    """#13149: the default used to be a hardcoded `/opt/autobot` literal, so
    the diagnostic always read the live install's `.env` regardless of which
    checkout invoked it. Calling with no arg (as ALL_CHECKS does) must not
    resolve under /opt/autobot."""
    result = check_env_file()

    assert "/opt/autobot" not in result.message


def test_check_env_file_default_is_wired_to_the_canonical_resolver():
    result = check_env_file()

    expected = str(project_root() / "autobot-backend" / ".env")
    assert expected in result.message


def test_check_env_file_default_tracks_project_root_env_override(monkeypatch, tmp_path):
    fake_root = tmp_path / "fake-checkout"
    (fake_root / "autobot-backend").mkdir(parents=True)
    monkeypatch.setenv("AUTOBOT_PROJECT_ROOT", str(fake_root))

    result = check_env_file()

    assert str(fake_root / "autobot-backend" / ".env") in result.message


def test_check_env_file_default_matches_original_literal_when_deployed(monkeypatch):
    """Compositional check for the deployed case — see the equivalent test in
    ``source_paths_test.py`` for why AUTOBOT_PROJECT_ROOT stands in for the
    real ``.env``-walk here, and why full host verification is out of scope
    for a hermetic test.

    Whether this dev machine can even stat ``/opt/autobot`` varies (it may
    not exist, or exist with restricted permissions owned by the deployed
    service account) — either way the diagnostic must fail closed and name
    the exact path the original hardcoded literal pointed at, proving the
    composed default is unchanged for a real deployment.
    """
    monkeypatch.setenv("AUTOBOT_PROJECT_ROOT", "/opt/autobot")

    result = check_env_file()

    assert result.ok is False
    assert "/opt/autobot/autobot-backend/.env" in result.message


def test_check_env_file_ok(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "OLLAMA_HOST=http://localhost:11434\n" "REDIS_URL=redis://localhost\n" "CHROMADB_HOST=localhost\n"
    )  # canonical: ignore py-hardcoded-url — test fixture/mock URL, not an executable default
    result = check_env_file(str(env))
    assert result.ok


def test_check_env_file_missing_var(tmp_path):
    env = tmp_path / ".env"
    env.write_text("REDIS_URL=redis://localhost\nCHROMADB_HOST=localhost\n")
    result = check_env_file(str(env))
    assert not result.ok
    assert "OLLAMA_HOST" in result.message


def test_run_doctor_all_pass(capsys, monkeypatch):
    def fake_check():
        return DoctorCheckResult(name="fake", ok=True, message="fake: OK")

    monkeypatch.setattr("cli.doctor.ALL_CHECKS", [fake_check])
    rc = run_environment_doctor(fix=False)
    assert rc == 0
    out = capsys.readouterr().out
    assert "All checks passed" in out


def test_run_doctor_failure_no_fix(capsys, monkeypatch):
    def fake_check():
        return DoctorCheckResult(name="fake", ok=False, message="fake: broken", fixable=False)

    monkeypatch.setattr("cli.doctor.ALL_CHECKS", [fake_check])
    rc = run_environment_doctor(fix=False)
    assert rc == 1


def test_run_doctor_fix_fixable(capsys, monkeypatch):
    fixed = []

    def fake_check():
        return DoctorCheckResult(
            name="fake",
            ok=False,
            message="broken",
            fixable=True,
            fix=lambda: fixed.append(1),
        )

    monkeypatch.setattr("cli.doctor.ALL_CHECKS", [fake_check])
    rc = run_environment_doctor(fix=True)
    assert fixed == [1]
    assert rc == 0


def test_run_doctor_fix_manual_items_return_1(capsys, monkeypatch):
    """--fix should still return 1 when non-fixable failures remain."""

    def fake_check():
        return DoctorCheckResult(name="manual", ok=False, message="manual fix needed", fixable=False)

    monkeypatch.setattr("cli.doctor.ALL_CHECKS", [fake_check])
    rc = run_environment_doctor(fix=True)
    assert rc == 1


def test_check_redis_schemas_import_error(monkeypatch):
    """If redis is not importable, check returns ok=False."""
    import builtins

    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "redis":
            raise ImportError("No module named 'redis'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)
    result = check_redis_schemas()
    assert not result.ok
    assert "Redis unreachable" in result.message


def _captured_npu_url(monkeypatch):
    """Run check_npu_worker_registry with urlopen stubbed; return the URL it probed."""
    import urllib.request

    from cli.doctor import check_npu_worker_registry

    seen = []

    def _fake_urlopen(url, timeout=None):
        seen.append(url)
        raise OSError("stubbed")

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
    check_npu_worker_registry()
    return seen[0]


def test_npu_doctor_default_port_is_the_ssot_value(monkeypatch):
    """#18094: the default was a literal 8080 while the worker serves the ssot port."""
    from autobot_shared.ssot_config import config as ssot_config

    monkeypatch.delenv("NPU_WORKER_PORT", raising=False)
    monkeypatch.delenv("AUTOBOT_NPU_WORKER_PORT", raising=False)

    assert _captured_npu_url(monkeypatch).endswith(f":{ssot_config.port.npu}/health")


def test_npu_doctor_still_honours_legacy_port_env(monkeypatch):
    monkeypatch.delenv("AUTOBOT_NPU_WORKER_PORT", raising=False)
    monkeypatch.setenv("NPU_WORKER_PORT", "9123")

    assert _captured_npu_url(monkeypatch).endswith(":9123/health")


def test_npu_doctor_maps_a_wildcard_legacy_host_to_loopback(monkeypatch):
    """#18094: NPU_WORKER_HOST=0.0.0.0 is the worker's bind address, not dialable."""
    monkeypatch.delenv("AUTOBOT_NPU_WORKER_HOST", raising=False)
    monkeypatch.setenv("NPU_WORKER_HOST", "0.0.0.0")

    assert _captured_npu_url(monkeypatch).startswith("http://127.0.0.1:")


def test_npu_doctor_still_honours_a_legacy_connect_host(monkeypatch):
    monkeypatch.delenv("AUTOBOT_NPU_WORKER_HOST", raising=False)
    monkeypatch.setenv("NPU_WORKER_HOST", "npu-box.internal")

    assert _captured_npu_url(monkeypatch).startswith("http://npu-box.internal:")


def test_npu_doctor_ssot_host_wins_over_the_legacy_name(monkeypatch):
    from autobot_shared.ssot_config import config as ssot_config

    monkeypatch.setenv("AUTOBOT_NPU_WORKER_HOST", "ignored-by-the-cached-singleton")
    monkeypatch.setenv("NPU_WORKER_HOST", "npu-box.internal")

    assert _captured_npu_url(monkeypatch).startswith(f"http://{ssot_config.vm.npu}:")


def test_npu_doctor_default_host_is_the_ssot_value(monkeypatch):
    from autobot_shared.ssot_config import config as ssot_config

    monkeypatch.delenv("AUTOBOT_NPU_WORKER_HOST", raising=False)
    monkeypatch.delenv("NPU_WORKER_HOST", raising=False)

    assert _captured_npu_url(monkeypatch).startswith(f"http://{ssot_config.vm.npu}:")
