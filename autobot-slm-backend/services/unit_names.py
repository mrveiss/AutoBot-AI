# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Validation of the values that reach a remote ``systemctl`` / ``journalctl`` command line (#18359).

Stdlib only, so both the restart executor (``service_restart``) and the journal fetch
(``journal_fetch``) can import it without pulling the ORM in. Every value is validated here AND
``shlex.quote``d by the builder: a refusal is the user-facing answer, the quoting is the backstop.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping

logger = logging.getLogger(__name__)

# Longest slice of an untrusted name a log line may carry (#19005).
_LOGGED_NAME_MAX = 80

# systemd.unit(5): a unit name is ASCII letters, digits and ``: - _ . \ @``; at most 255
# bytes. Chosen here: ``\`` (escaped instance names) is refused -- no SLM caller needs it --
# the first character may not be ``-`` (it would read as an option), and the dotted suffix
# is not enforced because ``systemctl`` itself resolves a bare name to ``<name>.service``.
# Everything outside the set (``; $ ` ( ) | & < > space / newline quotes``) is refused.
UNIT_NAME_MAX_LENGTH = 255
_UNIT_NAME_RE = re.compile(r"^[A-Za-z0-9:_.@][A-Za-z0-9:_.@\-]*$")

# The ``--since`` forms the SLM accepts: an ISO date or date-time, a relative span such as
# ``1h`` / ``-30min`` / ``2 d ago``, or one of journalctl's keywords. Nothing else.
_SINCE_RE = re.compile(
    r"(?:\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?"
    r"|-?\d{1,6}\s?(?:s|sec|m|min|h|hr|d|w)(?: ago)?"
    r"|now|today|yesterday)",
    re.ASCII,  # `\d` / `\s` match only ASCII: Arabic-Indic digits and U+2003 are not journalctl input (#18352)
)


def validate_unit_name(unit: str) -> str:
    """Return *unit* if it is a valid systemd unit name, else raise ValueError (#18359).

    ``fullmatch`` is used, not ``$``: a ``$`` anchor would let a trailing newline through.
    """
    if not isinstance(unit, str) or not unit or len(unit) > UNIT_NAME_MAX_LENGTH or not _UNIT_NAME_RE.fullmatch(unit):
        raise ValueError(f"invalid systemd unit name: {unit!r}")
    return unit


def validate_journal_since(since: str) -> str:
    """Return *since* if it is an accepted ``journalctl --since`` value, else raise ValueError (#18359)."""
    if not isinstance(since, str) or not _SINCE_RE.fullmatch(since):
        raise ValueError(f"invalid journalctl --since value: {since!r}")
    return since


def discovered_unit_name_ok(node_id: str, name: object) -> bool:
    """True if a heartbeat/scan-discovered service *name* may be stored; else warn and say False (#19005).

    The name is node-controlled input that later reaches ``manage-service.yml`` as an extra var,
    so one that is not a unit name is dropped at ingest. The log line carries the ``repr`` of a
    length-capped slice, never the raw value (no newline/ANSI forging, no unbounded line).
    """
    try:
        validate_unit_name(name)  # type: ignore[arg-type]
    except ValueError:
        logger.warning(
            "dropping discovered service with an invalid unit name node=%s name=%s",
            node_id,
            repr(name)[:_LOGGED_NAME_MAX],
        )
        return False
    return True


# Extra-var keys whose value is handed to a service module as a unit name: ``manage-service.yml``
# (service_name), ``remove-role.yml`` (systemd_service, from the admin-set Role row) and
# ``deploy-certificate.yml`` (reload_service). Found by reading every execute_playbook caller's keys.
UNIT_NAME_EXTRA_VAR_KEYS = frozenset({"service_name", "systemd_service", "reload_service"})


def validate_unit_extra_vars(extra_vars: Mapping[str, object] | None) -> None:
    """Raise ValueError if a unit-bearing key of *extra_vars* is not a unit name (#19005).

    Called by ``PlaybookExecutor.execute_playbook`` before anything is spawned, so every
    caller is covered, not only the ones that remembered to validate.
    """
    for key in UNIT_NAME_EXTRA_VAR_KEYS & set(extra_vars or ()):
        validate_unit_name(extra_vars[key])  # type: ignore[index,arg-type]
