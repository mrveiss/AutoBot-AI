# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Known-answer fixture for the duplicate detector (#17982, #18067).

A detector whose recall is unmeasured cannot be trusted to say "no duplicates".
This plants ONE duplicate pair that must be found and ONE near-miss that must
not, so a zero from the detector is a claim and not a silence. It also pins the
three properties that decided whether a scan could finish on AutoBot's own tree.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

pytest.importorskip("datasketch")

from api.codebase_analytics import duplicate_detector as det  # noqa: E402
from api.codebase_analytics import duplicate_lsh  # noqa: E402

_LIMITER = """
def acquire_slot(bucket, now, limit, window):
    expired = [stamp for stamp in bucket if now - stamp > window]
    for stamp in expired:
        bucket.remove(stamp)
    if len(bucket) >= limit:
        oldest = min(bucket)
        retry_after = window - (now - oldest)
        return False, retry_after
    bucket.append(now)
    remaining = limit - len(bucket)
    return True, remaining
"""

#: The planted duplicate: the same algorithm with two locals and the name changed.
_FORK = _LIMITER.replace("expired", "stale").replace("oldest", "first").replace("acquire_slot", "take_token")

#: The near-miss: long enough to be compared, shares the shape of a loop and an
#: early return, but is a different computation.
_NEAR_MISS = """
def summarise_invoice(lines, currency, rounding, tax_table):
    subtotal = sum(line.price * line.quantity for line in lines)
    tax = round(subtotal * tax_table.get(currency, 0.0), rounding)
    if subtotal <= 0:
        return None
    discount = 0.1 if subtotal > 1000 else 0.0
    total = round(subtotal + tax - subtotal * discount, rounding)
    return {"currency": currency, "total": total, "tax": tax}
"""

_SHORT = """
def tiny_helper(value):
    cleaned = value.strip()
    collapsed = " ".join(cleaned.split())
    return collapsed.lower()
"""
_SHORT_RENAMED = _SHORT.replace("tiny_helper", "small_helper")  # Jaccard 0.8 on 9 tokens


def _plant(root: Path, files: dict[str, str]) -> None:
    for name, body in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")


def _scan(root: Path, min_similarity: float = 0.5):
    return det.DuplicateCodeDetector(project_root=str(root), min_similarity=min_similarity).run_analysis()


def _pairs(analysis) -> set[frozenset[str]]:
    return {frozenset({Path(d.file1).name, Path(d.file2).name}) for d in analysis.duplicates}


def test_the_planted_pair_is_found_and_the_near_miss_is_not(tmp_path):
    _plant(tmp_path, {"a/limiter.py": _LIMITER, "b/throttle.py": _FORK, "c/billing.py": _NEAR_MISS})
    analysis = _scan(tmp_path, min_similarity=0.6)
    assert frozenset({"limiter.py", "throttle.py"}) in _pairs(analysis), "recall: the planted fork was missed"
    assert not any("billing.py" in pair for pair in _pairs(analysis)), "precision: the near-miss was reported"
    assert analysis.files_analyzed == 3, "the examined count is part of the answer"


def test_an_exact_copy_is_found_at_any_size_but_a_tiny_near_copy_is_not_fuzzy_matched(tmp_path):
    """The stated boundary of the fuzzy pass: under MIN_TOKENS_FOR_SIMILARITY
    distinct tokens only EXACT matches count, because token-set Jaccard on sets
    that small reaches the threshold by coincidence."""
    _plant(tmp_path, {"a/one.py": _SHORT, "b/two.py": _SHORT, "c/three.py": _SHORT_RENAMED})
    pairs = _pairs(_scan(tmp_path))
    assert frozenset({"one.py", "two.py"}) in pairs, "an exact tiny copy must still be found"
    assert not any("three.py" in p for p in pairs), "a tiny near-copy was fuzzy-matched"
    tiny = {len(set(det._normalize_code(_SHORT).split()))}
    assert max(tiny) < duplicate_lsh.MIN_TOKENS_FOR_SIMILARITY, "fixture no longer exercises the floor"


def test_the_result_is_capped_but_the_count_is_not(tmp_path, monkeypatch):
    """2.5 million returned pairs was the failure; the cap must not hide the size."""
    _plant(tmp_path, {f"d{i}/limiter.py": _LIMITER for i in range(4)})  # 6 exact pairs
    monkeypatch.setattr(det, "MAX_DUPLICATES_RETURNED", 2)
    analysis = _scan(tmp_path)
    assert analysis.total_duplicates == 6 and len(analysis.duplicates) == 2 and analysis.truncated
    assert analysis.high_similarity_count == 6, "statistics must describe every pair, not the returned slice"


def test_the_lsh_threshold_follows_min_similarity(monkeypatch, tmp_path):
    """Every timeout message says 'try a higher min_similarity'. LSH was built at a
    hardcoded 0.5, so doing so changed the answer and not the work.

    More than 10 eligible blocks are needed to leave the O(n^2) fallback.
    """
    seen: list[float] = []
    real = duplicate_lsh.build_index

    def _spy(minhashes, threshold, num_perm):
        seen.append(threshold)
        return real(minhashes, threshold, num_perm)

    monkeypatch.setattr(duplicate_lsh, "build_index", _spy)
    files = {f"m{n}/billing.py": _unrelated(n) for n in range(12)}
    files.update({"a/limiter.py": _LIMITER, "b/throttle.py": _FORK})
    _plant(tmp_path, files)
    analysis = _scan(tmp_path, min_similarity=0.6)
    assert seen == [0.5], "the index is built LSH_RECALL_MARGIN below the requested similarity"
    seen.clear()
    _scan(tmp_path, min_similarity=0.9)
    assert seen == [0.8], "a higher min_similarity must build a stricter (cheaper) index"
    assert frozenset({"limiter.py", "throttle.py"}) in _pairs(analysis), "the LSH path lost the planted fork"
    assert not any("billing.py" in pair for pair in _pairs(analysis)), "the LSH path reported unrelated functions"


def _unrelated(n: int) -> str:
    """A long function sharing no vocabulary with its siblings beyond Python keywords."""
    words = [f"w{n}_{k}" for k in range(8)]
    body = "\n".join(f"    {w} = {n * 7 + k} * {w}_seed + {k}" for k, w in enumerate(words))
    return f"def compute_{n}({words[0]}_seed, {words[1]}_extra):\n{body}\n    return {words[0]} + {words[7]}\n"
