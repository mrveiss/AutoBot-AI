# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for call graph resolution with import context (Issue #713)

Tests the following functionality:
- ImportContext class for tracking imports
- Cross-module function resolution
- External library call filtering
- Alias handling in imports
"""

import ast

from api.codebase_analytics.endpoints.call_graph import (
    FunctionCallVisitor,
    _extract_callee_name,
    _extract_import_context,
    _resolve_callee_id,
    extract_dotted_callee,
)
from api.codebase_analytics.endpoints.shared import (
    COMMON_THIRD_PARTY,
    STDLIB_MODULES,
    ImportContext,
    is_external_module,
)


class TestImportContext:
    """Tests for ImportContext class."""

    def test_add_module_import(self):
        """Test adding a simple module import."""
        ctx = ImportContext()
        ctx.add_import(module="json")

        assert ctx.resolve_name("json") == "json"

    def test_add_module_import_with_alias(self):
        """Test adding module import with alias."""
        ctx = ImportContext()
        ctx.add_import(module="numpy", alias="np")

        assert ctx.resolve_name("np") == "numpy"
        assert ctx.resolve_name("numpy") is None  # Original name not tracked

    def test_add_from_import(self):
        """Test adding from...import statement."""
        ctx = ImportContext()
        ctx.add_import(module="src.utils.redis_client", name="get_redis_client")

        resolved = ctx.resolve_name("get_redis_client")
        assert resolved == "src.utils.redis_client.get_redis_client"

    def test_add_from_import_with_alias(self):
        """Test adding from...import with alias."""
        ctx = ImportContext()
        ctx.add_import(module="src.utils.redis_client", name="get_redis_client", alias="get_redis")

        assert ctx.resolve_name("get_redis") == "src.utils.redis_client.get_redis_client"
        assert ctx.resolve_name("get_redis_client") is None

    def test_is_external_stdlib(self):
        """Test detection of stdlib imports as external."""
        ctx = ImportContext()
        ctx.add_import(module="json", name="loads")

        assert ctx.is_external("loads") is True

    def test_is_external_third_party(self):
        """Test detection of third-party imports as external."""
        ctx = ImportContext()
        ctx.add_import(module="fastapi", name="APIRouter")

        assert ctx.is_external("APIRouter") is True

    def test_is_external_internal(self):
        """Test detection of internal imports as not external."""
        ctx = ImportContext()
        ctx.add_import(module="src.utils.helper", name="helper_func")

        assert ctx.is_external("helper_func") is False

    def test_is_external_unknown_name(self):
        """Test is_external returns False for unknown names."""
        ctx = ImportContext()

        assert ctx.is_external("unknown_function") is False


class TestIsExternalModule:
    """Tests for is_external_module function."""

    def test_stdlib_module(self):
        """Test stdlib modules are detected as external."""
        assert is_external_module("json") is True
        assert is_external_module("os.path") is True
        assert is_external_module("asyncio") is True

    def test_third_party_module(self):
        """Test third-party modules are detected as external."""
        assert is_external_module("fastapi") is True
        assert is_external_module("pydantic.BaseModel") is True
        assert is_external_module("redis") is True

    def test_internal_module(self):
        """Test internal modules are detected correctly."""
        assert is_external_module("src.utils.helper") is False
        assert is_external_module("api.routes") is False

    def test_unknown_module(self):
        """Test unknown modules are assumed external."""
        assert is_external_module("some_unknown_package") is True


class TestExtractImportContext:
    """Tests for _extract_import_context function."""

    def test_extract_simple_import(self):
        """Test extracting simple import statement."""
        code = "import json"
        tree = ast.parse(code)
        ctx = _extract_import_context(tree)

        assert ctx.resolve_name("json") == "json"

    def test_extract_from_import(self):
        """Test extracting from...import statement."""
        code = "from pathlib import Path"
        tree = ast.parse(code)
        ctx = _extract_import_context(tree)

        assert ctx.resolve_name("Path") == "pathlib.Path"

    def test_extract_aliased_import(self):
        """Test extracting aliased import."""
        code = "import numpy as np"
        tree = ast.parse(code)
        ctx = _extract_import_context(tree)

        assert ctx.resolve_name("np") == "numpy"

    def test_extract_multiple_imports(self):
        """Test extracting multiple imports from one statement."""
        code = "from typing import Dict, List"
        tree = ast.parse(code)
        ctx = _extract_import_context(tree)

        assert ctx.resolve_name("Dict") == "typing.Dict"
        assert ctx.resolve_name("List") == "typing.List"
        # Optional is not part of this import statement, so it stays unresolved
        assert ctx.resolve_name("Optional") is None

    def test_skip_star_import(self):
        """Test that star imports are skipped."""
        code = "from module import *"
        tree = ast.parse(code)
        ctx = _extract_import_context(tree)

        # Star imports can't be tracked, so nothing should be resolved
        assert len(ctx.name_to_module) == 0

    def test_complex_code(self):
        """Test extracting imports from code with functions."""
        code = """
