#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Fail when a JSON-Schema ``default`` in the OpenAPI contract is an absolute path (#13572).

A schema ``default`` is baked into the published contract and shipped in the
committed frontend types. When that default is an absolute filesystem path it
does two things, both bad:

1. **It makes the contract host-dependent.** The value is whatever the machine
   that last generated it resolved, so ``verify-generated-types`` starts failing
   for reasons unrelated to any API change. #13357 already records this
   happening twice — "a generated-types regeneration twice picked up the build
   machine's absolute paths as schema defaults".
2. **It discloses the server's filesystem layout** to every API consumer.

The fix at each site is ``default_factory`` instead of ``default``. Pydantic and
FastAPI both omit a factory from the generated schema while the runtime default
is unchanged, so this costs nothing:

    # publishes the path
    repo_path: str = Field(default=str(PROJECT_ROOT))

    # identical at runtime, absent from the schema
    repo_path: str = Field(default_factory=lambda: str(PROJECT_ROOT))

This checker exists because nothing else stops the next one. #13572 fixed 21
sites; two of them were not in that issue's own list of 19 and were found only
by dumping the contract and looking — which is what this script automates.

Exit code:
  0 — no absolute-path defaults
  1 — at least one, or the contract could not be dumped
"""

from __future__ import annotations

import json
import subprocess  # nosec B404  # fixed argv, no shell, no caller input
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterator, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Values that are absolute but carry no host-specific information. ``/`` alone
#: is meaningless as a disclosure and shows up as a legitimate URL-path default.
_ALLOWED = {"/"}


def _walk_defaults(node: Any, path: str = "") -> Iterator[Tuple[str, str]]:
    """Yield ``(json_path, value)`` for every string default under *node*.

    List-valued defaults are flattened: ``default=[str(PROJECT_ROOT)]`` leaks
    exactly as much as the scalar form, and two of the sites in #13572 were of
    that shape.
    """
    if isinstance(node, dict):
        if "default" in node:
            value = node["default"]
            for item in value if isinstance(value, list) else [value]:
                if isinstance(item, str):
                    yield path, item
        for key, value in node.items():
            yield from _walk_defaults(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk_defaults(value, f"{path}[{index}]")


def _is_absolute_path(value: str) -> bool:
    """True when *value* looks like an absolute filesystem path, not a URL path.

    A URL route (``/api/health``) is a legitimate default and is not a
    disclosure. The distinction used here is that a filesystem path names a real
    directory on this machine — which is precisely the property that makes it
    host-dependent, and therefore the one worth rejecting.
    """
    if value in _ALLOWED or not value.startswith("/"):
        return False
    return Path(value).exists()


def _dump_openapi(target: Path) -> bool:
    """Dump the backend OpenAPI contract to *target*. True on success."""
    result = subprocess.run(  # nosec B603  # fixed argv, no shell
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "audit_api_wiring.py"),
            "--dump-openapi",
            str(target),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not target.exists() or target.stat().st_size == 0:
        print("Could not dump the OpenAPI contract:")
        print((result.stderr or result.stdout or "")[-2000:])
        return False
    return True


def _load_contract(argv: list[str]) -> dict | None:
    """Return the contract, reusing a pre-dumped file when one is given.

    ``--contract <path>`` exists so CI does not pay for a second dump:
    ``verify-generated-types.yml`` already builds ``app.openapi()`` and writes it
    out, and that build is the expensive part of the job.
    """
    if "--contract" in argv:
        given = Path(argv[argv.index("--contract") + 1])
        if not given.exists():
            print(f"--contract given but not found: {given}")
            return None
        return json.loads(given.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "openapi.json"
        if not _dump_openapi(target):
            return None
        return json.loads(target.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    """Dump (or load) the contract and reject absolute-path schema defaults."""
    contract = _load_contract(argv if argv is not None else sys.argv[1:])
    if contract is None:
        return 1

    offenders = [(p, v) for p, v in _walk_defaults(contract) if _is_absolute_path(v)]
    if not offenders:
        return 0

    for json_path, value in offenders[:15]:
        print(f"{json_path.lstrip('.')}: default is an absolute path -> {value}")
    if len(offenders) > 15:
        print(f"... and {len(offenders) - 15} more")
    print(
        f"\n{len(offenders)} absolute-path schema default(s) (#13572). "
        "Use default_factory=lambda: ... — same runtime value, absent from the schema."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
