# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``generate_cache_key`` must work against the REAL xxhash, not a stand-in.

#14731: the repo moved to ``xxhash>=4.0.0``, which removed ``str`` input —
``xxhash.xxh64("text")`` now raises ``TypeError: Strings must be encoded before
hashing``. ``LLMResponseCache.generate_cache_key`` passed a ``str``, so every
cache-key generation on the deployed backend raised, on every LLM call.

The whole suite stayed green. Every test that touches xxhash replaces it:

    tests/llm_interface_pkg/test_model_param_registry.py:41  xxh64=MagicMock(...)
    tests/llm_interface_pkg/test_provider_metadata.py:42     xxh64=MagicMock(...)
    tests/test_claude_adapter_wiring.py:50                   xh.xxh64 = MagicMock(...)

A ``MagicMock`` accepts a ``str`` happily and hands back a canned digest, so
those tests proved the caller was well-formed against a stand-in that cannot
reject anything. 12/12 shards, ``smoke-test`` and ``startup-import-smoke`` all
passed while the line was broken.

So this file's one job is to put the real library on the other end. It asserts
that explicitly, because a sibling test leaking a stub into ``sys.modules``
would otherwise turn this test back into the thing it exists to replace.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Imported directly, NOT via importorskip: xxhash is a hard dependency
# (autobot-backend/requirements.txt pins `xxhash>=4.0.0`), so an environment
# without it must fail loudly rather than skip this file back into the
# all-mocks state that let #14731 through.
import xxhash

_CACHE_PATH = Path(__file__).resolve().parent / "cache.py"


def _real_cache_module():
    """Load ``cache.py`` from disk, bypassing conftest's package stub.

    #14731 review: ``autobot-backend/conftest.py`` puts ``llm_shared.cache``
    into ``sys.modules`` as a bare stub and then assigns
    ``LLMResponseCache = MagicMock()`` on it, for the benefit of
    ``services.llm_service``. A plain ``from llm_shared.cache import
    LLMResponseCache`` therefore binds that MagicMock — so the first version of
    this file asserted against a mock and passed identically with or without
    the fix it was written to protect. The test guarded ``xxhash`` against
    being a stand-in and never checked the class under test.

    Loading the file under its own module name leaves the shared stub alone —
    other tests still get the MagicMock they expect — while this file gets the
    real class.
    """
    spec = importlib.util.spec_from_file_location("llm_shared_cache_real_14731", _CACHE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not build an import spec for {_CACHE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_CACHE = _real_cache_module()
LLMResponseCache = _CACHE.LLMResponseCache

_MESSAGES = [{"role": "user", "content": "summarise this document"}]


def _key(**overrides) -> str:
    """Call the real method unbound — it reads no ``self`` state.

    Constructing ``LLMResponseCache`` would pull SSOT config in, which has
    nothing to do with hashing and would give this test a second way to fail.
    """
    params = {
        "messages": _MESSAGES,
        "model": "a-model",
        "temperature": 0.7,
        "max_tokens": 512,
    }
    params.update(overrides)
    return LLMResponseCache.generate_cache_key(None, **params)


def test_the_code_under_test_is_real_not_a_stand_in() -> None:
    """Guard the guard — and check what the CODE binds, not what this file did.

    The first version of this test checked only that ``xxhash`` was real. It
    was; the *class* was a MagicMock from conftest, so every assertion below
    passed against a mock and the file proved nothing. Both bindings are
    checked now, and the xxhash one is read off the loaded module rather than
    off this file's own import — that is the object ``generate_cache_key``
    actually calls.
    """
    assert not isinstance(LLMResponseCache, MagicMock), (
        "LLMResponseCache is a MagicMock — the real module did not load, so "
        "everything below would assert against a stand-in that accepts "
        "anything. This is the exact failure that let #14731 ship."
    )
    assert hasattr(LLMResponseCache, "generate_cache_key")

    assert not isinstance(_CACHE.xxhash.xxh64, MagicMock), (
        "the loaded module's xxhash is a MagicMock — a mock accepts str input "
        "and would hide the #14731 break entirely."
    )
    assert hasattr(_CACHE.xxhash, "VERSION"), "xxhash does not look like the real module"


def test_the_real_library_rejects_str_input() -> None:
    """Pin the upstream behaviour this fix exists for.

    If a future xxhash accepts ``str`` again, the encode below stops being
    load-bearing and this test says so rather than quietly passing.
    """
    if int(xxhash.VERSION.split(".")[0]) < 4:
        pytest.skip("xxhash 3 accepted str; the encode is a no-op there")

    with pytest.raises(TypeError):
        xxhash.xxh64("not bytes")


def test_generate_cache_key_does_not_raise_under_xxhash_4() -> None:
    """The #14731 regression itself.

    Without the ``.encode("utf-8")`` this raises TypeError against the real
    library — which is what makes this test able to fail.
    """
    key = _key()

    assert key.startswith("llm_cache:")
    digest = key.split(":", 1)[1]
    assert len(digest) == 16, f"xxh64 hexdigest should be 16 chars, got {digest!r}"
    int(digest, 16)  # raises if it is not hex


def test_the_key_is_deterministic_and_input_sensitive() -> None:
    """A constant would satisfy the shape assertions above; this catches it."""
    assert _key() == _key(), "the same inputs must produce the same key"

    varied = {
        "model": _key(model="another-model"),
        "temperature": _key(temperature=0.1),
        "max_tokens": _key(max_tokens=1024),
        "messages": _key(messages=[{"role": "user", "content": "different"}]),
    }
    baseline = _key()
    for field, other in varied.items():
        assert other != baseline, f"changing {field} must change the cache key"


def test_utf8_encoding_keeps_keys_stable_across_the_xxhash_major() -> None:
    """Existing cache entries must stay addressable after the bump.

    xxhash 3 encoded ``str`` as UTF-8 internally, so encoding explicitly
    reproduces the digest it used to return. This pins that: it is the
    difference between a dependency bump and a silent cache-wide eviction.
    """
    sample = "('gpt', 0.7, None, 1.0, 512, False)"

    # The digest xxhash 3.8.1 returned for this text, taken from the real 3.x
    # library. xxhash 4 must produce the same for the UTF-8 bytes.
    assert xxhash.xxh64(sample.encode("utf-8")).hexdigest() == "58f380f25127f376"


def test_non_ascii_content_is_hashed_rather_than_exploding() -> None:
    """`str(key_data)` can carry any user text; encoding must not be lossy."""
    key = _key(messages=[{"role": "user", "content": "Ω sum — naïve café 日本語"}])

    assert key.startswith("llm_cache:")
    assert key != _key(), "distinct content must produce a distinct key"
