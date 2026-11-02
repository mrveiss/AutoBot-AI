#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Upsert one sticky pull-request comment, identified by an invisible marker (#12984).

The one implementation behind `.github/actions/upsert-pr-comment`. Two workflows used to carry
their own copy and the copies diverged: one paginated and matched an HTML marker, the other read
only the first page of comments (30 by default) and matched a visible heading, so on a pull
request with more than 30 comments it stopped finding its own comment and appended a new one on
every run.

Contract:
  * Every page of the comment list is read, following the `Link: rel="next"` header.
  * A comment is ours when its author is a Bot AND its body contains the marker. A person
    quoting the marker cannot capture the slot.
  * Several matches (stale duplicates left by the old behaviour): the NEWEST is updated, since
    it is the one a reader sees; the rest are left alone and named in the log. Deleting them is
    a data deletion and is proposed, never done here.
  * No match: a new comment is created.
  * The marker is prepended to the body when the body does not already carry it.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any, Iterator

logger = logging.getLogger(__name__)

PAGE_SIZE = 100
DEFAULT_TIMEOUT_SECONDS = 30.0
TIMEOUT_ENV = "AUTOBOT_UPSERT_COMMENT_TIMEOUT"


def read_timeout(raw: str | None) -> float:
    """A positive finite number of seconds, else the default with a warning.

    Local on purpose: this file runs on a bare runner with only the standard library, so it
    cannot import `autobot_shared.env_utils.env_float_clamped`. Same `positive_finite`
    semantics: NaN, infinity, zero and negatives are rejected, not clamped.
    """
    if raw is None or not raw.strip():
        return DEFAULT_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        value = math.nan
    if not math.isfinite(value) or value <= 0:
        logger.warning("%s=%r is not a positive finite number; using %s", TIMEOUT_ENV, raw, DEFAULT_TIMEOUT_SECONDS)
        return DEFAULT_TIMEOUT_SECONDS
    return value


TIMEOUT_SECONDS = read_timeout(os.environ.get(TIMEOUT_ENV))
_NEXT_LINK = re.compile(r'<([^>]+)>\s*;\s*rel="next"')


def next_page_url(link_header: str | None) -> str | None:
    """The `rel="next"` target of a `Link` header, or None on the last page."""
    match = _NEXT_LINK.search(link_header or "")
    return match.group(1) if match else None


def _call(method: str, url: str, token: str, payload: dict[str, Any] | None = None) -> tuple[Any, str | None]:
    """One authenticated API call; returns the decoded JSON and the `Link` header."""
    if not url.startswith(("https://", "http://")):
        raise ValueError(f"refusing a non-http(s) API URL: {url!r}")
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(  # noqa: S310 -- scheme checked above; URL is the runner's own API root
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310  # nosec B310
        return json.loads(response.read().decode("utf-8")), response.headers.get("Link")


def iter_comments(api_url: str, repo: str, number: int, token: str) -> Iterator[dict[str, Any]]:
    """Every comment on the issue/PR, across all pages."""
    url: str | None = f"{api_url}/repos/{repo}/issues/{number}/comments?per_page={PAGE_SIZE}"
    while url:
        page, link = _call("GET", url, token)
        yield from page
        url = next_page_url(link)


def is_ours(comment: dict[str, Any], marker: str) -> bool:
    return (comment.get("user") or {}).get("type") == "Bot" and marker in (comment.get("body") or "")


def with_marker(body: str, marker: str) -> str:
    return body if marker in body else f"{marker}\n{body}"


def upsert(api_url: str, repo: str, number: int, token: str, marker: str, body: str) -> tuple[str, int]:
    """Update our newest comment, else create one. Returns ("updated"|"created", comment id)."""
    if not marker.strip():
        raise ValueError("marker must be a non-empty string")
    mine = [c for c in iter_comments(api_url, repo, number, token) if is_ours(c, marker)]
    payload = {"body": with_marker(body, marker)}
    if mine:
        newest = max(mine, key=lambda c: (c.get("created_at") or "", c["id"]))
        stale = sorted(c["id"] for c in mine if c["id"] != newest["id"])
        if stale:
            logger.warning("%d older comment(s) carry the marker and were left alone: %s", len(stale), stale)
        _call("PATCH", f"{api_url}/repos/{repo}/issues/comments/{newest['id']}", token, payload)
        return "updated", newest["id"]
    created, _ = _call("POST", f"{api_url}/repos/{repo}/issues/{number}/comments", token, payload)
    return "created", created["id"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--marker", required=True)
    parser.add_argument("--body-file", required=True)
    parser.add_argument("--number", type=int, required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--api-url", required=True)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    with open(args.body_file, encoding="utf-8") as handle:
        body = handle.read()
    action, comment_id = upsert(
        args.api_url.rstrip("/"), args.repo, args.number, os.environ["GITHUB_TOKEN"], args.marker, body
    )
    logger.info("%s comment %s on #%s", action, comment_id, args.number)
    return 0


if __name__ == "__main__":
    sys.exit(main())
