# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Regression tests for the fleet "Test Connection" SSH argv builders (#12476).

Bug: both ``_build_key_ssh_command`` and ``_build_password_ssh_command``
built argv containing a stray duplicate ``"-o"`` token with no value:

    "-o", "StrictHostKeyChecking=accept-new",
    "-o",          # <-- stray
    "-o",          # <-- this -o's value becomes the literal string "-o"
    "ConnectTimeout=10",

``ssh`` consumed the second ``-o`` and took the following ``-o`` as its
*value*, then failed to parse it as a config keyword and aborted with
``no argument after keyword "-o"`` -- so Test Connection never ran the
real command, for both key- and password-based auth.

These tests assert the built argv is well-formed: every ``-o`` token is
immediately followed by a ``key=value`` token (never another bare flag).

The two builders are pure functions (no DB/FastAPI/encryption dependency),
but ``api/nodes.py`` as a whole registers FastAPI routes at import time
(``response_model=...`` decoration fails against the MagicMock Pydantic
stubs used elsewhere in this test suite -- see ``conftest.py``). Rather
than importing the whole module, this test AST-extracts just the two
target function definitions and execs them in an isolated namespace, so
it has zero dependency on FastAPI/SQLAlchemy/DB stubs.
"""

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

_NODES_PY = Path(__file__).parent / "nodes.py"
_WANTED_FUNCTIONS = {"_build_key_ssh_command", "_build_password_ssh_command"}


def _load_pure_functions() -> dict:
    """AST-extract and exec only the target function defs from nodes.py."""
    tree = ast.parse(_NODES_PY.read_text(encoding="utf-8"), filename=str(_NODES_PY))
    wanted_nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in _WANTED_FUNCTIONS]
    assert len(wanted_nodes) == len(_WANTED_FUNCTIONS), (
        f"Expected to find {sorted(_WANTED_FUNCTIONS)} in {_NODES_PY}, "
        f"found {sorted(n.name for n in wanted_nodes)}. Rename tracking broke."
    )
    module = ast.Module(body=wanted_nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    # Annotations reference ConnectionTestRequest -- only needed for the
    # `def` signature to evaluate; the functions themselves never touch it.
    namespace: dict = {"ConnectionTestRequest": object}
    exec(compile(module, filename=str(_NODES_PY), mode="exec"), namespace)  # noqa: S102
    return namespace


_functions = _load_pure_functions()
_build_key_ssh_command = _functions["_build_key_ssh_command"]
_build_password_ssh_command = _functions["_build_password_ssh_command"]


def _fake_request(**overrides) -> SimpleNamespace:
    """Minimal stand-in for ConnectionTestRequest -- the builders only read attrs."""
    defaults = {
        "ssh_user": "autobot",
        "ip_address": "10.0.0.5",
        "ssh_port": 22,
        "password": "s3cret",
        "auth_method": "key",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _assert_well_formed_o_options(argv: list) -> None:
    """Every '-o' token must be immediately followed by a 'key=value' token."""
    for i, token in enumerate(argv):
        if token == "-o":
            assert i + 1 < len(argv), f"'-o' at index {i} has no following value: {argv}"
            value = argv[i + 1]
            assert value != "-o", f"'-o' immediately followed by another '-o': {argv}"
            assert not value.startswith("-"), f"'-o' followed by a flag-like token {value!r}: {argv}"
            assert "=" in value, f"'-o' value {value!r} is not key=value: {argv}"


class TestBuildKeySshCommand:
    """_build_key_ssh_command -- key-based auth argv (#12476)."""

    def test_no_stray_o_tokens(self):
        argv = _build_key_ssh_command(_fake_request(), "uname -a")
        _assert_well_formed_o_options(argv)

    def test_exact_argv(self):
        request = _fake_request(ssh_user="autobot", ip_address="10.0.0.5", ssh_port=22)
        argv = _build_key_ssh_command(request, "uname -a")
        assert argv == [
            "ssh",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "ConnectTimeout=10",
            "-o",
            "BatchMode=yes",
            "-p",
            "22",
            "autobot@10.0.0.5",
            "uname -a",
        ]


class TestBuildPasswordSshCommand:
    """_build_password_ssh_command -- sshpass/password-based auth argv (#12476)."""

    def test_no_stray_o_tokens(self):
        argv = _build_password_ssh_command(_fake_request(), "uname -a")
        _assert_well_formed_o_options(argv)

    def test_exact_argv(self):
        request = _fake_request(ssh_user="autobot", ip_address="10.0.0.5", ssh_port=22, password="s3cret")
        argv = _build_password_ssh_command(request, "uname -a")
        assert argv == [
            "sshpass",
            "-p",
            "s3cret",
            "ssh",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "ConnectTimeout=10",
            "-o",
            "PubkeyAuthentication=no",
            "-p",
            "22",
            "autobot@10.0.0.5",
            "uname -a",
        ]


@pytest.mark.parametrize("builder", [_build_key_ssh_command, _build_password_ssh_command])
def test_no_consecutive_o_flags(builder):
    """Neither builder ever emits two consecutive '-o' tokens (#12476)."""
    argv = builder(_fake_request(), "uname -a")
    for i in range(len(argv) - 1):
        assert not (argv[i] == "-o" and argv[i + 1] == "-o"), f"consecutive '-o' at index {i}: {argv}"
