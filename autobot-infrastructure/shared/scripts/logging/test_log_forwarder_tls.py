#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for log_forwarder TLS hardening (#12285).

The syslog TCP_TLS destination must reject the broken TLSv1/TLSv1_1 protocols by
pinning the shared minimum TLS version on the SSL context it wraps sockets with.
"""

import ssl
import sys
from pathlib import Path

# Make ``log_forwarder`` importable regardless of the pytest rootdir.
sys.path.insert(0, str(Path(__file__).parent))

from log_forwarder import DestinationConfig, DestinationType, SyslogDestination, SyslogProtocol  # noqa: E402


def _tls_destination() -> SyslogDestination:
    config = DestinationConfig(
        name="test-syslog",
        type=DestinationType.SYSLOG,
        syslog_protocol=SyslogProtocol.TCP_TLS,
    )
    return SyslogDestination(config)


def test_ssl_context_rejects_tls_below_1_2() -> None:
    """_create_ssl_context enforces TLS >= 1.2 (#12285)."""
    ctx = _tls_destination()._create_ssl_context()
    assert ctx.minimum_version == ssl.TLSVersion.TLSv1_2


def test_ssl_context_min_version_matches_shared_constant() -> None:
    """The forwarder reuses the canonical autobot_shared.tls minimum version (#12285)."""
    from autobot_shared.tls import MIN_TLS_VERSION

    ctx = _tls_destination()._create_ssl_context()
    assert ctx.minimum_version == MIN_TLS_VERSION
