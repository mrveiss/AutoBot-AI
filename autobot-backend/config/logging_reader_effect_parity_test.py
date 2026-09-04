# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every ``logging.*`` config key with a reader also has an effect (#15587).

``services/config_service.py`` read four keys --
``logging.console``, ``logging.log_requests``, ``logging.log_sql``,
``logging.max_file_size`` -- for the settings UI and was their *only* reader
in the whole tree. Nothing else consulted them, so the UI presented four
toggles that persisted a value and changed nothing. That is worse than a
missing default: an operator turning off ``log_sql`` got a UI that confirmed
the change, stored it, and kept logging SQL.

This is the "next layer" #15575's ``logging_key_parity_test.py`` names in its
own docstring: that guard catches a *published* key nothing *reads*; this one
catches a key *read only by the settings-UI builder* -- i.e. a reader that
has no behavioural effect anywhere else. It re-derives readers at test time
rather than hardcoding a list, the same way the sibling guard does:

* "read outside the settings-UI builder" = every literal
  ``"logging.<dotted.path>"`` string passed to a ``get(`` / ``get_nested(``
  call anywhere under ``autobot-backend`` / ``autobot_shared``, in a file
  other than ``services/config_service.py`` (excluding tests).
* A key with such a reader is presumed wired (its effect gets its own
  behavioural test elsewhere, e.g. ``user_management/database_log_sql_test.py``
  for ``logging.log_sql``).
* A key with no such reader must be explicitly registered in
  ``_DISPLAY_ONLY_LOGGING_KEYS`` below, with the reason wiring it was
  reported instead of done. That keeps a bare "config_service.py is the only
  reader" from ever silently persisting -- it either shows up as a real
  second reader, or it has a name and a paper trail.
"""

import os
import re
import sys
from typing import Dict, Set

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autobot_shared.paths import project_root  # noqa: E402

# Toggles kept on the settings UI (per #15587 scope: never remove a control)
# whose config key is read only by services/config_service.py's UI builder.
# Each entry names why wiring it was reported instead of connected.
_DISPLAY_ONLY_LOGGING_KEYS = {
    "logging.console": (
        "#12506 made LoggingManager's console handler unconditional on "
        "purpose (systemd captures stdout/stderr in production; the "
        "console handler is production infra, not a dev-only extra). "
        "Wiring this toggle back would reverse that decision, not connect "
        "two existing things."
    ),
    "logging.log_requests": (
        "The only existing mechanism is uvicorn's built-in access log. "
        "main.py's access_log=True fires only in the standalone `python "
        "main.py` path; production launches via `uvicorn main:app "
        "--log-config <static json>` (autobot_shared/stream_logging.py), "
        "generated once at deploy time and never re-read per request. "
        "Gating it for real needs a new dynamic filter -- new machinery, "
        "not a connection."
    ),
    "logging.max_file_size": (
        "Duplicate of logging.rotation.max_bytes -- same concept (log "
        "rotation size), different unit/namespace (MB vs bytes). "
        "logging_manager.py already reads rotation.max_bytes, but only via "
        "a flat ConfigManager.get() call, which never resolves a dotted "
        "key (config/sync_ops.py's get() does `self._config.get(key, "
        "default)`, no dotted traversal) -- so the mechanism this would "
        "connect to is itself inert today. See the #15587 report."
    ),
}

_EXCLUDED_DIR_NAMES = {"code_analysis", "code_intelligence"}
_UI_BUILDER_MODULE = "autobot-backend/services/config_service.py"

_READ_KEY_PATTERN = re.compile(r"""get(?:_nested)?\(\s*(["'])logging((?:\.[A-Za-z_][A-Za-z0-9_]*)+)\1""")


def _logging_read_sites() -> Dict[str, Set[str]]:
    """Map each read "logging.<path>" key to the set of files that read it."""
    sites: Dict[str, Set[str]] = {}
    for scan_root in ("autobot-backend", "autobot_shared"):
        for path in (project_root() / scan_root).rglob("*.py"):
            if path.name.endswith("_test.py") or _EXCLUDED_DIR_NAMES & set(path.parts):
                continue
            text = path.read_text(encoding="utf-8")
            rel_path = str(path.relative_to(project_root()))
            for match in _READ_KEY_PATTERN.finditer(text):
                key = "logging" + match.group(2)
                sites.setdefault(key, set()).add(rel_path)
    return sites


def test_every_settings_ui_logging_key_has_an_effect_or_is_registered_display_only():
    """Catches #15587's shape: a reader (the UI builder) with no effect anywhere else."""
    read_sites = _logging_read_sites()

    for key in ("logging.console", "logging.log_requests", "logging.log_sql", "logging.max_file_size"):
        readers = read_sites.get(key, set())
        other_readers = readers - {_UI_BUILDER_MODULE}

        if key in _DISPLAY_ONLY_LOGGING_KEYS:
            continue

        assert other_readers, (
            f"{key} is read only by {_UI_BUILDER_MODULE} (readers found: {sorted(readers)}). "
            "It has no behavioural effect anywhere in the tree. Either wire it to real "
            "behaviour, or register it in _DISPLAY_ONLY_LOGGING_KEYS with a reason."
        )


def test_display_only_registry_stays_honest_display_only():
    """A display-only entry that gains a real second reader must be un-registered.

    Mirrors #15575's ``test_exempt_optional_read_keys_still_have_no_publisher``:
    keeps this file from silently drifting once someone actually wires a key.
    """
    read_sites = _logging_read_sites()

    for key in _DISPLAY_ONLY_LOGGING_KEYS:
        other_readers = read_sites.get(key, set()) - {_UI_BUILDER_MODULE}
        assert not other_readers, (
            f"{key} is registered display-only but now has a real reader outside "
            f"{_UI_BUILDER_MODULE}: {sorted(other_readers)}. Remove it from "
            "_DISPLAY_ONLY_LOGGING_KEYS -- it is wired now."
        )


def test_log_sql_is_the_one_key_actually_wired_by_this_issue():
    """Pins the concrete #15587 fix: log_sql now has a real second reader
    (user_management/database.py's SQLAlchemy echo gate)."""
    read_sites = _logging_read_sites()
    other_readers = read_sites.get("logging.log_sql", set()) - {_UI_BUILDER_MODULE}

    assert "autobot-backend/user_management/database.py" in other_readers
