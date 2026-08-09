# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the issue-triage label selector (#13050).

The selector is JavaScript because the workflow runs it under
``actions/github-script``. These tests drive it through ``node`` so the real
module is exercised rather than a Python re-implementation of its rules — a
paraphrase would drift from the file the workflow actually loads.

The fixtures are the real issues that were mislabelled: #13032-#13036 were pure
backend Python issues that received ``frontend`` (for "interface"/"component"),
``docs`` (for quoting a module docstring) and ``advanced`` (for the package name
``llm_shared/optimization/``).
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess

import pytest

_MODULE = pathlib.Path(__file__).resolve().parents[1] / ".github" / "scripts" / "issue-triage-labels.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not available")


def select(title: str = "", body: str = "", labels: list[str] | None = None) -> dict:
    """Run the real selector under node and return its decision."""
    payload = json.dumps({"title": title, "body": body, "labels": labels or []})
    script = (
        f"const {{selectLabels}} = require({json.dumps(str(_MODULE))});"
        f"process.stdout.write(JSON.stringify(selectLabels({payload})));"
    )
    result = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=30, encoding="utf-8", check=True
    )
    return json.loads(result.stdout)


class TestSubstringRegression:
    """#13050: keywords must match whole words, never substrings."""

    @pytest.mark.parametrize(
        "word",
        ["platform", "format", "information", "performance", "normal"],
    )
    def test_orm_does_not_match_inside_longer_words(self, word):
        """'orm' used to label anything containing 'platform' or 'performance' as backend."""
        assert select(body=f"The {word} needs review.")["labels"] == []

    @pytest.mark.parametrize("word", ["build", "require", "guide", "quick"])
    def test_ui_does_not_match_inside_longer_words(self, word):
        """'ui' used to label anything containing 'build' or 'require' as frontend."""
        assert select(body=f"We should {word} this.")["labels"] == []


class TestRealMislabelledIssues:
    """The #13032-#13036 shape, which is this issue's stated acceptance case."""

    BODY = (
        "The LayerInferenceEngine in llm_shared/optimization/ cannot produce correct output. "
        'Its docstring says """Stream layers from disk for large-model inference.""" but there is '
        "no embedding layer and no LM head, so the public interface returns hidden states rather "
        "than logits. Each component of the pipeline is exercised by the optimization tests."
    )

    def test_backend_issue_is_not_labelled_frontend_docs_or_advanced(self):
        """The acceptance criterion from #13050, verbatim."""
        result = select(title="bug(optimization): LayerInferenceEngine cannot produce correct output", body=self.BODY)

        # #13050's acceptance criterion is "receives `backend` and nothing else",
        # not merely "is not labelled wrongly" — asserting only absences passes
        # vacuously even if the selector returns nothing at all.
        assert result["labels"] == ["backend"]

    def test_explicit_backend_scope_wins(self):
        """A conventional-commit scope is the author's own statement of the area."""
        assert select(title="bug(backend): endpoint drops payload", body=self.BODY)["labels"] == ["backend"]


class TestAlreadyTriaged:
    """#13050: an explicit skill label at creation must suppress auto-triage entirely."""

    def test_existing_skill_label_suppresses_triage(self):
        result = select(title="bug(backend): something", body="python fastapi", labels=["backend"])
        assert result["labels"] == []
        assert "already carries a skill-area label" in result["reason"]

    def test_three_explicit_labels_are_respected(self):
        """The old guard was `labels.length > 3`, so three labels still got auto-triaged."""
        result = select(title="perf(ci): slow", body="docker ansible", labels=["bug", "backend", "priority"])
        assert result["labels"] == []


class TestPrefersNoLabelOverWrongLabel:
    """#13050 fix item 5."""

    def test_prose_matching_four_areas_yields_no_label(self):
        """Four or more areas is noise, not evidence.

        The threshold is 4 rather than 3 deliberately: two areas is a normal
        cross-cutting issue, and three is common in this repo (a vue dashboard
        calling a fastapi endpoint deployed with ansible really does span three).
        Silencing those loses correct labels, which is its own cost.
        """
        result = select(
            body="The vue dashboard calls a fastapi endpoint deployed with docker, "
            "with pytest coverage and a README describing the tutorial."
        )
        assert result["labels"] == []
        assert "too ambiguous" in result["reason"]

    def test_prose_matching_three_areas_is_still_labelled(self):
        """The counterpart: three areas is legitimate, not noise."""
        result = select(body="The vue dashboard calls a fastapi endpoint deployed with ansible.")
        assert sorted(result["labels"]) == ["backend", "frontend", "infrastructure"]

    def test_unremarkable_prose_yields_no_label(self):
        result = select(title="Something is wrong", body="It does not work as expected.")
        assert result["labels"] == []
        assert result["reason"] == "no confident signal"


class TestStillLabelsCorrectly:
    """The selector must remain useful, not merely safe."""

    def test_genuine_frontend_issue(self):
        assert select(title="Sidebar collapses", body="The vue component uses vite and css")["labels"] == ["frontend"]

    def test_genuine_infrastructure_issue(self):
        assert select(title="Deploy fails", body="ansible playbook errors on the systemd unit")["labels"] == [
            "infrastructure"
        ]

    def test_scope_maps_ci_to_infrastructure(self):
        assert select(title="perf(ci): shard the suite", body="split across runners")["labels"] == ["infrastructure"]


class TestKeywordHygiene:
    """Guards against reintroducing the #13050 keyword set."""

    def test_every_keyword_matches_itself(self):
        """Guards the `\\b` inversion trap: a keyword with a non-word edge
        (`.env`, `c++`) silently never fires. Each keyword must match a sentence
        containing it — the property, not the spelling."""
        script = (
            f"const m = require({json.dumps(str(_MODULE))});"
            "const all = [].concat(...Object.values(m.KEYWORDS), ...Object.values(m.DIFFICULTY_KEYWORDS));"
            "const dead = all.filter((k) => !m.matchesWord(`before ${k} after`, k));"
            "process.stdout.write(JSON.stringify(dead));"
        )
        result = subprocess.run(
            ["node", "-e", script], capture_output=True, text=True, timeout=30, encoding="utf-8", check=True
        )
        assert json.loads(result.stdout) == [], "these keywords can never match anything"

    def test_no_keyword_is_shorter_than_three_characters(self):
        """Two-character keywords are what made 'ui' match 'build' (#13050)."""
        script = (
            f"const m = require({json.dumps(str(_MODULE))});"
            "const all = [].concat(...Object.values(m.KEYWORDS), ...Object.values(m.DIFFICULTY_KEYWORDS));"
            "process.stdout.write(JSON.stringify(all.filter((k) => k.length < 3)));"
        )
        result = subprocess.run(
            ["node", "-e", script], capture_output=True, text=True, timeout=30, encoding="utf-8", check=True
        )
        assert json.loads(result.stdout) == []

    @pytest.mark.parametrize(
        "banned,body",
        [
            ("interface", "the public interface returns hidden states"),
            ("component", "each component of the pipeline is exercised"),
            ("comment", "the comment above the guard is stale"),
            ("optimization", "the optimization package has no embedding layer"),
        ],
    )
    def test_banned_backend_vocabulary_implies_nothing(self, banned, body):
        """The four words that mislabelled #13032-#13036.

        Asserted behaviourally rather than by grepping the source: the previous
        version searched only the KEYWORDS block, so 'optimization' — which lived
        in DIFFICULTY_KEYWORDS — passed vacuously and would still pass if it were
        reintroduced there, i.e. it never guarded the regression it named.
        """
        assert select(body=body)["labels"] == [], f"{banned!r} must not imply a label on its own"