import json
from pathlib import Path
from utils.helper import helper_func as hf

def my_function():
    data = json.loads("{}")
    path = Path("/tmp")
    hf()
"""
        tree = ast.parse(code)
        ctx = _extract_import_context(tree)

        assert ctx.resolve_name("json") == "json"
        assert ctx.resolve_name("Path") == "pathlib.Path"
        assert ctx.resolve_name("hf") == "utils.helper.helper_func"


class TestResolveCalleeId:
    """Tests for _resolve_callee_id function with import context."""

    def test_resolve_same_module_function(self):
        """Test resolving function in same module."""
        functions = {"mymodule.helper": {"name": "helper"}}
        callee_id, is_external = _resolve_callee_id(
            callee_name="helper",
            module_path="mymodule",
            current_class=None,
            functions=functions,
        )

        assert callee_id == "mymodule.helper"
        assert is_external is False

    def test_resolve_same_class_method(self):
        """Test resolving method in same class."""
        functions = {"mymodule.MyClass.method": {"name": "method"}}
        callee_id, is_external = _resolve_callee_id(
            callee_name="method",
            module_path="mymodule",
            current_class="MyClass",
            functions=functions,
        )

        assert callee_id == "mymodule.MyClass.method"
        assert is_external is False

    def test_resolve_via_import_context(self):
        """Test resolving function via import context."""
        functions = {"src.utils.helper.do_something": {"name": "do_something"}}

        ctx = ImportContext()
        ctx.add_import(module="src.utils.helper", name="do_something")

        callee_id, is_external = _resolve_callee_id(
            callee_name="do_something",
            module_path="mymodule",
            current_class=None,
            functions=functions,
            import_context=ctx,
        )

        assert callee_id == "src.utils.helper.do_something"
        assert is_external is False

    def test_detect_external_stdlib_call(self):
        """Test detection of stdlib call as external."""
        functions = {}

        ctx = ImportContext()
        ctx.add_import(module="json", name="loads")

        callee_id, is_external = _resolve_callee_id(
            callee_name="loads",
            module_path="mymodule",
            current_class=None,
            functions=functions,
            import_context=ctx,
        )

        assert callee_id is None
        assert is_external is True

    def test_detect_external_third_party_call(self):
        """Test detection of third-party call as external."""
        functions = {}

        ctx = ImportContext()
        ctx.add_import(module="fastapi", name="APIRouter")

        callee_id, is_external = _resolve_callee_id(
            callee_name="APIRouter",
            module_path="mymodule",
            current_class=None,
            functions=functions,
            import_context=ctx,
        )

        assert callee_id is None
        assert is_external is True

    def test_unresolved_internal_call(self):
        """Test unresolved internal call is not marked external."""
        functions = {}

        callee_id, is_external = _resolve_callee_id(
            callee_name="unknown_func",
            module_path="mymodule",
            current_class=None,
            functions=functions,
        )

        assert callee_id is None
        assert is_external is False

    def test_resolve_with_alias(self):
        """Test resolving aliased import."""
        functions = {"src.utils.redis_client.get_redis_client": {"name": "get_redis_client"}}

        ctx = ImportContext()
        ctx.add_import(module="src.utils.redis_client", name="get_redis_client", alias="get_redis")

        callee_id, is_external = _resolve_callee_id(
            callee_name="get_redis",
            module_path="mymodule",
            current_class=None,
            functions=functions,
            import_context=ctx,
        )

        assert callee_id == "src.utils.redis_client.get_redis_client"
        assert is_external is False


class TestStdlibAndThirdPartyConstants:
    """Tests for stdlib and third-party module constants."""

    def test_common_stdlib_modules_present(self):
        """Test common stdlib modules are in the set."""
        assert "json" in STDLIB_MODULES
        assert "os" in STDLIB_MODULES
        assert "sys" in STDLIB_MODULES
        assert "pathlib" in STDLIB_MODULES
        assert "typing" in STDLIB_MODULES
        assert "asyncio" in STDLIB_MODULES

    def test_common_third_party_present(self):
        """Test common third-party packages are in the set."""
        assert "fastapi" in COMMON_THIRD_PARTY
        assert "pydantic" in COMMON_THIRD_PARTY
        assert "redis" in COMMON_THIRD_PARTY
        assert "requests" in COMMON_THIRD_PARTY
        assert "numpy" in COMMON_THIRD_PARTY


# ---------------------------------------------------------------------------
# Issue #13492 — the dotted-name external check was unreachable
# ---------------------------------------------------------------------------


def _walk(source: str, module_path: str = "pkg.mod"):
    """Run the real visitor over *source* and return its three collections.

    Drives ``FunctionCallVisitor`` exactly as ``_analyze_python_files`` does,
    including ``_extract_import_context``, so these assertions are about the
    production path rather than about ``_resolve_callee_id`` called directly
    with a synthetic argument — which is the only way the branch under test
    could ever fire before #13492.
    """
    tree = ast.parse(source)
    functions: dict = {}
    call_edges: list = []
    external_calls: list = []
    # Two passes: the first registers definitions so the second can resolve
    # against them, matching the endpoint's definitions-then-calls ordering.
    for _ in range(2):
        visitor = FunctionCallVisitor(
            file_path=f"{module_path}.py",
            module_path=module_path,
            functions=functions,
            call_edges=call_edges,
            external_calls=external_calls,
            import_context=_extract_import_context(tree),
        )
        visitor.visit(tree)
        if not call_edges and not external_calls:
            continue
        break
    return functions, call_edges, external_calls


class TestDottedCalleeExtraction:
    """``_extract_dotted_callee`` produces the input the external check needs."""

    @staticmethod
    def _first_call(source: str):
        return next(n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Call))

    def test_module_attribute_call_yields_the_dotted_chain(self):
        assert extract_dotted_callee(self._first_call("json.loads(x)")) == "json.loads"

    def test_nested_attribute_call_yields_every_component(self):
        assert extract_dotted_callee(self._first_call("os.path.join(a, b)")) == "os.path.join"

    def test_method_call_on_self_is_still_dotted(self):
        assert extract_dotted_callee(self._first_call("self.helper(1)")) == "self.helper"

    def test_a_call_with_no_static_base_yields_none(self):
        """``get_client().send()`` has no base name to test against stdlib."""
        assert extract_dotted_callee(self._first_call("get_client().send(1)")) is None
        assert extract_dotted_callee(self._first_call("items[0].run()")) is None

    def test_a_plain_name_call_yields_none(self):
        assert extract_dotted_callee(self._first_call("helper(1)")) is None


class TestExternalCallsAreCountedFromTheAstPath:
    """The regression #13492 describes, measured end to end."""

    def test_bare_import_plus_attribute_call_is_counted_external(self):
        """``import json`` + ``json.loads(...)`` is an external library call.

        Before #13492 this produced **zero** external calls and one unresolved
        edge named ``loads``: ``_extract_callee_name`` strips the attribute to
        its last component, ``ImportContext`` has no ``loads`` entry (a bare
        ``import json`` registers only ``json``), and the dotted check that
        would have caught it never saw a dotted name.
        """
        _, call_edges, external = _walk(
            "import json\n\n\ndef read(blob):\n    return json.loads(blob)\n",
        )

        assert [e["to_name"] for e in external] == [
            "json.loads"
        ], f"expected one external call to json.loads, got {external} / edges {call_edges}"
        assert not any(
            e["to_name"] == "loads" for e in call_edges
        ), f"json.loads still recorded as a bare unresolved 'loads' edge: {call_edges}"

    def test_third_party_attribute_call_is_counted_external(self):
        _, _, external = _walk("import requests\n\n\ndef fetch(u):\n    return requests.get(u)\n")
        assert [e["to_name"] for e in external] == ["requests.get"]

    def test_an_unknown_base_is_not_assumed_external(self):
        """Only the two explicit sets count. An unindexed project module does not.

        This is the control for the opposite error: a dotted name whose base is
        unrecognised must stay unresolved, not be silently reclassified as a
        library call and dropped from the graph.
        """
        _, call_edges, external = _walk("import mycompany\n\n\ndef go():\n    return mycompany.run()\n")
        assert external == []
        assert [e["to_name"] for e in call_edges] == ["run"]

    def test_method_calls_still_resolve_to_their_class(self):
        """The reason ``_extract_callee_name`` keeps returning the bare attr.

        ``resolve_callee`` builds candidate ids as
        ``module.Class.<callee_name>``. Had #13492 been "fixed" by making
        ``_extract_callee_name`` return the dotted chain, this call would look
        for ``pkg.mod.Worker.self.helper`` and resolve nothing — every
        method-to-method edge in the graph would silently become unresolved.
        This test is what makes that fix fail instead of pass.
        """
        source = (
            "class Worker:\n"
            "    def helper(self):\n        return 1\n\n"
            "    def run(self):\n        return self.helper()\n"
        )
        _, call_edges, external = _walk(source)

        helper_edges = [e for e in call_edges if e["to_name"] == "helper"]
        assert helper_edges, f"self.helper() produced no edge named 'helper': {call_edges}"
        assert helper_edges[0]["resolved"] is True, f"self.helper() stopped resolving: {helper_edges[0]}"
        assert external == []

    def test_the_name_in_prose_is_not_a_call(self):
        """Contrast fixture: the string present, the construct absent.

        A guard that greps for ``json.loads`` is satisfied by a docstring, a
        ``#`` comment or a string literal saying so, and would report this file
        as making an external call. The visitor parses, so it must report none
        — and the assertion below proves the fixture really does carry the
        string, so a pass is not an artefact of an empty fixture.
        """
        source = (
            '"""This module deliberately mentions json.loads without calling it."""\n'
            "import json\n\n\n"
            "def read(blob):\n"
            '    """Parse *blob*. Historically this used json.loads directly."""\n'
            "    # json.loads(blob) -- replaced by the hardened reader\n"
            '    note = "json.loads is not called here"\n'
            "    return note\n"
        )
        assert source.count("json.loads") == 4

        _, call_edges, external = _walk(source)
        assert external == [], f"prose matched as an external call: {external}"
        assert call_edges == [], f"prose matched as a call edge: {call_edges}"


