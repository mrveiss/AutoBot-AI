# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Headless Vega-Lite v5 → SVG renderer for server-side export (Phase 2, MVA-484).

Runs a Node.js child process that uses the vega / vega-lite npm packages to
render a spec to an SVG string.  The Node script lives alongside this file at
canvas/scripts/vega_render.mjs.

Design:
- Async-friendly: uses asyncio.create_subprocess_exec so it doesn't block.
  This is safe against shell-injection: argv is passed as discrete items,
  never concatenated into a shell string, and spec data travels via stdin.
- Timeout: 10 s (configurable via VEGA_RENDER_TIMEOUT_S env var).
- Fails fast: if node is absent or the script errors, raises VegaRenderError
  so callers can decide how to handle (e.g. emit a fallback in the export).
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib

_SCRIPT_PATH = str(pathlib.Path(__file__).parent / "scripts" / "vega_render.mjs")
_DEFAULT_TIMEOUT = float(os.environ.get("VEGA_RENDER_TIMEOUT_S", "10"))


class VegaRenderError(RuntimeError):
    pass


async def render_vegalite_to_svg(spec: dict, *, timeout: float = _DEFAULT_TIMEOUT) -> str:
    """
    Render a Vega-Lite v5 spec to an SVG string using a Node.js subprocess.

    The spec JSON is passed via stdin; no user-controlled data appears in argv.
    Raises VegaRenderError on timeout, non-zero exit, or missing dependencies.
    """
    spec_json = json.dumps(spec)

    # argv items are fixed strings — no shell injection risk.
    # asyncio.create_subprocess_exec does NOT invoke a shell.
    try:
        proc = await asyncio.create_subprocess_exec(
            "node",
            _SCRIPT_PATH,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise VegaRenderError("node executable not found; cannot render chart to SVG") from exc

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(spec_json.encode()),
            timeout=timeout,
        )
    except TimeoutError as exc:
        proc.kill()
        raise VegaRenderError(f"Vega render timed out after {timeout}s") from exc

    if proc.returncode != 0:
        err_msg = stderr.decode(errors="replace").strip()
        raise VegaRenderError(f"Vega render process failed (exit {proc.returncode}): {err_msg}")

    svg = stdout.decode(errors="replace").strip()
    if not svg.startswith("<svg"):
        raise VegaRenderError(f"Vega render produced unexpected output (first 200 chars): {svg[:200]}")

    return svg
