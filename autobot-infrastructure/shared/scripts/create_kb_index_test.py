# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for create_kb_index — the KB index build (#12840).

These drive the real code path with a fake Redis client rather than a live one:
``create_index_with_correct_dimensions`` builds the index; it never drops one (#21383), so a stale index
is rebuilt only through the approved wipe proposal (``--request-wipe``).
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
    """Records every command, and answers FT.INFO like a freshly built index.

    ``get_redis_client`` returns a ``decode_responses=True`` client
    (``autobot_shared/redis_management/config.py:61,153``), so a live
    ``FT.INFO`` reply is a nested list of ``str``, never ``bytes`` — mocking
    ``bytes`` here would let a bytes-literal-indexing bug pass vacuously
    (#13290).
    """

    def __init__(self, drop_error: Exception | None = None):
        self.commands: list[tuple] = []
        self._drop_error = drop_error

    def execute_command(self, *args):
        self.commands.append(args)
        if args[0] == "FT.DROPINDEX" and self._drop_error is not None:
            raise self._drop_error
        if args[0] == "FT.INFO":
            return ["attributes", [["identifier", "vector", "attribute", "vector", "dim", str(kb_index.VECTOR_DIM)]]]
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
    assert redis.command_names() == ["FT.CREATE", "FT.INFO"]


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


def test_no_command_ever_drops_an_index(redis):
    """#21383: the build never issues a drop; the wipe is a human-approved proposal."""
    kb_index.create_index_with_correct_dimensions()

    assert "FT.DROPINDEX" not in redis.command_names()
    assert not hasattr(kb_index, "_drop_existing_indexes")


def test_an_existing_index_fails_the_build_without_a_drop(monkeypatch):
    """A stale index answers FT.CREATE with an error; the build reports failure and still drops nothing."""

    class Existing(FakeRedis):
        def execute_command(self, *args):
            super().execute_command(*args)
            if args[0] == "FT.CREATE":
                raise RuntimeError("Index already exists")
            return "OK"

    client = Existing()
    monkeypatch.setattr(kb_index, "get_redis_client", lambda **_: client)

    assert kb_index.create_index_with_correct_dimensions() is False
    assert "FT.DROPINDEX" not in client.command_names()


def test_request_wipe_flag_proposes_and_creates_nothing(redis, monkeypatch):
    """``--request-wipe`` / ``--dry-run`` go to the shared proposal entry and issue no Redis command."""
    import kb_wipe_cli

    asked = []

    async def fake_request(dry_run):
        asked.append(dry_run)
        return True

    monkeypatch.setattr(kb_wipe_cli, "request_wipe", fake_request)
    assert kb_index.main(["--request-wipe"]) == 0
    assert kb_index.main(["--dry-run"]) == 0
    assert asked == [False, True]
    assert redis.commands == []


def test_unreachable_redis_reports_failure(monkeypatch):
    monkeypatch.setattr(kb_index, "get_redis_client", lambda **_: None)

    assert kb_index.create_index_with_correct_dimensions() is False


def test_verify_index_creation_reads_a_decoded_ft_info_reply(caplog):
    """#13290: bytes-literal indexing on a decoded FT.INFO reply raised ValueError.

    Drives ``_verify_index_creation`` directly against the realistic
    ``decode_responses=True`` shape (str elements throughout) and asserts the
    dimension is actually logged rather than the walk raising or silently
    finding nothing.
    """
    client = FakeRedis()

    with caplog.at_level("INFO", logger=kb_index.logger.name):
        kb_index._verify_index_creation(client)

    assert f"Vector dimension: {kb_index.VECTOR_DIM}" in caplog.text
