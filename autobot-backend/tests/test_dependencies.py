# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for dependencies.py (#18705: security-layer provider is canonical and fails closed)."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from dependencies import provide_security_layer


def _request(**state):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(**state)))


def test_returns_the_app_state_layer():
    layer = object()
    assert provide_security_layer(_request(security_layer=layer)) is layer


def test_missing_layer_is_503():
    with pytest.raises(HTTPException) as exc:
        provide_security_layer(_request())
    assert exc.value.status_code == 503


def test_none_layer_is_503():
    with pytest.raises(HTTPException) as exc:
        provide_security_layer(_request(security_layer=None))
    assert exc.value.status_code == 503


def test_lookup_error_is_503_not_none():
    class _Boom:
        @property
        def state(self):
            raise RuntimeError("boom")

    with pytest.raises(HTTPException) as exc:
        provide_security_layer(SimpleNamespace(app=_Boom()))
    assert exc.value.status_code == 503


def test_files_accessor_is_the_canonical_provider():
    from api import files

    assert files.get_security_layer is provide_security_layer