def test_extract_callee_name_never_returns_a_dotted_name():
    """The premise that made the branch unreachable, asserted rather than assumed.

    If this ever stops holding, ``_resolve_callee_id``'s dotted check would be
    reachable from ``callee_name`` again and the ``dotted_name`` parameter
    would be redundant — but so would every ``module.Class.<name>`` candidate
    the resolver builds. Either way it is a change that must be noticed.
    """
    sources = ["json.loads(x)", "os.path.join(a, b)", "self.helper(1)", "obj.attr.method()"]
    for src in sources:
        node = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Call))
        name = _extract_callee_name(node)
        assert name is not None and "." not in name, f"{src!r} -> {name!r}"


def test_an_aliased_import_is_external_not_unresolved():
    """`import json as j; j.loads(x)` (CodeRabbit, #13492).

    The dotted check tested the raw first token against the module sets, and
    `j` is in neither -- the alias lives in the import context. So a plainly
    external call was recorded as an unresolved edge, which is the one verdict
    that means "the graph does not know", reserved for calls it genuinely
    cannot place.
    """
    ctx = ImportContext()
    ctx.add_import("json", alias="j")

    assert _resolve_callee_id("loads", "m", None, {}, ctx, dotted_name="j.loads") == (None, True)


def test_a_local_name_does_not_capture_an_external_dotted_call():
    """`def get(): ...` in a module that also calls `requests.get(url)`.

    `_shared_resolve_callee` matches on the BARE name, so it resolved to the
    local `get` and returned before the dotted check ran -- recording a false
    local edge and losing the external call entirely. The receiver decides:
    `a.b()` is never a call to a local `b`.
    """
    ctx = ImportContext()
    ctx.add_import("requests")
    functions = {"m.get": {"name": "get"}}

    assert _resolve_callee_id("get", "m", None, functions, ctx, dotted_name="requests.get") == (None, True)


