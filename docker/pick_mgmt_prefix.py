#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pick a free private /24 for the compose management network (#16833).

docker-compose.yml has no default range for ``autobot-mgmt``: a fixed one
(172.30.0.0/24) took over the host's own route on a LAN using the same /24.
This prints the first three octets of a /24 that overlaps no host route and no
existing Docker network, drawn at random from AUTOBOT_DOCKER_MGMT_POOL. It is
run once by docker/generate-secrets.sh, which keeps the result.
"""

from __future__ import annotations

import ipaddress
import os
import random
import subprocess
import sys

# Candidate pool, overridable. A large private block, away from the 10.0.x.x
# ranges home and office routers hand out most.
_DEFAULT_POOL = "10.128.0.0/9"
_ATTEMPTS = 512
# ip-route(8) route types that precede the destination on a line.
_ROUTE_TYPES = {
    "unicast",
    "blackhole",
    "unreachable",
    "prohibit",
    "throw",
    "local",
    "broadcast",
    "multicast",
    "nat",
    "anycast",
}

Network = ipaddress.IPv4Network


def routes_in_use(route_lines: list[str]) -> list[Network]:
    """Destinations from `ip -4 route show` lines; `default` is not a range."""
    used = []
    for line in route_lines:
        tokens = line.split()
        if tokens and tokens[0] in _ROUTE_TYPES:
            tokens = tokens[1:]  # `blackhole 10.0.0.0/8`, `unreachable 10.1.0.0/16 ...`
        if tokens and tokens[0] != "default":
            used.append(ipaddress.ip_network(tokens[0], strict=False))
    return used


def pick(used: list[Network], pool: Network, rng: random.Random) -> str:
    """First three octets of a random /24 in `pool` overlapping nothing in `used`."""
    subnets = 2 ** (24 - pool.prefixlen)
    for _ in range(_ATTEMPTS):
        base = int(pool.network_address) + (rng.randrange(subnets) << 8)
        candidate = ipaddress.ip_network((base, 24))
        if not any(candidate.overlaps(u) for u in used):
            return str(candidate.network_address).rsplit(".", 1)[0]
    raise SystemExit(f"no free /24 found in {pool}: set AUTOBOT_DOCKER_MGMT_PREFIX by hand (INSTALL.md)")


def _command_lines(cmd: list[str]) -> list[str]:
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout.splitlines()


def docker_subnets() -> list[Network]:
    """Subnets of existing Docker networks, so the pick never collides with another stack."""
    try:
        ids = _command_lines(["docker", "network", "ls", "-q"])
        fmt = "{{range .IPAM.Config}}{{.Subnet}} {{end}}"
        lines = _command_lines(["docker", "network", "inspect", "--format", fmt, *ids]) if ids else []
    except FileNotFoundError:
        return []  # no docker CLI: no Docker networks to collide with
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            f"docker did not answer ({exc.stderr.strip()}): start it or fix your access to it, "
            "or set AUTOBOT_DOCKER_MGMT_PREFIX by hand (INSTALL.md)"
        ) from exc
    found = [ipaddress.ip_network(s) for line in lines for s in line.split()]
    return [n for n in found if isinstance(n, Network)]


def main() -> None:
    raw_pool = os.getenv("AUTOBOT_DOCKER_MGMT_POOL", _DEFAULT_POOL)
    try:
        pool = ipaddress.ip_network(raw_pool)
    except ValueError as exc:
        raise SystemExit(f"AUTOBOT_DOCKER_MGMT_POOL is not a network: {raw_pool}") from exc
    usable = isinstance(pool, Network) and pool.is_private and not (pool.is_loopback or pool.is_link_local)
    if not usable or pool.prefixlen > 24:
        raise SystemExit(f"AUTOBOT_DOCKER_MGMT_POOL must be a private IPv4 block of /24 or larger, not {pool}")
    try:
        routes = _command_lines(["ip", "-4", "route", "show", "table", "all"])
    except FileNotFoundError as exc:
        raise SystemExit("cannot read host routes (no `ip`): set AUTOBOT_DOCKER_MGMT_PREFIX by hand") from exc
    used = routes_in_use(routes) + docker_subnets()
    sys.stdout.write(pick(used, pool, random.SystemRandom()) + "\n")


if __name__ == "__main__":
    main()
