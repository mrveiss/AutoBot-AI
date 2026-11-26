# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""No registry default and no generated env doc publishes a private address or internal hostname (#17440).

``docs/developer/ENV_VARS.md`` is generated from the ``EnvVarSpec`` defaults and committed to a public repo, so a
default is an outward artifact. The fix lives at the declaration; the doc is checked too, so a value that arrives by
another route is still caught.
"""

from __future__ import annotations

import re
from pathlib import Path

from autobot_shared.env_registry import REGISTRY

_ROOT = Path(__file__).resolve().parent.parent
_DOC = _ROOT / "docs" / "developer" / "ENV_VARS.md"

_PRIVATE_IP = re.compile(
    r"(?<![\d.])(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(?![\d])"
)
_INTERNAL_HOST = re.compile(r"(?<![\w-])[\w-]+(?:\.[\w-]+)*\.(?:internal|lan|local|corp|intranet)(?![\w-])")
# A workstation's home or mount path is internal to whoever wrote it, never a default worth publishing (#17440 AC3).
_USER_PATH = re.compile(r"(?<![\w.])(?:/home/[\w.-]+|/Users/[\w.-]+|/mnt/[a-z]/[\w.-]+|[A-Z]:\\Users\\[\w.-]+)")


def internal_values(text: str) -> list[str]:
    """Every private IPv4 address, internal-looking hostname and user-home path in *text*."""
    return [m.group(0) for rx in (_PRIVATE_IP, _INTERNAL_HOST, _USER_PATH) for m in rx.finditer(text)]


def test_the_detector_flags_private_addresses_and_internal_hosts_and_passes_public_ones() -> None:
    assert internal_values("http://" + ".".join(("10", "1", "2", "3")) + ":80") != []
    assert internal_values(".".join(("192", "168", "0", "9"))) != []
    assert internal_values(".".join(("172", "20", "0", "1"))) != []
    assert internal_values("node" + ".internal") != []
    assert internal_values("/home/" + "someone/work") != []
    assert internal_values("/Users/" + "someone/work") != []
    assert internal_values("/opt/autobot /var/log/autobot /home") == []
    assert internal_values("http://localhost:9090 127.0.0.1 8.8.8.8 172.32.0.1 example.com") == []


def test_no_registry_default_carries_a_private_address_or_internal_host() -> None:
    leaks = {n: internal_values(s.default) for n, s in REGISTRY.items() if isinstance(s.default, str)}
    assert {n: v for n, v in leaks.items() if v} == {}


def test_the_generated_env_doc_carries_no_private_address_or_internal_host() -> None:
    assert internal_values(_DOC.read_text(encoding="utf-8")) == []
