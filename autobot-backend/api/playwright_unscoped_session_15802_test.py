# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An unscoped Playwright caller must be visible, not silent (#15802).

`session_id` is optional on every Playwright request model, so a client written
before #11539 keeps working and lands in the shared default context. Neither end
can tell: the client believes it is isolated, the server sees a well-formed
request. One such caller shared the default context for roughly six months and
was found during unrelated host maintenance rather than by any check.

This does not make the field required — that would break every existing caller,
which is a decision rather than a fix. It makes the population discoverable, and
these tests assert that the signal fires exactly when it should.
"""

from __future__ import annotations

import logging

import pytest

from api.playwright import SESSION_AWARE_ROUTES, warn_if_unscoped


class _Client:
    host = "10.1.2.3"


class _Request:
    client = _Client()
    headers = {"user-agent": "legacy-mcp-server/0.3"}


class TestTheWarningFiresExactlyOnOmission:
    def test_an_omitted_session_id_warns(self, caplog):
        with caplog.at_level(logging.WARNING):
            warned = warn_if_unscoped("/navigate", None, _Request())

        assert warned is True
        assert any("without session_id" in r.message for r in caplog.records)

    def test_a_present_session_id_is_silent(self, caplog):
        """The contrast: warning on every call trains the reader to ignore it."""
        with caplog.at_level(logging.WARNING):
            warned = warn_if_unscoped("/navigate", "sess-abc", _Request())

        assert warned is False
        assert not [r for r in caplog.records if "without session_id" in r.message]

    def test_an_empty_string_counts_as_omitted(self, caplog):
        """`session_id=""` routes to the shared context exactly as `None` does,
        so treating it as scoped would be the same defect with a different
        spelling."""
        with caplog.at_level(logging.WARNING):
            warned = warn_if_unscoped("/navigate", "", _Request())

        assert warned is True


class TestTheWarningIdentifiesTheCaller:
    def test_the_caller_host_and_agent_are_named(self, caplog):
        """A warning that cannot identify who is unscoped does not make the
        population discoverable, which is the whole point."""
        with caplog.at_level(logging.WARNING):
            warn_if_unscoped("/interact", None, _Request())

        message = caplog.records[-1].getMessage()
        assert "10.1.2.3" in message
        assert "legacy-mcp-server/0.3" in message
        assert "/interact" in message

    def test_a_missing_http_request_still_warns(self, caplog):
        """Losing the caller's identity must not lose the warning."""
        with caplog.at_level(logging.WARNING):
            warned = warn_if_unscoped("/back", None, None)

        assert warned is True
        assert "unknown" in caplog.records[-1].getMessage()


class TestEverySessionAwareRouteIsInstrumented:
    """The reach half: a route added later without the call is invisible here."""

    def test_every_declared_route_calls_the_warning(self):
        import inspect

        import api.playwright as module

        source = inspect.getsource(module)
        missing = [route for route in SESSION_AWARE_ROUTES if f'warn_if_unscoped("{route}"' not in source]

        assert not missing, f"these session-aware routes do not warn on omission: {sorted(missing)}"

    def test_the_declared_set_is_not_empty(self):
        """A route set that emptied would make the assertion above vacuous."""
        assert len(SESSION_AWARE_ROUTES) >= 6
