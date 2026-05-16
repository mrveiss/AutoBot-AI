# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for EvidenceExtractor abbreviation-aware splitting (#2202).

Extends the existing TestSplitSentences coverage to verify that common
abbreviations (Mr., Ms., Mrs., St., vs., i.e.) do not cause false splits.
"""

from unittest.mock import AsyncMock

from services.neural_mesh.evidence_extractor import EvidenceExtractor


def _make_extractor() -> EvidenceExtractor:
    """Construct an EvidenceExtractor with a dummy reranker."""
    return EvidenceExtractor(reranker=AsyncMock(), max_evidence=15)


class TestAbbreviationAwareSplitting:
    """_split_sentences() must not break on common abbreviations (#2202)."""

    def test_mr_not_split(self) -> None:
        """'Mr. Jones arrived early.' stays as one sentence."""
        ext = _make_extractor()
        parts = ext._split_sentences("Mr. Jones arrived early.")
        assert parts == ["Mr. Jones arrived early."]

    def test_ms_not_split(self) -> None:
        """'Ms. Chen presented the report.' stays as one sentence."""
        ext = _make_extractor()
        parts = ext._split_sentences("Ms. Chen presented the report.")
        assert parts == ["Ms. Chen presented the report."]

    def test_mrs_not_split(self) -> None:
        """'Mrs. Smith left early.' stays as one sentence."""
        ext = _make_extractor()
        parts = ext._split_sentences("Mrs. Smith left early.")
        assert parts == ["Mrs. Smith left early."]

    def test_st_not_split(self) -> None:
        """'St. Louis is in Missouri.' stays as one sentence."""
        ext = _make_extractor()
        parts = ext._split_sentences("St. Louis is in Missouri.")
        assert parts == ["St. Louis is in Missouri."]

    def test_vs_not_split(self) -> None:
        """'The case was Smith vs. Jones in court.' stays as one sentence."""
        ext = _make_extractor()
        parts = ext._split_sentences("The case was Smith vs. Jones in court.")
        assert parts == ["The case was Smith vs. Jones in court."]

    def test_ie_not_split(self) -> None:
        """'The primary language, i.e. Python, is required.' stays as one sentence."""
        ext = _make_extractor()
        parts = ext._split_sentences("The primary language, i.e. Python, is required.")
        assert parts == ["The primary language, i.e. Python, is required."]

    def test_dr_with_real_sentence_break(self) -> None:
        """'Dr. Smith diagnosed the issue. Then left.' splits into two sentences."""
        ext = _make_extractor()
        parts = ext._split_sentences("Dr. Smith diagnosed the issue. Then left.")
        assert len(parts) == 2
        assert parts[0] == "Dr. Smith diagnosed the issue."
        assert parts[1] == "Then left."

    def test_multiple_abbreviations_in_one_sentence(self) -> None:
        """Sentence with Dr. and U.S. stays as one sentence."""
        ext = _make_extractor()
        text = "Dr. Smith works in the U.S. for a research lab."
        parts = ext._split_sentences(text)
        assert parts == ["Dr. Smith works in the U.S. for a research lab."]

    def test_eg_with_following_sentence(self) -> None:
        """'Use a tool, e.g. Redis for caching. It works well.' splits correctly."""
        ext = _make_extractor()
        text = "Use a tool, e.g. Redis for caching. It works well."
        parts = ext._split_sentences(text)
        assert len(parts) == 2
        assert parts[0] == "Use a tool, e.g. Redis for caching."
        assert parts[1] == "It works well."

    def test_mixed_abbreviations_and_real_breaks(self) -> None:
        """Complex text with abbreviations and real sentence boundaries."""
        ext = _make_extractor()
        text = "Mr. Jones met Dr. Smith. They discussed vs. alternatives. It was productive."
        parts = ext._split_sentences(text)
        assert len(parts) == 3
        assert parts[0] == "Mr. Jones met Dr. Smith."
        assert parts[1] == "They discussed vs. alternatives."
        assert parts[2] == "It was productive."

    def test_question_mark_still_splits(self) -> None:
        """Question marks still split sentences even with abbreviations nearby."""
        ext = _make_extractor()
        text = "Did Dr. Smith arrive? Yes he did."
        parts = ext._split_sentences(text)
        assert len(parts) == 2
        assert parts[0] == "Did Dr. Smith arrive?"
        assert parts[1] == "Yes he did."

    def test_exclamation_mark_still_splits(self) -> None:
        """Exclamation marks still split sentences."""
        ext = _make_extractor()
        text = "Mr. Jones won the award! Everyone cheered."
        parts = ext._split_sentences(text)
        assert len(parts) == 2
        assert parts[0] == "Mr. Jones won the award!"
        assert parts[1] == "Everyone cheered."
