# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20935: how the runner talks to the node over ssh: unavailable-not-failure, validated settings, host-key trust, sweep ttl."""

from __future__ import annotations

import subprocess

import pytest
from repo_tests.remote_test_node_20935_support import BASE_ENV, run


def _expire(*_args, **_kwargs):
    raise subprocess.TimeoutExpired("ssh", 1)


def test_a_missing_ssh_executable_is_unavailable_not_a_failure(capfd):
    env = {**BASE_ENV, "AUTOBOT_TEST_NODE_SSH_BIN": "/nonexistent/ssh"}
    assert run.probe(run.load_config(env)) == "ssh to the test node could not start (FileNotFoundError)"
    assert run.main(["--sha", "HEAD", "--", "true"], env=env) == run.UNAVAILABLE
    assert "UNAVAILABLE" in capfd.readouterr().err


def test_a_hung_probe_is_unavailable_not_a_failure(monkeypatch, capfd):
    monkeypatch.setattr(run.subprocess, "run", _expire)
    assert run.probe(run.load_config(BASE_ENV)) == "ssh to the test node timed out"
    assert run.main(["--sha", "HEAD", "--", "true"], env=BASE_ENV) == run.UNAVAILABLE
    assert "UNAVAILABLE" in capfd.readouterr().err


def test_a_hung_ship_is_unavailable_not_124(monkeypatch):
    monkeypatch.setattr(run.subprocess, "run", _expire)
    cfg = run.load_config(BASE_ENV)
    assert "timed out" in run.ship_commit(cfg, "abc", "job")
    monkeypatch.setattr(run, "probe", lambda _cfg: None)
    assert run.main(["--sha", "HEAD", "--", "true"], env=BASE_ENV) == run.UNAVAILABLE


def test_a_hung_cleanup_cannot_mask_the_result(monkeypatch):
    monkeypatch.setattr(run.subprocess, "run", _expire)
    run.remote_cleanup(run.load_config(BASE_ENV), "job")  # does not raise
    monkeypatch.setattr(run, "ship_commit", lambda *_a: None)
    monkeypatch.setattr(run, "_script_command", lambda *_a: "true")
    monkeypatch.setattr(
        run.subprocess, "Popen", lambda *_a, **_k: type("P", (), {"wait": lambda s, timeout: 7, "poll": lambda s: 7})()
    )
    assert run.run_remote(run.load_config(BASE_ENV), "abc", ["true"], 30) == 7


@pytest.mark.parametrize(
    "name,value,attr,expected",
    [
        ("AUTOBOT_TEST_NODE_SLOTS", "0", "slots", 3),
        ("AUTOBOT_TEST_NODE_SLOTS", "99", "slots", 3),
        ("AUTOBOT_TEST_NODE_SLOTS", "abc", "slots", 3),
        ("AUTOBOT_TEST_NODE_SLOTS", "5", "slots", 5),
        ("AUTOBOT_TEST_NODE_TIMEOUT", "1", "timeout", 600),
        ("AUTOBOT_TEST_NODE_CONNECT_TIMEOUT", "0", "connect_timeout", 10),
    ],
)
def test_env_ints_are_validated_against_the_registered_ranges(name, value, attr, expected):
    assert getattr(run.load_config({**BASE_ENV, name: value}), attr) == expected


def test_host_key_trust_is_first_use_unless_pinned():
    assert "StrictHostKeyChecking=accept-new" in run.ssh_argv(run.load_config(BASE_ENV))
    pinned = run.ssh_argv(run.load_config({**BASE_ENV, "AUTOBOT_TEST_NODE_KNOWN_HOSTS": "/pins/kh"}))
    assert "StrictHostKeyChecking=yes" in pinned and "UserKnownHostsFile=/pins/kh" in pinned
    assert "GlobalKnownHostsFile=/dev/null" in pinned  # the pinned file is the only trust source
    assert "StrictHostKeyChecking=accept-new" not in pinned
    assert pinned[pinned.index("-F") + 1] == "/dev/null"  # a user ssh config cannot widen trust
    first_use = run.ssh_argv(run.load_config(BASE_ENV))
    assert first_use[first_use.index("-F") + 1] == "/dev/null" and "-p" in pinned  # no user config either way


def test_the_stale_sweep_ttl_follows_the_effective_timeout(monkeypatch):
    sent = []
    monkeypatch.setattr(run, "ship_commit", lambda *_a: None)
    monkeypatch.setattr(run, "remote_cleanup", lambda *_a: None)
    monkeypatch.setattr(run, "_script_command", lambda *a: sent.append(a) or "true")
    monkeypatch.setattr(
        run.subprocess, "Popen", lambda *_a, **_k: type("P", (), {"wait": lambda s, timeout: 0, "poll": lambda s: 0})()
    )
    run.run_remote(run.load_config(BASE_ENV), "abc", ["true"], 3600)
    assert sent[0][4] == "90"  # 3600 s -> 60 min + 30
