# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One comment, an owned credential, and no ticked boxes (#17090 AC 4)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from agents import ac_poster
from agents.ac_poster import post_verification

_MODULE = Path(ac_poster.__file__)


@pytest.fixture
def gh(monkeypatch):
    """Capture what `gh` would have been asked to do."""
    calls: list[list[str]] = []
    box = {"code": 0, "stderr": "", "vault_backed": True}

    def _gh_env():
        return ({"GH_TOKEN": "t"} if box["vault_backed"] else {}), box["vault_backed"]

    def _run_gh(args, *, body, env, cwd):
        calls.append(args)
        return box["code"], box["stderr"]

    monkeypatch.setattr(ac_poster, "gh_env", _gh_env)
    monkeypatch.setattr(ac_poster, "_run_gh", _run_gh)
    monkeypatch.setattr(ac_poster, "git_repo_root", lambda: Path("."))
    return {"calls": calls, "box": box}


class TestTheCredentialIsOwned:
    def test_without_a_vault_token_it_refuses_rather_than_using_ambient_auth(self, gh):
        gh["box"]["vault_backed"] = False

        outcome = post_verification(17090, "body")

        assert outcome.posted is False
        assert "ambient" in outcome.reason
        assert gh["calls"] == [], "nothing may be sent to GitHub without an owned credential (#13859)"

    def test_with_a_vault_token_it_posts(self, gh):
        outcome = post_verification(17090, "body")

        assert outcome.posted is True and outcome.vault_backed is True


class TestOneComment:
    def test_it_posts_exactly_one_comment(self, gh):
        post_verification(17090, "body")

        assert len(gh["calls"]) == 1

    def test_it_uses_the_comment_verb_on_the_right_issue(self, gh):
        post_verification(17090, "body")

        assert gh["calls"][0][:3] == ["issue", "comment", "17090"]

    def test_the_body_goes_on_stdin_not_on_the_command_line(self, gh):
        """A long markdown body as an argv element hits the argument limit and
        puts the whole comment in the process list."""
        post_verification(17090, "body")

        assert "--body-file" in gh["calls"][0] and "--body" not in gh["calls"][0]

    def test_a_gh_failure_is_reported_not_swallowed(self, gh):
        gh["box"]["code"] = 1
        gh["box"]["stderr"] = "HTTP 403"

        outcome = post_verification(17090, "body")

        assert outcome.posted is False and "403" in outcome.reason


class TestReadingTheIssue:
    def test_without_a_vault_token_it_refuses_to_read_too(self, gh, monkeypatch):
        gh["box"]["vault_backed"] = False

        with pytest.raises(ac_poster.IssueUnreadable, match="ambient"):
            ac_poster.fetch_issue(17090)

    def test_a_body_and_its_comments_come_back(self, gh, monkeypatch):
        payload = '{"body": "## Acceptance criteria\\n- [ ] one\\n", "comments": [{"id": "c1", "body": "hi"}]}'
        monkeypatch.setattr(ac_poster, "_run_gh_capture", lambda args, **kw: (0, payload, ""))

        body, comments = ac_poster.fetch_issue(17090)

        assert "- [ ] one" in body and comments == [("c1", "hi")]

    def test_an_unreadable_issue_raises_rather_than_reading_as_empty(self, gh, monkeypatch):
        """ "No criteria" and "nobody read it" must not produce the same comment."""
        monkeypatch.setattr(ac_poster, "_run_gh_capture", lambda args, **kw: (1, "", "HTTP 404"))

        with pytest.raises(ac_poster.IssueUnreadable, match="404"):
            ac_poster.fetch_issue(17090)

    def test_unparseable_json_raises_too(self, gh, monkeypatch):
        monkeypatch.setattr(ac_poster, "_run_gh_capture", lambda args, **kw: (0, "not json", ""))

        with pytest.raises(ac_poster.IssueUnreadable, match="unparseable"):
            ac_poster.fetch_issue(17090)


class TestItNeverTicksABox:
    """#17090 AC 4 keeps ticking with a human. A rule held only by "nobody has
    written that call yet" is not held at all, so this reads the module."""

    @staticmethod
    def _gh_verbs() -> set[tuple[str, ...]]:
        tree = ast.parse(_MODULE.read_text(encoding="utf-8"))
        verbs: set[tuple[str, ...]] = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for arg in node.args:
                if isinstance(arg, ast.List):
                    literals = tuple(e.value for e in arg.elts if isinstance(e, ast.Constant))
                    if literals and literals[0] in ("issue", "pr", "api"):
                        verbs.add(literals[:2])
        return verbs

    #: Verbs that change an issue. `edit` is the one that could tick a box;
    #: the rest are here because "it only edits" is the argument that would be
    #: made for adding them.
    _MUTATING = {"edit", "close", "reopen", "delete", "transfer", "pin", "unpin", "lock", "unlock"}

    def test_the_only_write_verb_is_commenting(self):
        assert {verb for _, verb in self._gh_verbs() if verb not in ("view",)} == {"comment"}

    def test_no_mutating_verb_appears_at_all(self):
        assert not {verb for _, verb in self._gh_verbs()} & self._MUTATING

    def test_the_detector_would_notice_another_verb(self):
        """Positive control: an assertion about absence needs a demonstrated presence."""
        assert self._gh_verbs() == {("issue", "comment"), ("issue", "view")}

    def test_no_checkbox_rewriting_helper_hides_in_the_module(self):
        source = _MODULE.read_text(encoding="utf-8")

        assert "- [x]" not in source
        assert "issue edit" not in source
