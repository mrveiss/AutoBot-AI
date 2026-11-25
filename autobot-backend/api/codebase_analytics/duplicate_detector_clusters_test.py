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

import asyncio
import textwrap
from pathlib import Path

from api.codebase_analytics import duplicate_detector as det
from api.codebase_analytics.duplicate_blocks import (
    MIN_DUPLICATE_CHARS,
    make_block,
    normalize_exact,
    normalize_structural,
)
from api.codebase_analytics.duplicate_clusters import (
    KIND_EXACT,
    KIND_SIMILAR,
    KIND_STRUCTURAL,
    DuplicateCluster,
    DuplicateLocation,
    count_distinct_locations,
)
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
    assert len(normalize_structural(method)) < MIN_DUPLICATE_CHARS
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


def test_the_report_says_when_the_analysis_cap_cut_clusters_and_not_when_it_did_not(tmp_path):
    import dataclasses

    from api.codebase_analytics.endpoints import report

    _plant(tmp_path, {f"d{n}/m.py": _helper() for n in range(3)})
    whole = _scan(tmp_path)
    cut = dataclasses.replace(whole, total_duplicates=4)  # four found, one returned
    assert cut.truncated and not whole.truncated
    text = "\n".join(report._generate_duplicate_code_section(cut))
    assert "Total Duplicate Clusters | 4" in text and "Only 1 of 4 clusters were returned." in text
    assert "clusters were returned" not in "\n".join(report._generate_duplicate_code_section(whole))


def test_a_cached_analysis_round_trips_through_to_dict(tmp_path):
    """The cache read was ``DuplicateAnalysis(**cached)``: the derived ``truncated`` key raised TypeError."""
    _plant(tmp_path, {f"d{n}/m.py": _helper() for n in range(3)})
    analysis = _scan(tmp_path)
    restored = det.DuplicateAnalysis.from_dict(analysis.to_dict())
    assert restored.to_dict() == analysis.to_dict()
    assert restored.duplicates[0].locations == analysis.duplicates[0].locations


def _reordered(reverse: bool) -> str:
    """The same forty statements in either order: equal token sets, different text."""
    body = [f"    v{k} = {k} + base" for k in range(40)]
    return "def total(base):\n" + "\n".join(reversed(body) if reverse else body) + "\n    return v0\n"


def test_a_non_exact_match_is_never_one_hundred_percent_even_with_equal_token_sets(tmp_path):
    _plant(tmp_path, {"a/m.py": _reordered(False), "b/m.py": _reordered(True)})
    analysis = _scan(tmp_path)
    (row,) = analysis.duplicates
    assert normalize_exact(_reordered(False)) != normalize_exact(_reordered(True))
    assert row.kind == KIND_SIMILAR and row.similarity < 1.0
    assert analysis.to_dict()["duplicates"][0]["similarity"] < 100


def test_overlapping_sliding_windows_of_one_file_pair_merge_into_one_range(tmp_path):
    lines = "".join(f"value_{k} = {k} * seed_{k}\n" for k in range(20))  # no def: sliding windows of 10, step 5
    _plant(tmp_path, {"a/m.py": lines, "b/m.py": lines})
    exact = [d for d in _scan(tmp_path).duplicates if d.kind == KIND_EXACT]
    assert len(exact) == 1, "overlapping windows stayed separate rows"
    assert [(loc.start_line, loc.end_line) for loc in exact[0].locations] == [(1, 20), (1, 20)]
    assert exact[0].line_count == 20


def test_an_old_pair_shaped_cache_entry_is_a_miss_not_a_crash():
    old = {
        "total_duplicates": 1,
        "high_similarity_count": 1,
        "medium_similarity_count": 0,
        "low_similarity_count": 0,
        "total_duplicate_lines": 5,
        "duplicates": [{"file1": "a.py", "file2": "b.py", "similarity": 100.0, "lines": 5}],
    }
    assert det.DuplicateAnalysis.from_cache(old) is None
    assert det.DuplicateAnalysis.from_cache(None) is None


def test_the_cache_key_carries_the_schema_version_and_an_old_entry_cannot_crash_the_scan(tmp_path):
    asked: list[str] = []

    class _Cached(det.DuplicateCodeDetector):
        async def _get_cached_result(self, key, prefix=""):
            asked.append(key)
            return {"duplicates": [{"file1": "a.py"}]}

        async def _cache_result(self, *args, **kwargs):
            return None

        async def _find_semantic_duplicates_async(self, all_blocks, seen_pairs):
            return []

    scanner = _Cached(project_root=str(tmp_path))
    scanner.use_semantic_analysis = True
    analysis = asyncio.run(scanner.run_analysis_async())
    assert asked and f":v{det.DUPLICATE_CACHE_SCHEMA_VERSION}:" in asked[0]
    assert analysis.total_duplicates == 0


def test_python_floor_division_is_code_and_a_js_comment_is_not():
    assert normalize_exact("y = a // b") != normalize_exact("y = a // c")
    assert normalize_exact("x = 1 // c\ny = 2", js_family=True) == "x = 1 y = 2"


def test_a_python_block_of_floor_divisions_keeps_its_operands_and_qualifies():
    body = "\n".join(f"    q{k} = a // denominator_value_{k}" for k in range(3))
    method = f"def r(a):\n{body}"
    assert "// denominator_value_2" in normalize_structural(method)
    assert make_block("x.py", 1, 4, method, 4) is not None  # the old ``//.*$`` strip left it under the size gate
    assert "denominator" not in normalize_structural(method, js_family=True)  # in JS the same text is a comment


