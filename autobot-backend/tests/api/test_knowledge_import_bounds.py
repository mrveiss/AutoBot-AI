# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LearnedKnowledgeImport numeric bounds (GH#11179).

The import scoring fields must be range-bounded (symmetric with the export
endpoint's min_confidence ge/le) so an admin import can't inject out-of-range
values into the planner's strategy selection.
"""

import pytest
from pydantic import ValidationError

from api.schemas_agent import LearnedKnowledgeImport


def _payload(**overrides):
    base = dict(task_type="research", best_approach="a", best_prompt_template="t")
    base.update(overrides)
    return base


def test_confidence_above_one_rejected() -> None:
    with pytest.raises(ValidationError):
        LearnedKnowledgeImport(**_payload(confidence=1.5))


def test_confidence_below_zero_rejected() -> None:
    with pytest.raises(ValidationError):
        LearnedKnowledgeImport(**_payload(confidence=-0.1))


def test_avg_score_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        LearnedKnowledgeImport(**_payload(avg_score=42.0))


def test_negative_sample_size_rejected() -> None:
    with pytest.raises(ValidationError):
        LearnedKnowledgeImport(**_payload(sample_size=-1))


def test_values_within_bounds_accepted() -> None:
    model = LearnedKnowledgeImport(**_payload(confidence=0.9, avg_score=0.5, sample_size=3))
    assert model.confidence == 0.9
    assert model.avg_score == 0.5
    assert model.sample_size == 3
