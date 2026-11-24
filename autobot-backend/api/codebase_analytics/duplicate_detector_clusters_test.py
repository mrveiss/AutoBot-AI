# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What the duplicate detector may call a duplicate, and how it counts them (#22157).

Each test pairs a case that must be reported with the look-alike that must not:
the 50-line prompt methods that normalize to nine tokens against two identical
helpers, a match that needed string erasure against one that did not, a cluster
against the pairs it used to be counted as.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from api.codebase_analytics import duplicate_detector as det
from api.codebase_analytics.duplicate_blocks import make_block, normalize_exact, normalize_structural
from api.codebase_analytics.duplicate_clusters import KIND_EXACT, KIND_STRUCTURAL
from utils.file_categorization import SKIP_DIRS


def _prompt_method(text: str) -> str:
    # every word is unique to this text, so no two prompts share a token either
    body = "\n".join(f"{text}{n}x{n}{text} {text}y{n}" for n in range(48))
    return f'def _get_system_prompt(self) -> str:\n    return """\n{body}\n"""\n'


def _helper(tag: str = "a") -> str:
    lines = "\n".join(f"    step_{k} = values.get('{tag}_{k}', {k}) + offset * {k}" for k in range(28))
    return f"def collect_totals(values, offset):\n{lines}\n    return step_0 + step_27\n"


def _plant(root: Path, files: dict[str, str]) -> None:
    for name, body in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(textwrap.dedent(body), encoding="utf-8")


def _scan(root: Path):
    return det.DuplicateCodeDetector(project_root=str(root)).run_analysis()


def test_a_block_qualifies_on_its_normalized_size():
    """AC1: fifty lines of prompt text normalize to a handful of tokens and are no block at all."""
    method = _prompt_method("alpha")
    assert len(method.splitlines()) >= 50
    assert len(normalize_structural(method)) < det.MIN_DUPLICATE_CHARS
    assert make_block("x.py", 1, 51, method, 51) is None
    assert make_block("x.py", 1, 31, _helper(), 31) is not None


def test_prompt_methods_with_different_text_are_not_duplicates_but_identical_helpers_are(tmp_path):
    _plant(tmp_path, {"judges/a.py": _prompt_method("alpha"), "judges/b.py": _prompt_method("beta")})
    _plant(tmp_path, {"util/a.py": _helper(), "util/b.py": _helper()})
    analysis = _scan(tmp_path)
    files = {Path(loc.file).parent.name for d in analysis.duplicates for loc in d.locations}
    assert files == {"util"}, "the prompt methods were reported as duplicates of each other"
    assert analysis.total_duplicates == 1 and analysis.exact_cluster_count == 1


def test_a_match_that_needs_string_erasure_is_structural_never_one_hundred_percent(tmp_path):
    _plant(tmp_path, {"a/m.py": _helper("left"), "b/m.py": _helper("right")})
    analysis = _scan(tmp_path)
    assert normalize_exact(_helper("left")) != normalize_exact(_helper("right"))
    assert analysis.exact_cluster_count == 0 and analysis.structural_cluster_count == 1
    (row,) = analysis.duplicates
    assert row.kind == KIND_STRUCTURAL and row.similarity < 1.0
    assert analysis.to_dict()["duplicates"][0]["similarity"] < 100


def test_exact_means_equal_after_comment_and_whitespace_normalization_only(tmp_path):
    noisy = _helper().replace("offset):", "offset):  # a comment").replace("    step_1", "\n\n        step_1")
    _plant(tmp_path, {"a/m.py": _helper(), "b/m.py": noisy})
    analysis = _scan(tmp_path)
    assert normalize_exact(_helper()) == normalize_exact(noisy)
    assert analysis.exact_cluster_count == 1 and analysis.structural_cluster_count == 0


def test_a_comment_marker_inside_a_string_is_not_a_comment():
    assert normalize_exact("x = 'http://one'") != normalize_exact("x = 'http://two'")


def test_k_identical_blocks_are_one_cluster_listing_every_location(tmp_path):
    _plant(tmp_path, {f"d{n}/m.py": _helper() for n in range(5)})
    analysis = _scan(tmp_path)
    assert analysis.total_duplicates == 1, "five copies were counted as ten pairs"
    assert analysis.total_locations == 5
    assert len(analysis.duplicates[0].locations) == 5 and analysis.duplicates[0].kind == KIND_EXACT
    assert analysis.total_duplicate_lines == analysis.duplicates[0].line_count * 4


def test_adjacent_matching_blocks_of_one_file_pair_merge_into_one_range(tmp_path):
    both = _helper() + "\n" + _helper("other").replace("collect_totals", "collect_more")
    _plant(tmp_path, {"a/m.py": both, "b/m.py": both})
    analysis = _scan(tmp_path)
    exact = [d for d in analysis.duplicates if d.kind == KIND_EXACT]
    assert len(exact) == 1, "one range per file pair, not one row per matching block"
    assert all(loc.end_line - loc.start_line > 40 for loc in exact[0].locations)


def test_vendored_trees_are_excluded_and_the_exclusion_is_in_the_output(tmp_path):
    _plant(tmp_path, {"tests/external/x/a.py": _helper(), "tests/external/x/b.py": _helper()})
    analysis = _scan(tmp_path)
    assert "external" in SKIP_DIRS and analysis.total_duplicates == 0
    assert "external" in analysis.to_dict()["excluded_dirs"]
    assert analysis.files_analyzed == 0


def test_the_report_lists_every_location_of_a_cluster(tmp_path):
    from api.codebase_analytics.endpoints import report

    _plant(tmp_path, {f"d{n}/m.py": _helper() for n in range(3)})
    text = "\n".join(report._generate_duplicate_code_section(_scan(tmp_path)))
    assert "Total Duplicate Clusters | 1 (3 locations)" in text
    assert all(f"d{n}/m.py" in text for n in range(3)), "the report named only the first two copies"


def test_a_cached_analysis_round_trips_through_to_dict(tmp_path):
    """The cache read was ``DuplicateAnalysis(**cached)``: the derived ``truncated`` key raised TypeError."""
    _plant(tmp_path, {f"d{n}/m.py": _helper() for n in range(3)})
    analysis = _scan(tmp_path)
    restored = det.DuplicateAnalysis.from_dict(analysis.to_dict())
    assert restored.to_dict() == analysis.to_dict()
    assert restored.duplicates[0].locations == analysis.duplicates[0].locations
