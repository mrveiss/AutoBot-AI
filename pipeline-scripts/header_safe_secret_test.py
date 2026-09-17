# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A malformed CI token must not reach a log, a message or a traceback (#15204).

Every assertion here is on the **absence of the value**, never on the wording of
the message. The issue asks for that explicitly, and the reason is that an
assertion on text passes for the wrong reason the moment someone rewords the
error while reintroducing the leak.

``TestTheHazardIsReal`` pins the contrast in code rather than describing it in a
PR body: ``http.client`` genuinely does interpolate the header value into its
``ValueError``. If a future stdlib stops doing that, this file says so instead of
the guard quietly becoming decoration.
"""

from __future__ import annotations

import http.client

import ci_dispatch_watchdog as watchdog
import pytest
from header_safe_secret import HeaderUnsafeSecret, require_header_safe

# Distinctive so a substring check cannot pass by accident, and shaped like the
# real failure: a token with a stray character from a bad paste or a truncation.
LEAKY = "ghp_AaBbCcDd1234567890EeFfGg"
GOOD = "ghp_0123456789abcdefghijklmnopqrstuvwx"

MALFORMED = {
    "newline": f"{LEAKY}\nX-Injected: 1",
    "carriage_return": f"{LEAKY}\rX-Injected: 1",
    "null_byte": f"{LEAKY}\0",
    "non_latin1": f"{LEAKY}—",  # an em dash, the classic copy-paste import
}


class TestTheHazardIsReal:
    """The premise: without a guard, the value lands in the exception."""

    def test_http_client_puts_the_header_value_in_its_error(self) -> None:
        conn = http.client.HTTPConnection("localhost", 9)
        conn.putrequest("GET", "/")  # buffers only; opens no socket
        with pytest.raises(ValueError) as caught:
            conn.putheader("Authorization", f"Bearer {MALFORMED['newline']}")
        assert LEAKY in str(caught.value), "the leak this issue exists for is gone — re-read the guard"


class TestTheValueNeverAppears:
    @pytest.mark.parametrize("fault", sorted(MALFORMED))
    def test_a_malformed_token_is_refused_without_being_quoted(self, fault: str) -> None:
        with pytest.raises(HeaderUnsafeSecret) as caught:
            require_header_safe(MALFORMED[fault], "GITHUB_TOKEN")
        message = str(caught.value)
        assert LEAKY not in message, f"{fault}: the message quotes the credential"
        assert MALFORMED[fault] not in message

    @pytest.mark.parametrize("fault", sorted(MALFORMED))
    def test_nothing_is_chained_that_could_quote_it(self, fault: str) -> None:
        """A chained cause prints in the traceback too, so `raise ... from None`."""
        with pytest.raises(HeaderUnsafeSecret) as caught:
            require_header_safe(MALFORMED[fault], "GITHUB_TOKEN")
        assert caught.value.__cause__ is None
        assert LEAKY not in str(caught.value.__context__ or "")

    def test_an_empty_token_is_refused(self) -> None:
        with pytest.raises(HeaderUnsafeSecret):
            require_header_safe("", "GITHUB_TOKEN")

    def test_a_well_formed_token_passes_through_unchanged(self) -> None:
        assert require_header_safe(GOOD, "GITHUB_TOKEN") == GOOD

    def test_the_caller_chooses_the_error_type(self) -> None:
        with pytest.raises(watchdog.WatchdogConfigError):
            require_header_safe(MALFORMED["newline"], "GITHUB_TOKEN", watchdog.WatchdogConfigError)


class TestTheWatchdogPathsAreClosed:
    """Both ways the token can reach the HTTP layer."""

    def test_constructing_the_client_refuses_it(self) -> None:
        with pytest.raises(watchdog.WatchdogConfigError) as caught:
            watchdog.GitHubApi(MALFORMED["newline"], "owner/repo")
        assert LEAKY not in str(caught.value)

    def test_load_config_refuses_it(self, monkeypatch) -> None:
        # Not the null-byte variant: os.environ itself refuses one, so that case
        # can never reach load_config and testing it here would prove nothing.
        monkeypatch.setenv("GITHUB_TOKEN", MALFORMED["carriage_return"])
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
        with pytest.raises(watchdog.WatchdogConfigError) as caught:
            watchdog.load_config()
        assert LEAKY not in str(caught.value)

    def test_main_exits_cleanly_instead_of_raising_a_traceback(self, monkeypatch, capsys) -> None:
        """The property the issue is actually about.

        main() used to construct GitHubApi *outside* its handler, so a refusal
        raised here would have escaped as the traceback this guards against.
        """
        monkeypatch.setenv("GITHUB_TOKEN", MALFORMED["newline"])
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
        assert watchdog.main(["--check", "probe"]) == 2
        captured = capsys.readouterr()
        assert LEAKY not in captured.out + captured.err
