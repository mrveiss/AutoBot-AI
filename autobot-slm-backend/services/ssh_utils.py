# Copyright 2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Canonical ssh-key usability gate (#11793).

``Path(SSH_KEY_PATH).exists()`` propagates ``PermissionError`` when the key's
parent directory is unreadable (EACCES is not in pathlib's ignored-errno set),
so every ssh command build crashed with an unhandled exception instead of
degrading.  ``_ssh_key_usable`` is the one safe gate: it returns ``True`` only
when the key is confirmed readable and fails closed (``False`` -> no ``-i``
flag, ssh uses its default identity) on ANY doubt, logging an actionable
WARNING once per path instead of crashing.
"""

import ipaddress
import logging
import os
import re
from pathlib import Path
from typing import Annotated

from pydantic import AfterValidator

logger = logging.getLogger(__name__)

# Paths already warned about — warn once per path per process so a persistent
# permissions misconfiguration degrades with a single actionable line instead
# of replacing crash spam with log spam (#11793).
_WARNED_PATHS: set = set()


def _warn_once(path: str, detail: str) -> None:
    """Log the not-usable WARNING for *path* at most once per process."""
    if path in _WARNED_PATHS:
        return
    _WARNED_PATHS.add(path)
    logger.warning(
        "SSH key %s is not usable (%s); falling back to default ssh identity",
        path,
        detail,
    )


# --- The one validator for an ssh destination (#18366) -----------------------------------------
# A node row's ssh_user / ip_address go into the local ssh argv. A value starting with '-' is
# parsed by OpenSSH as an OPTION (``-oProxyCommand=<cmd>`` runs <cmd> on the SLM host before any
# connection is made), so every destination is validated here and preceded by ``--``.
_SSH_USER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,31}")  # POSIX portable name, never a leading '-'
_HOSTNAME_LABEL_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")  # RFC 1123 label
_HOSTNAME_MAX_LEN = 253


class InvalidSshDestination(ValueError):
    """The ssh user or host is not safe to place in an ssh argv."""


def validate_ssh_user(user: object) -> str:
    """Return *user* when it is a POSIX user name; raise ``InvalidSshDestination`` otherwise."""
    if isinstance(user, str) and _SSH_USER_RE.fullmatch(user):
        return user
    raise InvalidSshDestination("ssh user must be a POSIX user name (letters, digits, '_', '.', '-'; no leading '-')")


def validate_ssh_host(host: object) -> str:
    """Return *host* when it is an IP address or an RFC 1123 hostname; raise otherwise."""
    if isinstance(host, str) and host:
        try:
            ipaddress.ip_address(host)
            return host
        except ValueError:
            pass
        labels = host.split(".")
        if len(host) <= _HOSTNAME_MAX_LEN and all(_HOSTNAME_LABEL_RE.fullmatch(label) for label in labels):
            return host
    raise InvalidSshDestination("ssh host must be an IP address or a hostname (no leading '-', whitespace or '@')")


def validate_ssh_password(password: object) -> object:
    """Return *password* when it encodes as UTF-8; raise otherwise (#18613).

    A lone surrogate (e.g. U+D83D) would be written to the enrollment vars file as an escape
    Ansible's YAML loader rejects, failing the run late with an opaque scanner error.
    """
    if isinstance(password, str):
        try:
            password.encode("utf-8")
        except UnicodeEncodeError:
            raise InvalidSshDestination("ssh password must be valid UTF-8 (it contains a lone surrogate character)")
    return password


def ssh_destination(user: object, host: object) -> str:
    """The validated ``user@host`` ssh destination; the one place that string is built."""
    return f"{validate_ssh_user(user)}@{validate_ssh_host(host)}"


def ssh_destination_args(user: object, host: object) -> list[str]:
    """``["--", "user@host"]``: the validated destination, after the end-of-options marker.

    ssh, scp and rsync all read ``--`` as "no more options"; every direct-exec argv splices this in
    where the destination goes so a value that slipped past validation still cannot be an option.
    """
    return ["--", ssh_destination(user, host)]


def ssh_options(*options: str) -> list[str]:
    """``["-o", opt, "-o", opt, ...]``: one ``-o`` per ssh option."""
    return [part for option in options for part in ("-o", option)]


def ssh_remote_path(user: object, host: object, path: str) -> str:
    """``user@host:path``, the scp/rsync remote operand, with the same validated destination."""
    return f"{ssh_destination(user, host)}:{path}"


# Pydantic field types: the node create/update/test-connection schemas reject a bad value with 422.
SshUser = Annotated[str, AfterValidator(validate_ssh_user)]
SshHost = Annotated[str, AfterValidator(validate_ssh_host)]
SshPassword = Annotated[str, AfterValidator(validate_ssh_password)]


def build_ssh_base_cmd(host: str, user: str, port: int, key) -> list:
    """Build the canonical ssh base argv shared by every direct-exec caller.

    Single source of truth for ``api/nodes.py`` (``_build_node_ssh_cmd``) and
    ``services/sync_orchestrator.py`` (``_build_ssh_command``), which had
    drifted into two near-identical builders (#12690, round-2 of #12645):
    the orchestrator's copy was missing ``-o ConnectTimeout=10``, so a
    role-sync against an unreachable node could hang indefinitely instead of
    failing fast. Both call sites now build this argv and append their own
    trailing command / positional args.

    Returns ``["ssh", "-o", "StrictHostKeyChecking=accept-new", "-o",
    "ConnectTimeout=10", "-p", str(port), ["-i", key] if usable, "--", "user@host"]``.
    Raises ``InvalidSshDestination`` before any process is spawned (#18366).
    """
    cmd = [
        "ssh",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ConnectTimeout=10",
        "-p",
        str(port),
    ]
    if _ssh_key_usable(key):
        cmd.extend(["-i", os.fspath(key)])
    cmd.extend(["--", ssh_destination(user, host)])
    return cmd


def _ssh_key_usable(key_path) -> bool:
    """Return True only when *key_path* is confirmed readable.

    Fail-closed replacement for the inline ``Path(KEY).exists()`` gates:

    - missing key -> ``False``, quiet (matches the old behavior);
    - unreadable key, or any ``OSError`` while checking (e.g. EACCES on the
      key's parent directory) -> ``False`` plus a single WARNING per path.

    ``False`` means the caller builds its ssh/rsync command WITHOUT ``-i`` and
    ssh falls back to the default identity — never an unhandled
    ``PermissionError`` (#11793).
    """
    path = os.fspath(key_path)
    try:
        if not Path(path).exists():
            return False
        if os.access(path, os.R_OK):
            return True
    except OSError as exc:  # PermissionError included — EACCES on parent dir
        _warn_once(path, f"errno {exc.errno}: {exc.strerror or exc}")
        return False
    _warn_once(path, "exists but is not readable by the SLM process")
    return False
