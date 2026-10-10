# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
"""``is_local_ip`` answers "local" only when provable (#17855).

A false "local" runs a command on the wrong host; a false "remote" costs one SSH hop. So every
unknown or ambiguous input must resolve to remote. ``api/nodes_execution.py`` once built its own
set from ``gethostbyname(hostname)`` (commonly ``127.0.1.1``) and misclassified its own host.
"""

import socket
from types import SimpleNamespace

import pytest

import autobot_shared.network_utils as nu

#: ``ip -o -4 addr show`` for a host with a real NIC, Docker's default bridge, a user bridge,
#: a tailnet tunnel, and a link-local address.
_IP_OUTPUT = "\n".join(
    [
        "1: lo    inet 127.0.0.1/8 scope host lo",
        "2: eth0    inet 10.9.8.7/24 brd 10.9.8.255 scope global eth0",
        "3: docker0    inet 172.17.0.1/16 brd 172.17.255.255 scope global docker0",
        "4: br-1a2b3c    inet 172.20.0.1/16 brd 172.20.255.255 scope global br-1a2b3c",
        "5: tailscale0    inet 100.101.102.103/32 scope global tailscale0",
        "6: eth1    inet 169.254.10.10/16 scope link eth1",
        "7: eth2@if9    inet 192.168.50.2/24 scope global eth2",
    ]
)


@pytest.fixture(autouse=True)
def _host(monkeypatch):
    monkeypatch.setattr(nu, "_ip_cache", None)
    monkeypatch.setattr(nu, "_ip_cache_time", 0.0)
    monkeypatch.setattr(nu.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=_IP_OUTPUT))


def _dns(monkeypatch, mapping):
    def fake(host, port, *a, **k):
        if host not in mapping:
            raise socket.gaierror("unknown")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (addr, 0)) for addr in mapping[host]]

    monkeypatch.setattr(nu.socket, "getaddrinfo", fake)


@pytest.mark.parametrize(
    ("addr", "expected", "why"),
    [
        ("127.0.0.1", True, "loopback"),
        ("::1", True, "IPv6 loopback"),
        ("localhost", True, "loopback name"),
        ("::ffff:127.0.0.1", True, "IPv4-mapped loopback"),
        ("10.9.8.7", True, "exact NIC address"),
        ("192.168.50.2", True, "exact NIC address, interface name carries an @peer suffix"),
        ("::ffff:10.9.8.7", True, "IPv4-mapped NIC address that really is an interface address"),
        ("::ffff:10.0.0.5", False, "IPv4-mapped address that is not an interface address"),
        ("10.0.0.5", False, "private but not ours"),
        ("0.0.0.0", False, "unspecified"),
        ("::", False, "unspecified IPv6"),
        ("169.254.10.10", False, "link-local, even though an interface holds it"),
        ("169.254.169.254", False, "link-local metadata address"),
        ("fe80::1", False, "IPv6 link-local"),
        ("172.17.0.1", False, "docker0 exists on every Docker host"),
        ("172.20.0.1", False, "br-* user bridge"),
        ("100.101.102.103", False, "tailnet address on a tunnel interface"),
        ("100.64.0.9", False, "CGNAT overlay range"),
        ("", False, "empty"),
        ("   ", False, "blank"),
    ],
)
def test_literal_addresses(addr, expected, why):
    assert nu.is_local_ip(addr) is expected, why


def test_a_shared_range_is_not_local_even_if_a_plain_interface_holds_it(monkeypatch):
    out = "2: eth0    inet 100.70.1.1/10 scope global eth0"
    monkeypatch.setattr(nu.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=out))
    assert nu.is_local_ip("100.70.1.1") is False


def test_hostname_is_local_only_if_every_resolved_address_is_local(monkeypatch):
    _dns(
        monkeypatch,
        {
            "all-local": ["10.9.8.7", "127.0.0.1"],
            "mixed": ["10.9.8.7", "203.0.113.5"],
            "remote": ["203.0.113.5", "203.0.113.6"],
            "bridge-only": ["172.17.0.1"],
            "any-addr": ["0.0.0.0"],
            "empty": [],
        },
    )
    assert nu.is_local_ip("all-local") is True
    assert nu.is_local_ip("mixed") is False
    assert nu.is_local_ip("remote") is False
    assert nu.is_local_ip("bridge-only") is False
    assert nu.is_local_ip("any-addr") is False
    assert nu.is_local_ip("empty") is False


def test_an_unresolvable_hostname_is_remote(monkeypatch):
    _dns(monkeypatch, {})
    assert nu.is_local_ip("nowhere.invalid") is False


def test_no_ip_command_means_only_loopback_is_local(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("ip")

    monkeypatch.setattr(nu.subprocess, "run", boom)
    assert nu.is_local_ip("127.0.0.1") is True
    assert nu.is_local_ip("10.9.8.7") is False


def test_get_local_ips_still_lists_every_interface_for_fleet_matching():
    assert {"127.0.0.1", "10.9.8.7", "172.17.0.1", "100.101.102.103"} <= nu.get_local_ips()
