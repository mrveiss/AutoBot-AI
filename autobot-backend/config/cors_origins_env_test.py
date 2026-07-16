#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""get_cors_origins must honour the CORS_ORIGINS env var (#11805).

The backend Ansible role renders CORS_ORIGINS into the service env, but
nothing read it — so deployments fell through to generated
``http://{ip}:{port}`` defaults. A TLS browser origin (``https://<host>``,
no port) matched none of them, and api/ws_security.py rejected EVERY
WebSocket handshake with 403 (live events, voice streaming).
"""

from unittest.mock import patch

from config.service_config import ServiceConfigMixin

_TLS_ORIGIN = "https://autobot.example"
_PLAIN_ORIGIN = "http://autobot.example"


class _Cfg(ServiceConfigMixin):
    """Minimal host for the mixin: `security.cors_origins` unset by default."""

    def __init__(self, nested=None):
        self._nested = nested or {}

    def get_nested(self, key, default=None):
        return self._nested.get(key, default)


def test_env_origins_used_when_set():
    with patch.dict("os.environ", {"CORS_ORIGINS": f"{_TLS_ORIGIN},{_PLAIN_ORIGIN}"}):
        assert _Cfg().get_cors_origins() == [_TLS_ORIGIN, _PLAIN_ORIGIN]


def test_env_origins_are_trimmed_and_empties_dropped():
    with patch.dict("os.environ", {"CORS_ORIGINS": f" {_TLS_ORIGIN} , , {_PLAIN_ORIGIN} "}):
        assert _Cfg().get_cors_origins() == [_TLS_ORIGIN, _PLAIN_ORIGIN]


def test_tls_origin_without_port_is_allowed():
    """The exact live failure: https://<host> with no port must be present."""
    with patch.dict("os.environ", {"CORS_ORIGINS": _TLS_ORIGIN}):
        assert _TLS_ORIGIN in _Cfg().get_cors_origins()


def test_config_file_override_still_wins():
    nested = {"security.cors_origins": ["https://from-config.example"]}
    with patch.dict("os.environ", {"CORS_ORIGINS": "https://from-env.example"}):
        assert _Cfg(nested).get_cors_origins() == ["https://from-config.example"]


def test_falls_back_to_generated_defaults_when_env_absent():
    with patch.dict("os.environ", {"CORS_ORIGINS": ""}):
        origins = _Cfg().get_cors_origins()
    assert origins, "generated defaults must still apply when nothing is configured"
    assert all(o.startswith("http") for o in origins)
