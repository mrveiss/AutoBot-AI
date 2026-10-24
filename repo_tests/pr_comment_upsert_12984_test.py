# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One sticky-PR-comment upsert (#12984).

Two things are checked and they are different kinds of evidence:

* BEHAVIOUR of `.github/actions/upsert-pr-comment/upsert_pr_comment.py`, run for real against a
  fake GitHub comments API on a local socket: no marker, marker on page 1, marker on page 3 (the
  bug the unpaginated copy had), several stale markers, a user quoting the marker.
* ABSENCE of a second implementation: no workflow `script:`/`run:` block and no Python source
  outside the action lists comments or edits a comment by id. A detector over text, so the
  contrast pair below shows it fires on the old shape and stays quiet on the fire-and-forget
  `createComment` calls that are deliberately not upserts.

What this does NOT cover: that the workflows wire the action correctly at run time. Workflows
cannot run locally; `test_both_callers_use_the_action` reads their YAML.
"""

from __future__ import annotations

import ast
import functools
import importlib.util
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
import yaml
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ACTION_DIR = ".github/actions/upsert-pr-comment"
_HELPER = f"{_ACTION_DIR}/upsert_pr_comment.py"
_REPO = "o/r"
_PR = 7
_MARK = "<!-- test-report -->"


def _load():
    spec = importlib.util.spec_from_file_location("upsert_pr_comment", repo_root() / _HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


helper = _load()


_LIST_PATH = f"/repos/{_REPO}/issues/{_PR}/comments"


class FakeGitHub:
    """A comments API: pages by `per_page`/`page`, `Link: rel="next"`, records writes."""

    def __init__(self, comments: list[dict], per_page_cap: int = 2) -> None:
        self.comments = comments
        self.cap = per_page_cap
        self.reads: list[str] = []
        self.writes: list[tuple[str, str, dict]] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args) -> None:
                pass

            def _reply(self, status: int, payload, link: str | None = None) -> None:
                raw = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                if link:
                    self.send_header("Link", link)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self) -> None:
                url = urlparse(self.path)
                query = parse_qs(url.query)
                page = int(query.get("page", ["1"])[0])
                size = min(int(query.get("per_page", ["30"])[0]), fake.cap)
                fake.reads.append(self.path)
                chunk = fake.comments[(page - 1) * size : page * size]
                more = page * size < len(fake.comments)
                # The next-page link names the one listing route, never echoes the request path into a header.
                link = f'<{fake.base}{_LIST_PATH}?per_page={size}&page={page + 1}>; rel="next"' if more else None
                self._reply(200, chunk, link)

            def _body(self) -> dict:
                return json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))

            def do_POST(self) -> None:
                fake.writes.append(("POST", self.path, self._body()))
                self._reply(201, {"id": 9000})

            def do_PATCH(self) -> None:
                fake.writes.append(("PATCH", self.path, self._body()))
                self._reply(200, {"id": 1})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def _comment(cid: int, body: str, user_type: str = "Bot") -> dict:
    return {"id": cid, "body": body, "user": {"type": user_type}, "created_at": f"2026-01-01T00:00:{cid:02d}Z"}


def _filler(count: int, start: int = 1) -> list[dict]:
    return [_comment(start + i, f"unrelated {i}") for i in range(count)]


@pytest.fixture
def api(request):
    comments = request.param
    fake = FakeGitHub(comments)
    yield fake
    fake.close()


def _run(fake: FakeGitHub, body: str = "report") -> tuple[str, int]:
    return helper.upsert(fake.base, _REPO, _PR, "tok", _MARK, body)


@pytest.mark.parametrize("api", [_filler(5)], indirect=True)
def test_no_marker_creates_one_comment(api) -> None:
    assert _run(api) == ("created", 9000)
    assert [w[0] for w in api.writes] == ["POST"]
    assert api.writes[0][1] == f"/repos/{_REPO}/issues/{_PR}/comments"
    assert api.writes[0][2]["body"] == f"{_MARK}\nreport"


@pytest.mark.parametrize("api", [[_comment(1, f"{_MARK}\nold")] + _filler(4, 2)], indirect=True)
def test_marker_on_page_one_updates_it(api) -> None:
    assert _run(api) == ("updated", 1)
    assert [(w[0], w[1]) for w in api.writes] == [("PATCH", f"/repos/{_REPO}/issues/comments/1")]


@pytest.mark.parametrize("api", [_filler(4) + [_comment(5, f"{_MARK}\nold")]], indirect=True)
def test_marker_on_page_three_is_found_not_duplicated(api) -> None:
    """The bug: a copy that read page 1 only appended a new comment here."""
    assert _run(api) == ("updated", 5)
    assert [w[0] for w in api.writes] == ["PATCH"]
    assert len(api.reads) == 3, f"expected 3 pages read, got {api.reads}"


@pytest.mark.parametrize(
    "api", [_filler(3) + [_comment(4, f"{_MARK}\na"), _comment(5, "x"), _comment(6, f"{_MARK}\nb")]], indirect=True
)
def test_several_stale_markers_update_the_newest_and_touch_nothing_else(api) -> None:
    assert _run(api) == ("updated", 6)
    assert [(w[0], w[1]) for w in api.writes] == [("PATCH", f"/repos/{_REPO}/issues/comments/6")]


@pytest.mark.parametrize("api", [[_comment(1, f"quoting {_MARK}", "User"), _comment(2, "x")]], indirect=True)
def test_a_person_quoting_the_marker_does_not_capture_the_slot(api) -> None:
    assert _run(api) == ("created", 9000)


@pytest.mark.parametrize("api", [[]], indirect=True)
def test_a_body_that_already_carries_the_marker_is_posted_verbatim(api) -> None:
    _run(api, f"{_MARK}\nbody")
    assert api.writes[0][2]["body"] == f"{_MARK}\nbody"


def test_an_empty_marker_is_refused() -> None:
    with pytest.raises(ValueError):
        helper.upsert("http://x", _REPO, _PR, "t", "  ", "b")


def test_a_non_http_api_url_is_refused() -> None:
    with pytest.raises(ValueError):
        helper.upsert("file:///etc", _REPO, _PR, "t", _MARK, "b")


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ('<https://a/x?page=2>; rel="next", <https://a/x?page=9>; rel="last"', "https://a/x?page=2"),
        ('<https://a/x?page=1>; rel="prev"', None),
        (None, None),
    ],
)
def test_next_page_url(header, expected) -> None:
    assert helper.next_page_url(header) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, 30.0), ("", 30.0), ("12.5", 12.5), ("0", 30.0), ("-3", 30.0), ("nan", 30.0), ("inf", 30.0), ("abc", 30.0)],
)
def test_the_timeout_accepts_only_a_positive_finite_number(raw, expected) -> None:
    assert helper.read_timeout(raw) == expected


# ---- the guard: no second implementation ---------------------------------------------------

_OLD_API = re.compile(r"\b(updateComment|listComments|update_comment|list_comments)\b|issues/comments/|--edit-last")


def _workflow_blocks(text: str) -> list[str]:
    """Every `run:` and `with.script:` string in a workflow or composite action."""
    blocks: list[str] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("run", "script") and isinstance(value, str):
                    blocks.append(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(yaml.safe_load(text) or {})
    return blocks


def _workflow_has_inline_upsert(text: str) -> bool:
    return any(_OLD_API.search(block) for block in _workflow_blocks(text))


def _python_has_inline_upsert(source: str) -> bool:
    """A string constant or called name that edits or lists comments. Comments and docstrings of
    other shapes are not constants this matcher can be fooled by: it reads the syntax tree."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and "issues/comments/" in node.value:
            if not (node.value.endswith("\n") or len(node.value) > 200):
                return True
        if isinstance(node, ast.Call):
            name = getattr(node.func, "attr", getattr(node.func, "id", ""))
            if name in ("update_comment", "list_comments", "edit_comment"):
                return True
    return False


