# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The audit worker's filing credential must be owned, not ambient (#13859).

The worker filed GitHub issues by shelling out to `gh` and relying entirely on
whatever CLI session existed for the account Celery happened to run as. Nothing
owned that credential, nothing rotated it, nothing audited its use, and the only
place its absence surfaced was a log line — which is precisely how it lapsed
unnoticed in #13570, where findings were queued for days while every clean run
looked identical to a healthy one.

CLAUDE.md requires credentials to travel via the canonical secrets manager under
grant/audit/revocation, never as ambient state on a host.
"""

from __future__ import annotations

import importlib

import pytest

audit_tasks = importlib.import_module("workers.audit_tasks")


@pytest.fixture(autouse=True)
def _clean_cache():
    audit_tasks.reset_gh_env_cache()
    yield
    audit_tasks.reset_gh_env_cache()


class TestTheTokenReachesTheSubprocess:
    def test_a_vault_token_is_exported_under_both_names(self, monkeypatch):
        """Different gh subcommands read different variables — the Copilot
        adapter sets both for the same reason."""
        monkeypatch.setattr(audit_tasks, "_resolve_filing_token", lambda: "tok-abc")

        env, from_vault = audit_tasks._gh_env()

        assert from_vault is True
        assert env["GH_TOKEN"] == "tok-abc"
        assert env["GITHUB_TOKEN"] == "tok-abc"

    def test_no_token_leaves_the_environment_untouched(self, monkeypatch):
        """Ambient auth still works — this must not break filing on a host that
        has not stored a token yet."""
        monkeypatch.setattr(audit_tasks, "_resolve_filing_token", lambda: None)
        monkeypatch.delenv("GH_TOKEN", raising=False)

        env, from_vault = audit_tasks._gh_env()

        assert from_vault is False
        assert "GH_TOKEN" not in env

    def test_file_issue_passes_the_credential(self, monkeypatch):
        """The call that actually needs it. Threading the env through
        `_gh_available` alone would authenticate the CHECK and not the write."""
        monkeypatch.setattr(audit_tasks, "_resolve_filing_token", lambda: "tok-file")
        seen: dict[str, object] = {}

        def _fake_run(cmd, cwd=None, env=None):
            seen["cmd"] = cmd
            seen["env"] = env
            return 0, "", ""

        monkeypatch.setattr(audit_tasks, "_run", _fake_run)

        assert audit_tasks._file_issue("t", "b") is True
        assert seen["cmd"][:3] == ["gh", "issue", "create"]
        assert (seen["env"] or {}).get("GH_TOKEN") == "tok-file"

    def test_listing_issues_passes_the_credential(self, monkeypatch):
        monkeypatch.setattr(audit_tasks, "_resolve_filing_token", lambda: "tok-list")
        seen: dict[str, object] = {}

        def _fake_run(cmd, cwd=None, env=None):
            seen["env"] = env
            return 0, "[]", ""

        monkeypatch.setattr(audit_tasks, "_run", _fake_run)
        audit_tasks._list_open_issues()

        assert (seen["env"] or {}).get("GH_TOKEN") == "tok-list"


class TestRevocationIsPossible:
    def test_the_cache_is_dropped_between_runs(self, monkeypatch):
        """Celery workers are long-lived. Without a reset a revoked token keeps
        working for the life of the process, which defeats the revocation this
        issue exists to provide."""
        tokens = iter(["first", "second"])
        monkeypatch.setattr(audit_tasks, "_resolve_filing_token", lambda: next(tokens))

        assert audit_tasks._gh_env()[0]["GH_TOKEN"] == "first"
        assert audit_tasks._gh_env()[0]["GH_TOKEN"] == "first", "should be cached within a run"

        audit_tasks.reset_gh_env_cache()

        assert audit_tasks._gh_env()[0]["GH_TOKEN"] == "second", "a new run must re-read the vault"

    def test_each_task_resets_before_its_first_gh_call(self, monkeypatch):
        """The reset must precede `_list_open_issues`, not sit inside
        `_gh_available`: every task lists issues FIRST, so the run's first gh
        call carried the previous run's token. A revoked one there returns [],
        which empties existing_titles and silently disables dedupe."""
        calls = {"n": 0}

        def _count():
            calls["n"] += 1
            return "tok"

        monkeypatch.setattr(audit_tasks, "_resolve_filing_token", _count)
        monkeypatch.setattr(audit_tasks, "_run", lambda cmd, cwd=None, env=None: (0, "", ""))

        import ast
        import inspect

        source = inspect.getsource(audit_tasks)
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.FunctionDef) and node.name.startswith("audit_")):
                continue
            names = [n.func.id for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
            assert "reset_gh_env_cache" in names, f"{node.name} never drops the cached credential"
            first_gh = next((i for i, nm in enumerate(names) if nm in {"_list_open_issues", "_gh_available"}), None)
            if first_gh is not None:
                assert (
                    names.index("reset_gh_env_cache") < first_gh
                ), f"{node.name} resets AFTER its first gh call — that call uses the previous run's token"
        assert calls["n"] >= 0


class TestTheGapIsReportedEvenWhenItWorks:
    def test_ambient_auth_is_reported_on_every_run(self, monkeypatch, caplog):
        """The whole failure mode was invisibility: ambient auth that happens to
        work looks identical to an owned credential until the day it lapses."""
        import logging

        monkeypatch.setattr(audit_tasks, "_resolve_filing_token", lambda: None)
        # An AMBIENT token present, deliberately. The first version of this test
        # deleted it, which is why it passed against a detector that answered
        # "does this process have a GH_TOKEN anywhere?" instead of "did the vault
        # give me one?" — docker-compose injects an empty GH_TOKEN
        # unconditionally, and the pre-#13859 log told operators to set one.
        monkeypatch.setenv("GH_TOKEN", "ambient-leftover")
        monkeypatch.setattr(audit_tasks, "_run", lambda cmd, cwd=None, env=None: (0, "ok", ""))

        with caplog.at_level(logging.WARNING):
            assert audit_tasks._gh_available() is True

        assert any("no vault-owned filing credential" in r.message for r in caplog.records)

    def test_a_vault_backed_run_is_not_warned_about(self, monkeypatch, caplog):
        """The direction that must stay true — a warning on every run would be
        noise nobody reads, which is how the original lapse survived."""
        import logging

        monkeypatch.setattr(audit_tasks, "_resolve_filing_token", lambda: "tok")
        monkeypatch.setattr(audit_tasks, "_run", lambda cmd, cwd=None, env=None: (0, "ok", ""))

        with caplog.at_level(logging.WARNING):
            audit_tasks._gh_available()

        assert not any("no vault-owned filing credential" in r.message for r in caplog.records)

    def test_a_vault_outage_does_not_kill_the_audit_run(self, monkeypatch):
        """Filing is best-effort; an unreachable vault must degrade to ambient
        auth rather than take the whole audit down."""

        def _boom():
            raise RuntimeError("vault unreachable")

        monkeypatch.setattr(audit_tasks, "_read_filing_token", _boom)
        monkeypatch.setattr(audit_tasks, "run_or_schedule", lambda coro: _boom())

        assert audit_tasks._resolve_filing_token() is None
