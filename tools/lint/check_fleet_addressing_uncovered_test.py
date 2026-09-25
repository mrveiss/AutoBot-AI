# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for tools/lint/check_fleet_addressing_uncovered.py (#17440).

No fleet address is written literally in this file. Each fixture derives one
from the pattern the guard parses out of the shared rule set, so this test
cannot become the next place the range is published -- which is the mistake the
guard exists to prevent, and which a test file is just as public for.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import check_fleet_addressing_uncovered as hook  # noqa: E402


@pytest.fixture(scope="module")
def literal() -> str:
    """An address the real pattern matches, built from the real pattern."""
    pattern = hook.fleet_address_pattern()
    text = pattern.pattern.replace("\\.", ".").replace("[0-9]+", "77").replace("\\d+", "77")
    assert pattern.search(text), "fixture no longer matches the parsed pattern"
    return text


def test_the_extension_list_is_parsed_not_restated() -> None:
    """A second copy of the list would drift the moment either side changed."""
    exts = hook.scanned_extensions()
    assert {"py", "yml"} <= exts, f"HV_SCAN_EXTENSIONS parsed as {sorted(exts)}"
    source = pathlib.Path(hook.__file__).read_text(encoding="utf-8")
    assert (
        "'py|ts|vue|js|sh|yml|yaml'" not in source
    ), "the extension list is hardcoded here as well as parsed -- one definition only"


def test_an_unparseable_rule_source_raises_rather_than_widening(tmp_path, monkeypatch) -> None:
    """An unread list and an empty one must not look the same.

    Defaulting to empty would make `is_covered` return False for everything and
    silently widen this guard's population to the whole tree.
    """
    (tmp_path / "scripts" / "lib").mkdir(parents=True)
    (tmp_path / "scripts" / "lib" / "hardcoded-value-rules.sh").write_text("# nothing\n", encoding="utf-8")
    with pytest.raises(hook.RuleSourceError):
        hook.scanned_extensions(tmp_path)


def test_a_missing_rule_source_raises() -> None:
    with pytest.raises(hook.RuleSourceError):
        hook.scanned_extensions(pathlib.Path("/nonexistent-root-for-17440"))


@pytest.mark.parametrize(
    ("rel", "covered"),
    [
        # scanned extension, inside HV_SCAN_DIRS, not excluded -> the hv hook has it
        ("autobot-backend/api/x.py", True),
        ("autobot-slm-backend/deploy/site.yml", True),
        ("autobot-frontend/src/app.ts", True),
        ("docs/developer/GUIDE.md", True),  # #15208
        # scanned extension but EXCLUDED by _HV_EXCLUDE_RE -> nobody scans it
        ("autobot-backend/tests/test_prompt_manager.py", False),
        ("autobot-backend/api/thing_test.py", False),
        ("repo_tests/anything.py", False),
        # scanned extension but OUTSIDE HV_SCAN_DIRS -> nobody scans it
        ("pipeline-scripts/check_x.py", False),
        ("tools/lint/helper.py", False),
        ("check-grafana-health.sh", False),
        # unscanned extension anywhere
        ("autobot-slm-backend/ansible/README-PLAYBOOKS.md", False),
        ("autobot-infrastructure/shared/config/board.json", False),
        ("etc/autobot.service", False),
    ],
)
def test_coverage_mirrors_the_shared_detector_not_just_its_extension_list(rel: str, covered: bool) -> None:
    """The population is what the OTHER guards do not reach -- all three clauses.

    The first draft checked the extension alone, so a `*_test.py` or anything
    under `pipeline-scripts/` counted as covered while the shared detector
    excluded it. That left a gap where neither audit looked: 4 files, 20
    occurrences (#17447 review). `hv_file_in_scope()` requires the extension AND
    a path `_HV_EXCLUDE_RE` does not match; the tree scan adds `HV_SCAN_DIRS`.
    """
    assert hook.is_covered(rel, hook.scanned_extensions(), hook.scanned_dirs(), hook.exclude_pattern()) is covered


def test_the_exclude_pattern_has_no_empty_alternative() -> None:
    """The bug this caught, pinned so it cannot come back.

    `_HV_EXCLUDE_RE` is built from one `=` and eight `+=` fragments, each of
    which already carries its own leading `|`. Joining them with `"|"` produced
    `(a)||(b)`, whose EMPTY alternative matches at any position -- so every path
    looked excluded, every file looked uncovered, and the population inflated
    from 1085 to 9933. Nothing failed; only the number showed it.
    """
    pattern = hook.exclude_pattern()
    assert "||" not in pattern.pattern
    assert not pattern.search(
        "autobot-backend/api/ordinary_module.py"
    ), "the exclude pattern matches a plain source file -- it has an empty alternative"
    assert pattern.search("repo_tests/x.py"), "the exclude pattern no longer reaches its subjects"


def test_exempt_and_baseline_are_disjoint_and_both_live() -> None:
    """An exemption is not a debt, and a debt is not an exemption.

    `EXEMPT` holds files that MUST carry the pattern -- the definition itself and
    the fixtures of the guards that match it. Recording those as baseline debt
    would make the shrink-only number permanently unreachable, which is the same
    as having no target at all.
    """
    overlap = sorted(set(hook.EXEMPT) & set(hook.BASELINE))
    assert not overlap, f"these are both exempt and baselined: {overlap}"
    assert all(reason.strip() for reason in hook.EXEMPT.values()), "every exemption states its reason"

    counts, _ = hook.uncovered_counts()
    stranded = sorted(rel for rel in hook.EXEMPT if rel not in counts)
    assert not stranded, f"exempt but no longer carrying the pattern -- stale claims: {stranded}"


def test_the_baseline_stores_no_address(literal: str) -> None:
    """The load-bearing one: this file is as public as the ones it guards.

    A baseline keyed by the literal would republish every address it exists to
    contain -- the same defect, one directory across.
    """
    pattern = hook.fleet_address_pattern()
    source = pathlib.Path(hook.__file__).read_text(encoding="utf-8")
    hits = [line for line in source.splitlines() if pattern.search(line)]
    assert not hits, f"{len(hits)} line(s) in the guard carry a fleet-range literal"
    assert all(isinstance(v, int) for v in hook.BASELINE.values())


def test_the_tree_is_clean_against_its_baseline() -> None:
    """The guard's own verdict on the real tree, so CI and pytest agree."""
    problems, reached = hook.audit()
    assert reached >= hook.DISCOVERY_FLOOR
    assert not problems, "the tree no longer matches BASELINE:\n  " + "\n  ".join(problems)
