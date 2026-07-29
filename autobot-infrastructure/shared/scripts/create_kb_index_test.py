# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for create_kb_index — the KB index build (#12840).

These drive the real code path with a fake Redis client rather than a live one:
``create_index_with_correct_dimensions`` DROPs the index before recreating it,
so running it against a real instance would discard the indexed vectors.
"""

import importlib.util
import pathlib
import sys

import pytest

_MODULE_PATH = pathlib.Path(__file__).with_name("create_kb_index.py")


def _load_module():
    """Import create_kb_index by path — its directory is not a package."""
    spec = importlib.util.spec_from_file_location("create_kb_index", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["create_kb_index"] = module
    spec.loader.exec_module(module)
    return module


kb_index = _load_module()


class FakeRedis:
    """Records every command, and answers FT.INFO like a freshly built index."""

    def __init__(self, drop_error: Exception | None = None):
        self.commands: list[tuple] = []
        self._drop_error = drop_error

    def execute_command(self, *args):
        self.commands.append(args)
        if args[0] == "FT.DROPINDEX" and self._drop_error is not None:
            raise self._drop_error
        if args[0] == "FT.INFO":
            return [b"attributes", [[b"vector", b"dim", str(kb_index.VECTOR_DIM).encode()]]]
        return "OK"

    def command_names(self) -> list[str]:
        return [c[0] for c in self.commands]

    def first(self, name: str) -> tuple:
        return next(c for c in self.commands if c[0] == name)


@pytest.fixture
def redis(monkeypatch):
    client = FakeRedis()
    monkeypatch.setattr(kb_index, "get_redis_client", lambda **_: client)
    return client


def test_module_imports_without_redisvl():
    """#12840: the module referenced IndexSchema, which nothing ever imported.

    redisvl is not a repo dependency, and the repo already documents its import
    chain as broken, so the schema must be expressible without it.
    """
    assert "redisvl" not in sys.modules
    assert not hasattr(kb_index, "IndexSchema")


def test_create_runs_end_to_end(redis):
    """The whole function completes — this used to raise NameError mid-way."""
    assert kb_index.create_index_with_correct_dimensions() is True
    assert redis.command_names() == ["FT.DROPINDEX", "FT.DROPINDEX", "FT.CREATE", "FT.INFO"]


def test_create_command_declares_the_expected_index(redis):
    """The FT.CREATE argv is the only schema definition, so pin its shape."""
    kb_index.create_index_with_correct_dimensions()
    create = redis.first("FT.CREATE")

    assert create[1] == kb_index.INDEX_NAME
    assert create[create.index("PREFIX") + 2] == kb_index.INDEX_PREFIX
    assert create[create.index("DIM") + 1] == str(kb_index.VECTOR_DIM)
    assert create[create.index("DISTANCE_METRIC") + 1] == "COSINE"
    assert create[create.index("TYPE") + 1] == "FLOAT32"


def test_dimension_is_declared_as_a_string(redis):
    """redis-py rejects a bare int in argv; DIM must be stringified."""
    kb_index.create_index_with_correct_dimensions()
    create = redis.first("FT.CREATE")

    assert isinstance(create[create.index("DIM") + 1], str)


def test_legacy_index_is_dropped_too(redis):
    """Both the current and the pre-rename index are cleared before rebuild."""
    kb_index.create_index_with_correct_dimensions()
    dropped = [c[1] for c in redis.commands if c[0] == "FT.DROPINDEX"]

    assert dropped == [kb_index.INDEX_NAME, kb_index.LEGACY_INDEX_NAME]


def test_missing_index_on_drop_is_not_fatal(monkeypatch):
    """A first-ever run has nothing to drop; that must not abort the build."""
    client = FakeRedis(drop_error=RuntimeError("Unknown index name"))
    monkeypatch.setattr(kb_index, "get_redis_client", lambda **_: client)

    assert kb_index.create_index_with_correct_dimensions() is True
    assert "FT.CREATE" in client.command_names()


def test_unreachable_redis_reports_failure(monkeypatch):
    monkeypatch.setattr(kb_index, "get_redis_client", lambda **_: None)

    assert kb_index.create_index_with_correct_dimensions() is False
