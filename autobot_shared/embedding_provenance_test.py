# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#6514: regression tests for embedding-provenance defensive validation.

Pins the contract that prevents the silent cross-model contamination
described in the original issue body — two paths writing to the same
ChromaDB collection with different (model_name, dim) pairs.
"""

import pytest

from autobot_shared.embedding_provenance import (
    PROVENANCE_METADATA_PREFIX,
    EmbeddingMismatchError,
    EmbeddingProvenance,
    provenance_from_metadata,
    provenance_to_metadata,
    validate_vectors_against_provenance,
)

# ---------------------------------------------------------------------------
# EmbeddingProvenance dataclass — input validation
# ---------------------------------------------------------------------------


class TestEmbeddingProvenance:
    def test_valid_construction(self) -> None:
        p = EmbeddingProvenance(model_name="microsoft/codebert-base", dim=768)
        assert p.model_name == "microsoft/codebert-base"
        assert p.dim == 768

    def test_frozen(self) -> None:
        p = EmbeddingProvenance("nomic-embed-text", 768)
        with pytest.raises((AttributeError, TypeError)):
            p.dim = 384  # type: ignore[misc]  # frozen=True prohibits

    def test_empty_model_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-empty string"):
            EmbeddingProvenance(model_name="", dim=768)

    def test_non_string_model_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-empty string"):
            EmbeddingProvenance(model_name=None, dim=768)  # type: ignore[arg-type]

    def test_zero_dim_rejected(self) -> None:
        with pytest.raises(ValueError, match="positive int"):
            EmbeddingProvenance(model_name="x", dim=0)

    def test_negative_dim_rejected(self) -> None:
        with pytest.raises(ValueError, match="positive int"):
            EmbeddingProvenance(model_name="x", dim=-1)

    def test_non_int_dim_rejected(self) -> None:
        with pytest.raises(ValueError, match="positive int"):
            EmbeddingProvenance(model_name="x", dim="768")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Round-trip: provenance ↔ metadata
# ---------------------------------------------------------------------------


class TestProvenanceMetadataRoundTrip:
    def test_to_metadata_returns_chroma_compatible_dict(self) -> None:
        p = EmbeddingProvenance("microsoft/codebert-base", 768)
        m = provenance_to_metadata(p)
        # Chroma only accepts str / int / float — no nesting, no lists.
        for key, value in m.items():
            assert isinstance(key, str)
            assert isinstance(value, (str, int, float))

    def test_metadata_keys_use_namespace_prefix(self) -> None:
        """Avoid collision with reserved Chroma keys like ``hnsw:space``."""
        p = EmbeddingProvenance("nomic-embed-text", 384)
        m = provenance_to_metadata(p)
        for key in m:
            assert key.startswith(PROVENANCE_METADATA_PREFIX)

    def test_round_trip(self) -> None:
        p = EmbeddingProvenance("microsoft/codebert-base", 768)
        recovered = provenance_from_metadata(provenance_to_metadata(p))
        assert recovered == p

    def test_from_metadata_returns_none_for_legacy_untagged_collection(self) -> None:
        # Existing Chroma collections have only `hnsw:space` etc. — they
        # predate the tagging system. provenance_from_metadata must return
        # None instead of raising so legacy callers still work.
        legacy_metadata = {"hnsw:space": "cosine", "description": "old collection"}
        assert provenance_from_metadata(legacy_metadata) is None

    def test_from_metadata_returns_none_when_metadata_is_none(self) -> None:
        assert provenance_from_metadata(None) is None

    def test_from_metadata_returns_none_when_metadata_is_empty(self) -> None:
        assert provenance_from_metadata({}) is None

    def test_from_metadata_returns_none_on_partial_tags(self) -> None:
        # Half-tagged: only model_name, no dim — defensive null return,
        # not a malformed-data exception.
        partial = {f"{PROVENANCE_METADATA_PREFIX}.model_name": "x"}
        assert provenance_from_metadata(partial) is None

    def test_from_metadata_returns_none_on_corrupt_dim(self) -> None:
        m = {
            f"{PROVENANCE_METADATA_PREFIX}.model_name": "x",
            f"{PROVENANCE_METADATA_PREFIX}.dim": "not-a-number",
        }
        assert provenance_from_metadata(m) is None

    def test_from_metadata_handles_float_dim_string(self) -> None:
        # Chroma may stringify ints in some serialization paths — accept
        # ``int(value)`` parses.
        m = {
            f"{PROVENANCE_METADATA_PREFIX}.model_name": "x",
            f"{PROVENANCE_METADATA_PREFIX}.dim": "768",
        }
        recovered = provenance_from_metadata(m)
        assert recovered is not None
        assert recovered.dim == 768


# ---------------------------------------------------------------------------
# validate_vectors_against_provenance — runtime guard
# ---------------------------------------------------------------------------


class TestValidateVectorsAgainstProvenance:
    def test_matching_dim_passes_silently(self) -> None:
        p = EmbeddingProvenance("codebert", 768)
        vectors = [[0.1] * 768, [0.2] * 768]
        # Must not raise.
        validate_vectors_against_provenance(vectors, p)

    def test_mismatched_dim_raises_embedding_mismatch_error(self) -> None:
        p = EmbeddingProvenance("codebert", 768)
        # nomic-embed-text and codebert in the same collection: classic
        # #6514 contamination shape.
        vectors = [[0.1] * 384]
        with pytest.raises(EmbeddingMismatchError, match="dim 384.*expects dim 768"):
            validate_vectors_against_provenance(vectors, p)

    def test_first_mismatch_in_batch_is_raised(self) -> None:
        # Batch write where only one vector is wrong — fail-fast on
        # the first mismatch with the offending index in the message.
        p = EmbeddingProvenance("codebert", 768)
        vectors = [[0.0] * 768, [0.0] * 768, [0.0] * 384, [0.0] * 768]
        with pytest.raises(EmbeddingMismatchError, match="vector at index 2"):
            validate_vectors_against_provenance(vectors, p)

    def test_empty_input_is_noop(self) -> None:
        p = EmbeddingProvenance("codebert", 768)
        validate_vectors_against_provenance([], p)
        # No exception.

    def test_non_sized_vector_raises(self) -> None:
        # Caller passed an int instead of a vector — surfaces as a
        # mismatch error, not an opaque TypeError downstream.
        p = EmbeddingProvenance("codebert", 768)
        with pytest.raises(EmbeddingMismatchError, match="not a sequence"):
            validate_vectors_against_provenance([42], p)  # type: ignore[list-item]

    def test_embedding_mismatch_error_is_value_error_subclass(self) -> None:
        # Subclass of ValueError so existing `except ValueError:` blocks
        # still catch it — preserves error-handling contracts in callers
        # that don't yet know about the new specific type.
        assert issubclass(EmbeddingMismatchError, ValueError)


# ---------------------------------------------------------------------------
# Reproducer: the original #6514 silent-contamination shape
# ---------------------------------------------------------------------------


class TestIssue6514Reproducer:
    """Pin the original failure mode: two paths writing to the same
    collection with incompatible models. Once tagged, the second
    writer's batch must raise rather than silently corrupting recall."""

    def test_codebert_collection_rejects_nomic_writes(self) -> None:
        # 1. Path A creates a collection tagged for codebert (768-dim).
        codebert = EmbeddingProvenance("microsoft/codebert-base", 768)
        codebert_metadata = provenance_to_metadata(codebert)

        # 2. Path B tries to write nomic vectors (e.g. 384-dim) into
        # the same collection. Production guard reads provenance and
        # validates. Without the fix, this would silently corrupt.
        recovered = provenance_from_metadata(codebert_metadata)
        assert recovered == codebert

        nomic_vectors = [[0.5] * 384]
        with pytest.raises(EmbeddingMismatchError):
            validate_vectors_against_provenance(nomic_vectors, recovered)

    def test_codebert_collection_accepts_codebert_writes(self) -> None:
        codebert = EmbeddingProvenance("microsoft/codebert-base", 768)
        recovered = provenance_from_metadata(provenance_to_metadata(codebert))
        assert recovered is not None
        codebert_vectors = [[0.5] * 768]
        # Same model + dim → passes silently.
        validate_vectors_against_provenance(codebert_vectors, recovered)
