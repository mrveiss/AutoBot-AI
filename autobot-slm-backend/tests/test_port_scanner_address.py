# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for bind-address capture in the agent port scanner (GH#11224).

Covers:
- _parse_bind_address across ss/netstat address formats (ipv4, wildcard, ipv6).
- get_listening_ports populates PortInfo.address from mocked `ss` output.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_slm_root = Path(__file__).parent.parent
if str(_slm_root) not in sys.path:
    sys.path.insert(0, str(_slm_root))

from slm.agent.port_scanner import _parse_bind_address, get_listening_ports  # noqa: E402


class TestParseBindAddress:
    def test_ipv4_concrete(self):
        assert _parse_bind_address("127.0.0.1:6379") == "127.0.0.1"
        assert _parse_bind_address("0.0.0.0:22") == "0.0.0.0"
        assert _parse_bind_address("192.168.1.5:5432") == "192.168.1.5"

    def test_wildcard(self):
        assert _parse_bind_address("*:8080") == "*"

    def test_ipv6(self):
        assert _parse_bind_address(":::22") == "::"
        assert _parse_bind_address("[::]:22") == "::"
        assert _parse_bind_address("[::1]:6379") == "::1"

    def test_unparseable(self):
        assert _parse_bind_address("noport") is None


class TestGetListeningPortsAddress:
    def test_address_populated_from_ss(self):
        ss_output = (
            "State  Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n"
            'LISTEN 0      128    0.0.0.0:6379       0.0.0.0:*         users:(("redis-server",pid=42,fd=6))\n'
            'LISTEN 0      128    127.0.0.1:5432     0.0.0.0:*         users:(("postgres",pid=99,fd=7))\n'
        )
        completed = MagicMock(returncode=0, stdout=ss_output, stderr="")
        with patch("slm.agent.port_scanner.subprocess.run", return_value=completed):
            ports = get_listening_ports()

        by_port = {p.port: p for p in ports}
        assert by_port[6379].address == "0.0.0.0"
        assert by_port[6379].process == "redis-server"
        assert by_port[5432].address == "127.0.0.1"
