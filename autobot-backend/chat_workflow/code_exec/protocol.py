# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Wire protocol constants shared between the shim, the broker pump, and tests.

Code-execution mode multiplexes two logical streams over the sandbox's single
stdout: the shim's JSON-RPC tool requests and the script's own output (prints
and its final result). To keep them cleanly separable (GH#11613), every RPC
request line the shim writes is prefixed with ``RPC_SENTINEL``; the executor
pump routes only sentinel-prefixed lines to the broker and treats every other
stdout line as the script's result.

``\\x1e`` (ASCII Record Separator) is a control character that never appears in
JSON or ordinary text output, so a script's own prints cannot be mistaken for
RPC — and, conversely, RPC framing never pollutes the returned result.
"""

from __future__ import annotations

#: Prefix marking a stdout line as a shim -> broker JSON-RPC request.
RPC_SENTINEL: str = "\x1eCXRPC\x1e"

#: Bytes form used by the executor pump before utf-8 decode.
RPC_SENTINEL_BYTES: bytes = RPC_SENTINEL.encode("utf-8")

__all__ = ["RPC_SENTINEL", "RPC_SENTINEL_BYTES"]
