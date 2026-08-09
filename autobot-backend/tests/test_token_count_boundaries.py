# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Token counting at context-fit decision boundaries (#13694).

Every context-fitting decision was made against `len(text.split()) * 1.3`,
whose own docstring conceded it held "for English prose" — which is exactly
where large prompts do not come from.

The three failure classes below are the ones the issue named, and the numbers
are why the fix matters rather than being tidiness: the estimate gates the 90%
auto-summarise trigger and whether compression runs at all, so under-counting
means the threshold is reached only after the real window is blown.
"""

import pytest

from autobot_shared.token_count import estimate_fast, exact_from_usage, resolve_tokens


# The heuristic this replaced, kept here as the thing under comparison.
def _words_times_1_3(text: str) -> int:
    return int(len(text.split()) * 1.3)


CODE = (
    "async def get_chat_history_manager(request: Request) -> ChatHistoryManager:\n"
    "    return await ResourceFactory.get_chat_history_manager(request)"
)
JSON_PAYLOAD = '{"rows":[{"id":1,"name":"a"},{"id":2,"name":"b"}],"meta":{"total":2,"ok":true}}'
CJK = "部署已於上午九點完成並且沒有任何錯誤發生系統運行正常" * 4
PROSE = "The deployment ran at nine in the morning and completed without any errors at all."


class TestTheThreeFailureClasses:
    """Each asserts the new estimate no longer collapses the way the old one did."""

    def test_cjk_is_no_longer_counted_as_a_single_word(self):
        """`text.split()` returns ONE element for a non-space-delimited script.

        AutoBot is i18n across 11 locales, so this is not hypothetical.
        """
        old = _words_times_1_3(CJK)
        new = estimate_fast(CJK)

        assert old <= 2, "precondition: the old heuristic collapses CJK"
        assert new > 10 * old, f"expected a large correction, got {old} -> {new}"

    def test_json_is_no_longer_counted_as_a_single_word(self):
        old = _words_times_1_3(JSON_PAYLOAD)
        new = estimate_fast(JSON_PAYLOAD)

        assert new > 10 * old, f"punctuation-dense payload still under-counted: {old} -> {new}"

    def test_code_is_no_longer_under_counted(self):
        """Identifiers are one 'word' and several tokens."""
        old = _words_times_1_3(CODE)
        new = estimate_fast(CODE)

        assert new > 2 * old, f"code still under-counted: {old} -> {new}"

    def test_english_prose_is_substantially_unchanged(self):
        """The old heuristic was genuinely fine here — the fix must not
        overcorrect on the case it handled well."""
        old = _words_times_1_3(PROSE)
        new = estimate_fast(PROSE)

        assert 0.5 * old <= new <= 2 * old, f"prose drifted: {old} -> {new}"


class TestProviderCountsWin:
    """AC: where the provider returns authoritative usage, prefer it."""

    def test_total_tokens_is_used_when_present(self):
        assert exact_from_usage({"total_tokens": 1234}) == 1234

    def test_prompt_and_completion_are_summed_when_total_is_absent(self):
        assert exact_from_usage({"prompt_tokens": 100, "completion_tokens": 50}) == 150

    def test_absent_usage_is_none_not_zero(self):
        """None means 'no authoritative count', which is different from 'zero
        tokens' — conflating them would silently pin a session at 0% fill."""
        assert exact_from_usage(None) is None
        assert exact_from_usage({}) is None
        assert exact_from_usage({"prompt_tokens": 0, "completion_tokens": 0}) is None

    def test_resolve_prefers_the_provider_over_the_estimate(self):
        text = "x" * 4000  # would estimate ~1000

        assert resolve_tokens(text, {"total_tokens": 7}) == 7

    def test_resolve_falls_back_knowingly_when_no_usage(self):
        text = "x" * 4000

        assert resolve_tokens(text, None) == estimate_fast(text)


class TestNoFourthEstimator:
    """AC: one shared helper; no second estimation concept introduced."""

    def test_the_fast_path_delegates_to_the_canonical_estimator(self):
        from autobot_shared.doc_chunking import estimate_tokens

        for text in (PROSE, CODE, JSON_PAYLOAD, CJK):
            assert estimate_fast(text) == estimate_tokens(text)

    def test_the_compression_gate_uses_the_shared_helper(self):
        """`compression._estimate_tokens` gated whether compression runs at all."""
        from services.memory.compression import _estimate_tokens

        for text in (CODE, JSON_PAYLOAD, CJK):
            assert _estimate_tokens(text) == estimate_fast(text)

    def test_empty_text_is_zero_not_an_error(self):
        assert estimate_fast("") == 0


class TestTheGateActuallyMoves:
    """The point of the fix: the corrected count changes the decision."""

    @pytest.mark.parametrize("payload", [JSON_PAYLOAD, CJK])
    def test_a_payload_that_never_tripped_the_threshold_now_can(self, payload):
        # Scaled to a realistic conversation's worth of one payload type.
        big = payload * 600
        threshold = 8192  # services/memory/compression._DEFAULT_COMPRESSION_THRESHOLD

        assert _words_times_1_3(big) < threshold, "precondition: old estimate stayed under"
        assert estimate_fast(big) > threshold, "corrected estimate must now trip it"
