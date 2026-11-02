# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20224: the analytics responses say their results cover the whole index, not `analysis_root`."""

from api.code_search import _build_declarations_summary
from api.code_search_duplicates import build_duplicates_response


def test_the_declarations_summary_says_the_results_cover_the_whole_index() -> None:
    summary = _build_declarations_summary({}, "/project")["summary"]
    assert summary["analysis_root"] == "/project"
    assert summary["results_scope"] == "whole_index"


def test_the_duplicates_summary_says_the_results_cover_the_whole_index() -> None:
    summary = build_duplicates_response(0, [], "/project")["summary"]
    assert summary["analysis_root"] == "/project"
    assert summary["results_scope"] == "whole_index"
