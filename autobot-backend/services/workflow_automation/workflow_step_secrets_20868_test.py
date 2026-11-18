# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The values injected into a step are what gets masked, even after the stored secret changes (#20868)."""

import pickle
import sqlite3
import time
from types import SimpleNamespace

import pytest
from cryptography.fernet import InvalidToken

from services.workflow_secret_service import StepSecrets, WorkflowSecretService

from . import command_step, executor

_VALUE = "s3cr3t-value-20868"
_COMMAND = "echo ${secrets.TOKEN}"


@pytest.fixture
def service(monkeypatch):
    """A real service whose store holds one secret, and the store handle to change it."""
    store = {"TOKEN": _VALUE}
    svc = WorkflowSecretService(secrets_service=SimpleNamespace())
    monkeypatch.setattr(svc, "get_secret_value", lambda name, owner: store.get(name))
    monkeypatch.setattr(command_step, "get_workflow_secret_service", lambda: svc)
    monkeypatch.setattr(executor, "get_workflow_secret_service", lambda: svc)
    return svc, store


def test_resolve_injects_the_value_and_returns_it_for_the_step(service):
    svc, _ = service
    resolved, injected = svc.resolve_secrets(_COMMAND, "owner")
    assert resolved == f"echo {_VALUE}"
    assert injected.names == frozenset({"TOKEN"})


def test_the_step_result_masks_the_injected_value(service):
    svc, _ = service
    _, injected = svc.resolve_secrets(_COMMAND, "owner")
    raw = {"return_code": 0, "stdout": f"got {_VALUE}", "stderr": f"err {_VALUE}"}
    result = command_step._step_result(raw, command_step.secret_value_redactor(injected), time.monotonic())
    assert _VALUE not in str(result)
    assert result["stdout"] == "got ***" and result["stderr"] == "err ***"


def test_the_executor_result_masks_the_injected_value(service):
    svc, _ = service
    _, injected = svc.resolve_secrets(_COMMAND, "owner")
    result = executor._redact_result_secrets({"stdout": f"a {_VALUE} b", "stderr": _VALUE}, injected)
    assert result == {"stdout": "a *** b", "stderr": "***"}


@pytest.mark.parametrize("change", ["rotated", "deleted"])
def test_a_secret_changed_mid_step_is_still_masked_by_its_injected_value(service, change):
    svc, store = service
    _, injected = svc.resolve_secrets(_COMMAND, "owner")
    if change == "rotated":
        store["TOKEN"] = "a-new-value-after-rotation"
    else:
        del store["TOKEN"]
    result = executor._redact_result_secrets({"stdout": f"old {_VALUE}", "stderr": ""}, injected)
    assert _VALUE not in result["stdout"]


def test_nothing_injected_leaves_text_alone_and_reads_no_store(service):
    svc, store = service
    store.clear()
    _, injected = svc.resolve_secrets("echo plain", "owner")
    assert not injected
    assert svc.redact_secrets("plain " + _VALUE, injected) == "plain " + _VALUE


def test_the_longer_value_is_masked_whole_when_one_contains_another():
    injected = StepSecrets({"A": "abc", "B": "abcdef"})
    assert WorkflowSecretService(secrets_service=SimpleNamespace()).redact_secrets("x abcdef y", injected) == "x *** y"


def test_the_holder_neither_prints_nor_pickles_the_value():
    injected = StepSecrets({"TOKEN": _VALUE})
    assert _VALUE not in repr(injected) and _VALUE not in str(injected)
    with pytest.raises(TypeError):
        pickle.dumps(injected)


@pytest.mark.parametrize(
    "error", [sqlite3.OperationalError("locked"), OSError("disk"), ValueError("row"), InvalidToken()]
)
def test_an_unreadable_secret_store_leaves_the_token_unresolved(monkeypatch, error):
    def _unreadable():
        raise error

    monkeypatch.setattr(executor, "get_workflow_secret_service", _unreadable)
    command, injected = executor._resolve_command_secrets(_COMMAND, "owner")
    assert command == _COMMAND and not injected


def test_a_defect_in_secret_resolution_is_not_swallowed(monkeypatch):
    def _broken():
        raise RuntimeError("a bug, not an unreadable store")

    monkeypatch.setattr(executor, "get_workflow_secret_service", _broken)
    with pytest.raises(RuntimeError):
        executor._resolve_command_secrets(_COMMAND, "owner")
