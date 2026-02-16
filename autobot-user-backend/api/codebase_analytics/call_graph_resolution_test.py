# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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

from backend.api.codebase_analytics.endpoints.call_graph import (
    _extract_import_context,
    _resolve_callee_id,
)
from backend.api.codebase_analytics.endpoints.shared import (
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
        ctx.add_import(
            module="src.utils.redis_client", name="get_redis_client", alias="get_redis"
        )

        assert (
            ctx.resolve_name("get_redis") == "src.utils.redis_client.get_redis_client"
        )
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
        assert is_external_module("backend.api.routes") is False

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
        code = "from typing import Dict, List, Optional"
        tree = ast.parse(code)
        ctx = _extract_import_context(tree)

        assert ctx.resolve_name("Dict") == "typing.Dict"
        assert ctx.resolve_name("List") == "typing.List"
        assert ctx.resolve_name("Optional") == "typing.Optional"

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
        assert ctx.resolve_name("hf") == "src.utils.helper.helper_func"


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
        functions = {
            "src.utils.redis_client.get_redis_client": {"name": "get_redis_client"}
        }

        ctx = ImportContext()
        ctx.add_import(
            module="src.utils.redis_client", name="get_redis_client", alias="get_redis"
        )

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