def test_whitespace_inside_a_string_literal_is_part_of_its_value():
    assert normalize_exact('k = "first  name"') != normalize_exact('k = "first name"')
    assert normalize_exact("k = `a  b`", js_family=True) != normalize_exact("k = `a b`", js_family=True)
    assert normalize_exact('k  =  "a"   # note') == normalize_exact('k = "a"')  # outside a literal it is not


def test_a_four_line_js_function_is_a_block():
    code = "function sumAllTheValues(values, offset) {\n  const total = values.reduce((a, b) => a + b, offset);\n"
    code += "  return total * multiplierForTheseValues;\n}"
    lines = code.splitlines()
    assert len(lines) == det.MIN_DUPLICATE_LINES == 4
    (block,) = det._extract_js_blocks("x.js", lines)
    assert (block.start_line, block.end_line, block.line_count) == (1, 4, 4)
    assert det._extract_js_blocks("x.js", lines[:2] + lines[3:]) == []  # three lines are below the minimum


def test_a_string_holding_a_block_comment_marker_does_not_swallow_code():
    code = 'a = "/*"; b(); c = "*/"'
    assert normalize_exact(code, js_family=True) == code
    assert "b()" in normalize_exact('d = """/* x\n"""\ny = b()')


def test_a_block_listed_by_an_exact_and_a_structural_cluster_counts_once(tmp_path):
    _plant(tmp_path, {"a/m.py": _helper("left"), "b/m.py": _helper("left"), "c/m.py": _helper("right")})
    analysis = _scan(tmp_path)
    exact = next(d for d in analysis.duplicates if d.kind == KIND_EXACT)
    assert analysis.exact_cluster_count == 1 and analysis.structural_cluster_count == 1
    assert analysis.total_locations == 3, "the exact pair was counted again inside the structural cluster"
    assert analysis.total_duplicate_lines == exact.line_count * 2


def _js_function(name: str) -> str:
    consts = "\n".join(f"  const step{k} = values[{k}] + offset * {k};" for k in range(4))
    return f"function {name}(values, offset) {{\n{consts}\n  return step0;\n}}\n"


def test_exact_rows_merge_only_when_contiguous_never_across_a_gap(tmp_path):
    contiguous = _js_function("collectOne") + _js_function("collectTwo")
    gapped = _js_function("collectOne") + "\n" + _js_function("collectTwo")
    _plant(tmp_path / "touching", {"a/m.js": contiguous, "b/m.js": contiguous})
    _plant(tmp_path / "gapped", {"a/m.js": gapped, "b/m.js": gapped})
    touching = [d for d in _scan(tmp_path / "touching").duplicates if d.kind == KIND_EXACT]
    apart = [d for d in _scan(tmp_path / "gapped").duplicates if d.kind == KIND_EXACT]
    assert len(touching) == 1 and touching[0].similarity == 1.0, "contiguous exact blocks must merge at 100%"
    assert len(apart) == 2, "an unchecked line between two exact blocks was merged into one 100% row"


def test_the_js_family_is_the_scanners_extension_sets_so_mjs_comments_are_comments():
    code = "const total = values.reduce((sum, v) => sum + v, 0)\nconst scaled = total * factor + offset - baseline\n"
    noted = code.replace("0)\n", "0) // trailing note\n", 1)
    assert make_block("a.mjs", 1, 2, noted, 2).exact_hash == make_block("a.mjs", 1, 2, code, 2).exact_hash
    assert make_block("a.py", 1, 2, noted, 2).exact_hash != make_block("a.py", 1, 2, code, 2).exact_hash


def test_a_nested_template_literal_is_one_string_and_code_after_it_is_kept():
    code = "const a = `x ${`in  ner ${1}`} y`; // gone\nreturn a  +  b"
    assert normalize_exact(code, js_family=True) == "const a = `x ${`in  ner ${1}`} y`; return a + b"
    # contrast: a plain template keeps its inner spacing and a real comment is still stripped
    assert normalize_exact("`a  b` /* c */ x", js_family=True) == "`a  b` x"


def test_a_regex_literal_is_code_not_a_line_comment():
    code = "const r = /\\/\\//g; const s = 1  +  2"
    assert normalize_exact(code, js_family=True) == "const r = /\\/\\//g; const s = 1 + 2"
    assert normalize_exact("x = a / b // real\ny", js_family=True) == "x = a / b y"  # division, then a comment
    assert normalize_exact("x = [/a  b/]; // c", js_family=True) == "x = [/a  b/];"  # spaces inside a regex are kept
    assert normalize_exact("return /[/]/.test(s) // c", js_family=True) == "return /[/]/.test(s)"


def test_two_exact_subgroups_bridged_by_a_structural_cluster_count_one_original():
    def loc(f):
        return DuplicateLocation(f, 1, 10)

    def cluster(kind, *files):
        return DuplicateCluster(kind, 1.0, 10, [loc(f) for f in files], "")

    exact_a, exact_b = cluster(KIND_EXACT, "a", "b"), cluster(KIND_EXACT, "c", "d")
    structural = cluster(KIND_STRUCTURAL, "a", "b", "c", "d")
    # four blocks that all match structurally hold three redundant copies of 10 lines
    assert count_distinct_locations([exact_a, exact_b, structural]) == (4, 30)
    # contrast: without the structural bridge the two pairs are separate (one redundant copy each)
    assert count_distinct_locations([exact_a, exact_b]) == (4, 20)
    assert count_distinct_locations([structural]) == (4, 30)
