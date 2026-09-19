# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``secrets_baseline_legacy_keys.json`` is excluded from detect-secrets, and
that exclusion can never hide a real secret (#17130).

The file records 1,355 ``(filename, type, hashed_secret)`` triples --
bookkeeping about *already-audited* findings elsewhere in the repo, not
source material of its own. Every ``hashed_secret`` is a 40-hex-char SHA1
digest, which is itself indistinguishable from a "Hex High Entropy String"
to detect-secrets' own plugin -- scanning this file therefore produced ~698
hash-of-a-hash findings with no baseline entry to audit them against
(nothing scans a file this shape without producing them), failing the
whole-tree CI job on every PR whose diff touched an unrelated path that
happened to flip on that job's path filter.

Adding 698 entries to ``.secrets.baseline`` (marking each ``is_secret:
false``) does not fix this: the fix's own record of *which* hashes were
exempted is itself a file of 40-hex strings, so it gets flagged too, in
successive generations, forever. The actual fix is a
``detect_secrets.filters.regex.should_exclude_file`` entry in
``.secrets.baseline``'s own ``filters_used`` -- the ONE place both the
pre-commit hook and the whole-tree CI job read (both invoke
``detect-secrets scan --baseline .secrets.baseline`` with no other exclude
flag), verified empirically: the pattern persists in the baseline and is
honoured on a rescan that never re-passes ``--exclude-files``.

That trades a false-positive fight for a blind spot, so this file closes it:
an excluded file could quietly gain a real secret with nothing to catch it.
The shape check below is what stands in for the scan that no longer runs --
every entry must still be exactly ``[filename: str, type: str, hashed_secret:
40-hex-char str]`` and nothing else, so a change that put a raw credential
(any non-hash-shaped value) in this file would fail here even though
detect-secrets itself will never look at it again.
"""

from __future__ import annotations

import json
import re

from repo_tests._paths import repo_root
from repo_tests.secrets_baseline_reasons import load_legacy_keys

_REPO_ROOT = repo_root()
_BASELINE = _REPO_ROOT / ".secrets.baseline"
_LEGACY_KEYS_PATH = _REPO_ROOT / "repo_tests" / "secrets_baseline_legacy_keys.json"
_EXCLUDE_FILTER_PATH = "detect_secrets.filters.regex.should_exclude_file"
_HASHED_SECRET_RE = re.compile(r"^[0-9a-f]{40}$")


def _exclude_file_patterns() -> list[str]:
    baseline = json.loads(_BASELINE.read_text(encoding="utf-8"))
    filters = baseline.get("filters_used")
    assert isinstance(filters, list) and filters, f"{_BASELINE} holds no filters_used"
    patterns: list[str] = []
    for entry in filters:
        if entry.get("path") == _EXCLUDE_FILTER_PATH:
            patterns.extend(entry.get("pattern", []))
    return patterns


def test_legacy_keys_file_is_excluded_from_detect_secrets() -> None:
    """The exclusion this guard exists to keep safe must actually be present."""
    patterns = _exclude_file_patterns()
    assert patterns, (
        f"{_BASELINE}'s filters_used has no {_EXCLUDE_FILTER_PATH} entry -- without it, "
        "every hashed_secret inside secrets_baseline_legacy_keys.json is scanned as if it "
        "were source material and flagged as a fresh, unaudited finding (#17130)."
    )
    assert any(re.fullmatch(p, "repo_tests/secrets_baseline_legacy_keys.json") for p in patterns), (
        f"None of {patterns} matches repo_tests/secrets_baseline_legacy_keys.json -- "
        "the exclusion does not cover the file it is meant to."
    )


def test_legacy_keys_file_holds_only_filename_type_hash_triples() -> None:
    """Excluding the file from scanning removes the one check that would
    otherwise catch a real secret landing in it -- this replaces that check."""
    raw = json.loads(_LEGACY_KEYS_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw, list) and raw, f"{_LEGACY_KEYS_PATH} holds no entries"

    offenders = []
    for entry in raw:
        if not (isinstance(entry, list) and len(entry) == 3):
            offenders.append(f"{entry!r}: not a 3-element [filename, type, hashed_secret] list")
            continue
        filename, secret_type, hashed_secret = entry
        if not (isinstance(filename, str) and filename):
            offenders.append(f"{entry!r}: filename is not a non-empty string")
        if not (isinstance(secret_type, str) and secret_type):
            offenders.append(f"{entry!r}: type is not a non-empty string")
        if not (isinstance(hashed_secret, str) and _HASHED_SECRET_RE.match(hashed_secret)):
            offenders.append(f"{entry!r}: hashed_secret is not a 40-char lowercase hex string")

    assert not offenders, (
        f"{len(offenders)} entr{'y' if len(offenders) == 1 else 'ies'} in {_LEGACY_KEYS_PATH} "
        "do not match the [filename, type, 40-hex-char hashed_secret] shape this exclusion "
        "relies on -- a raw credential could be hiding in a file detect-secrets never scans:\n"
        + "\n".join(offenders[:10])
    )


def test_offenders_detects_a_planted_non_hash_value() -> None:
    """Self-test: the shape check actually looks, on data it knows is wrong."""
    raw = [["some/file.py", "Secret Keyword", "not-a-real-hash"]]  # pragma: allowlist secret
    offenders = []
    for entry in raw:
        filename, secret_type, hashed_secret = entry
        if not _HASHED_SECRET_RE.match(hashed_secret):
            offenders.append(entry)
    assert offenders == raw


def test_load_legacy_keys_agrees_with_the_shape_check() -> None:
    """The set secrets_baseline_reasons.py actually loads is the same data
    this guard validated -- not a stale copy read some other way."""
    loaded = load_legacy_keys()
    raw = json.loads(_LEGACY_KEYS_PATH.read_text(encoding="utf-8"))
    assert loaded == frozenset(tuple(entry) for entry in raw)
