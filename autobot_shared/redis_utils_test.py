# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Direct tests for the shared Redis decode helpers (#13290).

``decode_redis_list`` was added for ``FT.INFO`` walking and was previously
covered only indirectly, through two setup scripts. It is in ``autobot_shared``
and therefore reachable by any caller, so it gets its own coverage here.
"""

from autobot_shared.redis_utils import decode_redis_list, decode_redis_value


class TestDecodeRedisValue:
    """Leaf decoding."""

    def test_bytes_are_decoded(self):
        assert decode_redis_value(b"hello") == "hello"

    def test_str_passes_through(self):
        assert decode_redis_value("hello") == "hello"

    def test_none_passes_through(self):
        assert decode_redis_value(None) is None


class TestDecodeRedisList:
    """Recursive RESP-array decoding."""

    def test_flat_list_of_bytes(self):
        assert decode_redis_list([b"a", b"b"]) == ["a", "b"]

    def test_nested_lists_are_walked_to_every_leaf(self):
        assert decode_redis_list([b"a", ["b", [b"c"]]]) == ["a", ["b", ["c"]]]

    def test_already_decoded_input_is_not_double_decoded(self):
        assert decode_redis_list(["a", ["b"]]) == ["a", ["b"]]

    def test_non_str_scalars_pass_through(self):
        assert decode_redis_list([1, 1.5, None]) == [1, 1.5, None]

    def test_bare_scalar_is_delegated_to_decode_redis_value(self):
        assert decode_redis_list(b"solo") == "solo"
        assert decode_redis_list(None) is None

    def test_empty_list(self):
        assert decode_redis_list([]) == []

    def test_ft_info_shape_is_decoded_end_to_end(self):
        """The shape this helper exists for: a nested FT.INFO reply."""
        reply = [b"index_name", b"llama_index", b"attributes", [[b"type", b"VECTOR", b"DIM", b"768"]]]

        assert decode_redis_list(reply) == [
            "index_name",
            "llama_index",
            "attributes",
            [["type", "VECTOR", "DIM", "768"]],
        ]
