# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Fail once, at startup, when a config value is still an unfilled template placeholder (#20886).

`.env.example` ships values such as `YOUR_REDIS_IP`. Left unreplaced they reach each client as a
hostname, and every client then fails on its own with "Name or service not known". One check names
every offender in one error instead.
"""

import os
import re
from typing import Mapping

_PLACEHOLDER = re.compile(r"^YOUR_[A-Z0-9_]+$")
# Only AutoBot's own settings: an unrelated variable set to a `YOUR_*` value must not block startup.
SETTING_PREFIX = "AUTOBOT_"


class PlaceholderConfigError(RuntimeError):
    """One or more settings still hold an unfilled `YOUR_*` template value."""


def find_placeholders(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return {name: value} for every AutoBot setting whose whole value is a `YOUR_*` placeholder."""
    env = os.environ if environ is None else environ
    return {k: v for k, v in sorted(env.items()) if k.startswith(SETTING_PREFIX) and _PLACEHOLDER.match(v.strip())}


def enforce_no_placeholders(environ: Mapping[str, str] | None = None) -> None:
    """Raise one clear error naming (never echoing the value of) every setting that holds a placeholder."""
    found = find_placeholders(environ)
    if found:
        raise PlaceholderConfigError(_message(sorted(found)))


def _message(names: list[str]) -> str:
    """Names only: a real secret that happens to match the pattern must not reach the error or the log."""
    return (
        f"Unfilled placeholder in configuration: {', '.join(names)}. Replace each with the real value "
        "(see .env.example) before starting."
    )