_OLD_UNPAGINATED = """\
- uses: actions/github-script@v9
  with:
    script: |
      const { data: comments } = await github.rest.issues.listComments({owner, repo, issue_number});
      if (comments.find(c => c.body.includes('x'))) await github.rest.issues.updateComment({});
"""
_FIRE_AND_FORGET = """\
- uses: actions/github-script@v9
  with:
    script: |
      await github.rest.issues.createComment({owner, repo, issue_number, body: 'thanks'});
"""
_USES_THE_ACTION = """\
- uses: ./.github/actions/upsert-pr-comment
  with:
    marker: '<!-- m -->'
    body-file: /tmp/x.md
"""


@pytest.mark.parametrize(
    ("label", "text", "expected"),
    [
        ("the old unpaginated upsert", _OLD_UNPAGINATED, True),
        ("a fire-and-forget createComment", _FIRE_AND_FORGET, False),
        ("a caller of the action", _USES_THE_ACTION, False),
        ("a gh --edit-last", "- run: gh pr comment 1 --edit-last --body hi\n", True),
        ("the word in a YAML comment only", "# updateComment lives elsewhere\n- run: echo hi\n", False),
    ],
)
def test_the_workflow_matcher_tells_an_upsert_from_a_plain_comment(label, text, expected) -> None:
    assert _workflow_has_inline_upsert(text) is expected, label


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("a PATCH url", 'url = f"/repos/{r}/issues/comments/{cid}"\n', True),
        ("a helper call", "client.update_comment(cid, body)\n", True),
        ("posting a new comment", 'url = f"/repos/{r}/issues/{n}/comments"\n', False),
        ("a name in a comment", "# update_comment is elsewhere\nx = 1\n", False),
    ],
)
def test_the_python_matcher_tells_an_upsert_from_a_plain_post(label, source, expected) -> None:
    assert _python_has_inline_upsert(source) is expected, label


