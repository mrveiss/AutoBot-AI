# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for marketplace remote-catalog hardening (Issue #6525).

Three defects in the pre-fix ``_remote_plugin_to_entry`` adapter:
  1. ``dict.get(key, default)`` returns the stored value when the key is
     present-but-null — so ``{"name": None}.get("name", "")`` returns None
     and downstream ``.replace``/``.title`` crashed.
  2. Single malformed entry from a user-added remote 500s the whole
     ``/catalog?source_id=...`` request — trivial DoS surface.
  3. ``str.title()`` butchers acronyms (``"GIT-tools"`` → ``"Git Tools"``)
     and apostrophes (``"don't-panic"`` → ``"Don'T Panic"``).
"""

import logging

from api.marketplace import (
    _coerce_list,
    _coerce_str,
    _remote_plugin_to_entry,
    _safe_remote_plugin_to_entry,
)


class TestCoerceHelpers:
    """#6525: type coercion contracts."""

    def test_coerce_str_passes_string_through(self):
        assert _coerce_str("hello") == "hello"

    def test_coerce_str_returns_fallback_for_none(self):
        assert _coerce_str(None) == ""
        assert _coerce_str(None, fallback="x") == "x"

    def test_coerce_str_returns_fallback_for_non_string(self):
        assert _coerce_str(42) == ""
        assert _coerce_str([], fallback="lst") == "lst"
        assert _coerce_str({"a": 1}) == ""

    def test_coerce_list_passes_list_through(self):
        assert _coerce_list(["a", "b"]) == ["a", "b"]

    def test_coerce_list_returns_empty_for_non_list(self):
        assert _coerce_list(None) == []
        assert _coerce_list("string") == []
        assert _coerce_list({"k": "v"}) == []


class TestRemotePluginToEntryHardening:
    """#6525: type-coerce all string fields against null/non-string remotes."""

    def test_null_name_does_not_crash(self):
        """Pre-fix: AttributeError on .replace(...) of None. Now coerced to ''."""
        entry = _remote_plugin_to_entry({"name": None, "version": "1.0"}, "src")
        assert entry["name"] == ""
        assert entry["display_name"] == ""

    def test_null_tags_becomes_empty_list(self):
        entry = _remote_plugin_to_entry({"name": "ok", "tags": None}, "src")
        assert entry["tags"] == []

    def test_non_string_category_falls_back_to_default(self):
        """A remote sending category=123 must not propagate an int into the response."""
        entry = _remote_plugin_to_entry({"name": "ok", "category": 123}, "src")
        # Should fall back to the OTHER default since 123 is not a string.
        assert entry["category"] == "other"

    def test_null_author_falls_back_to_source_name(self):
        entry = _remote_plugin_to_entry({"name": "ok", "author": None}, "alt-source")
        assert entry["author"] == "alt-source"

    def test_display_name_preserves_acronyms_and_apostrophes(self):
        """Pre-fix str.title() butchered these; now we use upstream display_name
        when supplied, else fall back to raw name (untransformed)."""
        # Upstream display_name preserved verbatim.
        entry = _remote_plugin_to_entry(
            {"name": "git-tools", "display_name": "GIT Tools"},
            "src",
        )
        assert entry["display_name"] == "GIT Tools"

        # No display_name → raw name kept verbatim (no .title()).
        entry = _remote_plugin_to_entry({"name": "don't-panic"}, "src")
        assert entry["display_name"] == "don't-panic"

        # No display_name → keep ALL-CAPS acronym intact.
        entry = _remote_plugin_to_entry({"name": "GIT-tools"}, "src")
        assert entry["display_name"] == "GIT-tools"


class TestSafeRemotePluginToEntry:
    """#6525: per-item wrapper turns one bad plugin into a logged skip."""

    def test_dict_entry_passes_through(self):
        entry = _safe_remote_plugin_to_entry({"name": "ok", "version": "1.0"}, "src")
        assert entry is not None
        assert entry["name"] == "ok"

    def test_non_dict_entry_returns_none_with_log(self, caplog):
        with caplog.at_level(logging.WARNING, logger="api.marketplace"):
            assert _safe_remote_plugin_to_entry("not-a-dict", "src") is None
            assert _safe_remote_plugin_to_entry(None, "src") is None
            assert _safe_remote_plugin_to_entry(42, "src") is None
        assert any("Skipping non-dict catalog entry" in r.getMessage() for r in caplog.records)

    def test_dos_proof_one_bad_apple_does_not_break_others(self):
        """The exact DoS scenario from the issue: one bad entry between two good ones."""
        remote = [
            {"name": "good-plugin", "version": "1.0"},
            {"name": None, "version": "1.0"},  # was: AttributeError on .replace
            {"name": "another", "version": "1.0"},
        ]
        # Pre-fix this list comp crashed on item 1, returning none of the good ones.
        catalog = [entry for p in remote for entry in (_safe_remote_plugin_to_entry(p, "src"),) if entry is not None]
        # Even with the new coercion, ``{"name": None}`` produces a valid entry
        # (name=""), but it's still a real entry — only structurally broken
        # entries are filtered. So expect 3 here, not 2. The DoS-proof is that
        # the comprehension does not raise.
        assert len(catalog) == 3
        names = {e["name"] for e in catalog}
        assert "good-plugin" in names
        assert "another" in names

    def test_truly_broken_entry_is_logged_and_skipped(self, caplog):
        """A non-dict in the remote payload is dropped, not crashing."""
        remote = [
            {"name": "good"},
            "totally-broken-string",
            42,
            {"name": "good2"},
        ]
        with caplog.at_level(logging.WARNING, logger="api.marketplace"):
            catalog = [
                entry for p in remote for entry in (_safe_remote_plugin_to_entry(p, "src"),) if entry is not None
            ]
        assert len(catalog) == 2
        # Two warnings — one per dropped non-dict.
        warnings = [r for r in caplog.records if "Skipping non-dict" in r.getMessage()]
        assert len(warnings) == 2
