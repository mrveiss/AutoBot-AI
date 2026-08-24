# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Dump the SLM backend OpenAPI schema to stdout as JSON.

Used by the ``gen:types`` pipeline in ``autobot-slm-frontend`` to regenerate
``src/types/generated/api.ts`` from a reproducible, checked-in spec rather than
a live server. Run from anywhere::

    python3 autobot-slm-backend/scripts/dump_openapi.py > autobot-slm-frontend/openapi.json
"""

import json
import sys
from pathlib import Path

# Make ``main`` / ``api`` importable (autobot-slm-backend) and ``autobot_shared``
# (repo root) resolvable regardless of the invoking working directory. The
# backend root must precede the repo root so the backend ``main`` wins over the
# deprecated repo-root ``main.py`` shim.
_SCRIPT = Path(__file__).resolve()
_BACKEND_ROOT = _SCRIPT.parents[1]
_REPO_ROOT = _SCRIPT.parents[2]
for _path in (str(_REPO_ROOT), str(_BACKEND_ROOT)):
    if _path in sys.path:
        sys.path.remove(_path)
    sys.path.insert(0, _path)


def main() -> int:
    from autobot_shared.openapi_schema import normalize_pattern_anchors
    from main import app

    # pydantic >= 2.12 emits the Rust end anchor `\\z` for a Field(pattern=...)
    # written with `$`. JSON Schema's dialect is ECMA-262, which reads `\\z` as a
    # literal `z` -- `^(hour|day)\\z` then rejects "hour" and accepts "hourz".
    # Normalise before the spec becomes a published artifact (#12959 sweep).
    spec = normalize_pattern_anchors(app.openapi())
    json.dump(spec, sys.stdout, indent=2, sort_keys=True, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