_GUARDED_ROOTS = (".github/workflows", "scripts", "tools", "pipeline-scripts", "autobot_shared")


def _population(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, *_GUARDED_ROOTS)
    except EmptyEnumeration:
        return []
    return [r for r in tracked if r.endswith((".yml", ".yaml", ".py")) and not r.endswith("_test.py")]


REACH = declare(
    "pr-comment-upsert-sweep",
    discover=_population,
    # Mid-window, from REACH.window() == (135, 435, 285).
    floor=285,
    what="workflow YAML and non-test python",
    roots=_GUARDED_ROOTS,
    growth=300,
)


@functools.lru_cache(maxsize=1)
def _offenders() -> tuple[str, ...]:
    found = []
    for rel in REACH.examined(repo_root()):
        text = (repo_root() / rel).read_text(encoding="utf-8")
        if rel == _HELPER:
            continue
        if rel.endswith(".py"):
            if _python_has_inline_upsert(text):
                found.append(rel)
        elif _workflow_has_inline_upsert(text):
            found.append(rel)
    return tuple(found)


def test_no_second_upsert_implementation_exists() -> None:
    assert _offenders() == (), (
        f"#12984: {list(_offenders())} implement their own find-and-update PR comment. Use "
        f"./{_ACTION_DIR} (marker + body-file); it reads every page of comments."
    )


@pytest.mark.parametrize(
    "rel", [".github/workflows/ssot-coverage.yml", ".github/workflows/_gate-ai-security-review.yml"]
)
def test_both_callers_use_the_action(rel: str) -> None:
    """READ, not run: the step exists, is advisory (continue-on-error), and names a marker."""
    text = (repo_root() / rel).read_text(encoding="utf-8")
    steps = [
        s
        for job in yaml.safe_load(text)["jobs"].values()
        for s in job.get("steps", [])
        if s.get("uses") == f"./{_ACTION_DIR}"
    ]
    assert len(steps) == 1, f"{rel}: {len(steps)} steps use the action"
    assert steps[0].get("continue-on-error") is True
    assert steps[0]["with"]["marker"].startswith("<!--")
