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
        ("autobot-backend/api/x.py", True),
        ("deploy/site.yml", True),
        ("src/app.ts", True),
        ("docs/developer/GUIDE.md", True),
        ("autobot-slm-backend/ansible/README-PLAYBOOKS.md", False),
        ("config/grafana/dashboards/board.json", False),
        ("etc/autobot.service", False),
        ("scripts/autobot-ctl", False),
    ],
)
def test_coverage_is_the_complement_of_the_other_guards(rel: str, covered: bool) -> None:
    """The population is defined by what else already scans the file.

    `.md` is asymmetric on purpose: #15208 guards it under `docs/` and nowhere
    else, and the 311 occurrences in READMEs outside `docs/` are why this exists.
    """
    assert hook.is_covered(rel, hook.scanned_extensions()) is covered


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
