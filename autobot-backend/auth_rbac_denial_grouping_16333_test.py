# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A non-admin repeating a refused request can't flood the audit log (#16333).

``audit_role_denied`` writes one ``role_denied`` row per user and route template per window;
the next row carries how many refusals it absorbed.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import auth_rbac
from autobot_shared.repeat_grouping import RepeatGrouper


@pytest.fixture
def layer(monkeypatch):
    monkeypatch.setattr(auth_rbac, "_DENIALS", RepeatGrouper(window_s=300))
    layer = MagicMock()
    with patch.object(auth_rbac, "_get_security_layer", return_value=layer):
        yield layer


def _request(template: str, path: str):
    return SimpleNamespace(scope={"route": SimpleNamespace(path=template)}, url=SimpleNamespace(path=path))


def _deny(user: str, template: str = "/admin/items/{item_id}", path: str = "/admin/items/1"):
    auth_rbac.audit_role_denied({"username": user}, ["admin", "superadmin"], "user", _request(template, path))


def test_repeats_on_one_route_write_one_row(layer):
    for item in range(50):
        _deny("bob", path=f"/admin/items/{item}")  # one template, many paths: still one route
    assert layer.audit_log.call_count == 1
    assert layer.audit_log.call_args.kwargs["details"]["repeats_since_last_record"] == 0


def test_the_next_row_counts_what_the_window_absorbed(layer):
    for _ in range(10):
        _deny("bob")
    key = ("bob", "user", "/admin/items/{item_id}")
    at, repeats = auth_rbac._DENIALS._recent[key]
    auth_rbac._DENIALS._recent[key] = (at - 301, repeats)
    _deny("bob")
    assert layer.audit_log.call_count == 2
    assert layer.audit_log.call_args.kwargs["details"]["repeats_since_last_record"] == 9


def test_each_user_and_each_route_is_recorded(layer):
    _deny("bob")
    _deny("alice")
    _deny("bob", template="/admin/other", path="/admin/other")
    assert layer.audit_log.call_count == 3


def test_unmatched_paths_group_under_one_key(layer):
    """A caller-chosen raw path must not grow the tracker: no route means one constant key."""
    for item in range(20):
        request = SimpleNamespace(scope={}, url=SimpleNamespace(path=f"/nowhere/{item}"))
        auth_rbac.audit_role_denied({"username": "bob"}, ["admin"], "user", request)
    assert layer.audit_log.call_count == 1
    assert len(auth_rbac._DENIALS._recent) == 1
    assert layer.audit_log.call_args.kwargs["details"]["endpoint"] == "/nowhere/0"


def test_a_changed_role_is_its_own_record(layer):
    _deny("bob")
    auth_rbac.audit_role_denied({"username": "bob"}, ["admin"], "viewer", _request("/admin/items/{item_id}", "/x"))
    assert layer.audit_log.call_count == 2
