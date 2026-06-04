# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for autobot doctor health checks.

Issue #7371: each repair is a discrete idempotent function with a unit test.
"""

from cli.doctor import (
    CheckResult,
    check_env_file,
    check_redis_schemas,
    run_doctor,
)


def test_check_result_ok():
    r = CheckResult(name="test", ok=True, message="OK")
    assert r.ok
    assert not r.fixable


def test_check_result_fixable():
    fixed = []
    r = CheckResult(name="test", ok=False, message="broken", fixable=True, fix=lambda: fixed.append(1))
    assert r.fixable
    r.fix()
    assert fixed == [1]


def test_check_env_file_missing(tmp_path):
    result = check_env_file(str(tmp_path / "nonexistent.env"))
    assert not result.ok
    assert "not found" in result.message


def test_check_env_file_ok(tmp_path):
    env = tmp_path / ".env"
    env.write_text("OLLAMA_HOST=http://localhost:11434\n" "REDIS_URL=redis://localhost\n" "CHROMADB_HOST=localhost\n")
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
        return CheckResult(name="fake", ok=True, message="fake: OK")

    monkeypatch.setattr("cli.doctor.ALL_CHECKS", [fake_check])
    rc = run_doctor(fix=False)
    assert rc == 0
    out = capsys.readouterr().out
    assert "All checks passed" in out


def test_run_doctor_failure_no_fix(capsys, monkeypatch):
    def fake_check():
        return CheckResult(name="fake", ok=False, message="fake: broken", fixable=False)

    monkeypatch.setattr("cli.doctor.ALL_CHECKS", [fake_check])
    rc = run_doctor(fix=False)
    assert rc == 1


def test_run_doctor_fix_fixable(capsys, monkeypatch):
    fixed = []

    def fake_check():
        return CheckResult(
            name="fake",
            ok=False,
            message="broken",
            fixable=True,
            fix=lambda: fixed.append(1),
        )

    monkeypatch.setattr("cli.doctor.ALL_CHECKS", [fake_check])
    rc = run_doctor(fix=True)
    assert fixed == [1]


def test_run_doctor_fix_manual_items_return_1(capsys, monkeypatch):
    """--fix should still return 1 when non-fixable failures remain."""

    def fake_check():
        return CheckResult(name="manual", ok=False, message="manual fix needed", fixable=False)

    monkeypatch.setattr("cli.doctor.ALL_CHECKS", [fake_check])
    rc = run_doctor(fix=True)
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