def test_a_genuine_bare_local_call_still_resolves_locally():
    """The contrast, and the one that stops the fix above from being a regression.

    Classifying dotted calls first must not make every call external: with no
    receiver, the same local `get` must still resolve to its own id.
    """
    ctx = ImportContext()
    ctx.add_import("requests")
    functions = {"m.get": {"name": "get"}}

    assert _resolve_callee_id("get", "m", None, functions, ctx, dotted_name=None) == ("m.get", False)


def test_a_local_class_named_like_stdlib_resolves_locally():
    """`class json` with a `loads` method, and no `import json` (CodeRabbit, #13492).

    Classifying dotted calls early -- the fix for the two cases above -- made
    `json` match STDLIB_MODULES and return external before anything looked for
    a local definition. `resolve_callee` could not have caught it either: it
    builds `module.<current_class>.<name>` and never uses the RECEIVER, so
    `m.json.loads` is a candidate it cannot construct.
    """
    ctx = ImportContext()
    functions = {"m.json.loads": {"name": "loads"}}

    assert _resolve_callee_id("loads", "m", None, functions, ctx, dotted_name="json.loads") == ("m.json.loads", False)


def test_an_explicit_import_outranks_a_local_class_of_the_same_name():
    """The discriminator for the test above, and the reason tier 1 exists.

    With `import json` present, `json.loads(x)` is the stdlib call however the
    module names its own classes. If this passed only because the local lookup
    never ran, the test above would be meaningless -- the two fail in opposite
    directions, so both are needed.
    """
    ctx = ImportContext()
    ctx.add_import("json")
    functions = {"m.json.loads": {"name": "loads"}}

    assert _resolve_callee_id("loads", "m", None, functions, ctx, dotted_name="json.loads") == (None, True)
