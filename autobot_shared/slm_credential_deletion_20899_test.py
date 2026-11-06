# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The internal key never crosses the network in clear text to a remote SLM (#20899, option A)."""

from unittest.mock import patch

import pytest

from autobot_shared.slm_credential_deletion import (
    PlainHttpToRemoteSlmError,
    is_loopback_host,
    is_split_without_tls,
    slm_direct_url,
)
from autobot_shared.ssot_config import config

REMOTE = "slm.cluster.example"


def _layout(host: str, tls: bool):
    return patch.object(config.vm, "slm", host), patch.object(config.tls, "slm_tls_enabled", tls)


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "[::1]"])
def test_loopback_http_is_allowed(host) -> None:
    vm, tls = _layout(host, False)
    with vm, tls:
        assert slm_direct_url().startswith(f"http://{host}:") and not is_split_without_tls()


@pytest.mark.parametrize("host", [REMOTE, "10.1.2.3", "0.0.0.0"])
def test_non_loopback_http_is_refused(host) -> None:
    vm, tls = _layout(host, False)
    with vm, tls, pytest.raises(PlainHttpToRemoteSlmError):
        slm_direct_url()
    with vm, tls:
        assert is_split_without_tls()


def test_https_to_a_remote_slm_is_allowed() -> None:
    vm, tls = _layout(REMOTE, True)
    with vm, tls:
        assert slm_direct_url().startswith(f"https://{REMOTE}:") and not is_split_without_tls()


def test_a_lookalike_host_is_not_loopback() -> None:
    assert not is_loopback_host("127.0.0.1.example.com") and not is_loopback_host("")
