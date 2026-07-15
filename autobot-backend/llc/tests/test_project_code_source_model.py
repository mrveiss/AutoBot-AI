# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
from llc.models.sprint import LLCProject


def test_llcproject_has_code_source_id_column():
    assert "code_source_id" in LLCProject.__table__.columns
    col = LLCProject.__table__.columns["code_source_id"]
    assert col.nullable is True
