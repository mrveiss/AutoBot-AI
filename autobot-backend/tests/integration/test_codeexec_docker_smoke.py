# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""On-box Docker stdio-broker smoke for code-execution mode (Issue #11596).

This is the validation GATE that must pass before ``AUTOBOT_CODEEXEC_ENABLED``
is ever set true in any environment. It exercises the REAL path that unit tests
mock: ``SecureSandboxExecutor.execute_with_stdio_broker`` driving a live
``CodeExecBroker`` over a real Docker container's duplex ``attach_socket``
stream (8-byte frame demux, JSON-RPC line protocol, budget abort, no-network).

It CANNOT run in ordinary CI or a dev box without Docker. It self-skips unless
ALL of the following hold:
  * the ``docker`` SDK imports and a daemon is reachable,
  * the ``autobot/secure-sandbox:latest`` image is present locally,
  * the opt-in env ``AUTOBOT_CODEEXEC_DOCKER_SMOKE=1`` is set.

Run on a box that has the sandbox image::

    AUTOBOT_CODEEXEC_DOCKER_SMOKE=1 \\
      python3 -m pytest autobot-backend/tests/integration/test_codeexec_docker_smoke.py -v

The tools are FAKE (canned dispatch results): this validates the sandbox +
stdio + broker plumbing, not any real tool. Tools are the two read-only names
the v1 injectable set advertises so ``injectable_tool_set`` accepts them.
"""

from __future__ import annotations

import json
import os
import textwrap

import pytest

_SMOKE_ENV = "AUTOBOT_CODEEXEC_DOCKER_SMOKE"
_SANDBOX_IMAGE = "autobot/secure-sandbox:latest"


def _docker_ready() -> bool:
    """True when a Docker daemon is reachable and the sandbox image exists."""
    try:
        import docker  # noqa: PLC0415
    except Exception:
        return False
    try:
        client = docker.from_env()
        client.ping()
        client.images.get(_SANDBOX_IMAGE)
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    os.environ.get(_SMOKE_ENV) != "1" or not _docker_ready(),
    reason=(
        f"code-exec Docker smoke: set {_SMOKE_ENV}=1 and provide a reachable "
        f"daemon with the {_SANDBOX_IMAGE} image (gate for #11568 before enabling)"
    ),
)


def _make_broker(dispatch_fn, tools, run_id="smoke-run"):
    """Build a real CodeExecBroker over *dispatch_fn* for *tools*."""
    from chat_workflow.code_exec.broker import CodeExecBroker

    return CodeExecBroker(
        dispatch_fn,
        tools,
        frozenset(),
        run_id,
        f"autobot:codeexec:security:events:{run_id}",
        progress_channel=f"workflow:{run_id}",
    )


async def _run(program: str, tools, dispatch_fn):
    """Execute *program* through the real executor + broker; return SandboxResult."""
    from chat_workflow.code_exec.shim_codegen import generate_shim_module
    from secure_sandbox_executor import CODEEXEC_TIMEOUT_SECONDS, SecureSandboxExecutor

    shim_src = generate_shim_module(tools)
    broker = _make_broker(dispatch_fn, tools)
    executor = SecureSandboxExecutor()
    result = await executor.execute_with_stdio_broker(program, shim_src, broker, CODEEXEC_TIMEOUT_SECONDS, "smoke-run")
    return result, broker


_TOOLS = ["web_search", "scrape_url"]


@pytest.mark.asyncio
async def test_smoke_two_readonly_tools_merge_in_one_dispatch():
    """A script calling two shim tools returns a merged result in ONE executor call.

    Asserts the broker dispatched exactly the two calls the script made and that
    the script's final answer is cleanly retrievable. Since GH#11613 the RPC
    stream is sentinel-framed and the pump captures only non-RPC stdout as the
    result, so ``result.stdout`` holds the script's RESULT line with no RPC
    transcript mixed in.
    """

    async def dispatch(tool, params):
        return {"tool": tool, "echo": params}

    program = textwrap.dedent("""
        import asyncio, json, autobot_tools

        async def main():
            a = await autobot_tools.web_search(query="hello")
            b = await autobot_tools.scrape_url(url="http://x")
            print("RESULT " + json.dumps({"a": a, "b": b}))

        asyncio.run(main())
        """)
    result, broker = await _run(program, _TOOLS, dispatch)

    assert broker._call_count == 2, "broker should see exactly the 2 shim calls"
    # The final answer must be recoverable from the run output.
    marker = [ln for ln in (result.stdout or "").splitlines() if ln.startswith("RESULT ")]
    assert marker, f"final RESULT line not cleanly retrievable; stdout={result.stdout!r}"
    payload = json.loads(marker[-1][len("RESULT ") :])
    assert payload["a"]["tool"] == "web_search"
    assert payload["b"]["tool"] == "scrape_url"


@pytest.mark.asyncio
async def test_smoke_network_is_disabled_in_sandbox():
    """An in-script outbound socket connect fails — the container has no network."""

    async def dispatch(tool, params):
        return {"ok": True}

    program = textwrap.dedent("""
        import asyncio, json, socket, autobot_tools

        async def main():
            await autobot_tools.web_search(query="warmup")
            try:
                socket.create_connection(("1.1.1.1", 80), timeout=3)
                print("NET open")
            except OSError:
                print("NET blocked")

        asyncio.run(main())
        """)
    result, _ = await _run(program, _TOOLS, dispatch)
    assert "NET blocked" in (result.stdout or ""), "sandbox network must be disabled"
    assert "NET open" not in (result.stdout or "")


@pytest.mark.asyncio
async def test_smoke_budget_exhaustion_aborts_container():
    """A script exceeding the tool-call budget is aborted by the broker."""
    from chat_workflow.code_exec.broker import CODEEXEC_MAX_TOOL_CALLS
    from secure_sandbox_executor import SecureSandboxExecutor  # noqa: F401

    async def dispatch(tool, params):
        return {"ok": True}

    over = CODEEXEC_MAX_TOOL_CALLS + 5
    program = textwrap.dedent(f"""
        import asyncio, autobot_tools

        async def main():
            for _ in range({over}):
                await autobot_tools.web_search(query="x")

        asyncio.run(main())
        """)
    result, broker = await _run(program, _TOOLS, dispatch)
    assert broker.budget_exhausted, "budget should be reported exhausted"
    assert broker._call_count <= CODEEXEC_MAX_TOOL_CALLS, "no dispatch past the cap"


@pytest.mark.asyncio
async def test_smoke_multi_frame_reply_reassembled():
    """A dispatch result larger than one Docker frame is delivered intact.

    Exercises the ``_demux_frames`` reassembly + line buffering under a payload
    that spans multiple 4KiB socket reads.
    """
    big = "z" * (16 * 1024)

    async def dispatch(tool, params):
        return {"blob": big}

    program = textwrap.dedent("""
        import asyncio, json, autobot_tools

        async def main():
            r = await autobot_tools.web_search(query="big")
            print("LEN " + str(len(r["blob"])))

        asyncio.run(main())
        """)
    result, _ = await _run(program, _TOOLS, dispatch)
    assert f"LEN {len(big)}" in (result.stdout or ""), "large reply must survive demux intact"
