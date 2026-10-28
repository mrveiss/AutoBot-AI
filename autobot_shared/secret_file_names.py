# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""File names that hold secrets: the one list a crawler or indexer must never ingest (#19339).

A file is matched by its NAME, not its content. A stem naming a credential (``credentials.json``,
``api-token.txt``, ``db_password.conf``) is judged by the shared redaction vocabulary
(``secret_redaction.is_credential_file_stem``), and a key or env file shape (``*.pem``, ``id_rsa``,
``.env.local``) by the globs below. Stem words are split on ``-``, ``_``, ``.`` and spaces, so
``tokenizer.py`` or ``secretary.md`` is not a match.
"""

from __future__ import annotations

import fnmatch

from autobot_shared.secret_redaction import is_credential_file_stem

#: File-name shapes of keys, keystores and env files, matched case-insensitively.
SECRET_FILE_GLOBS: tuple[str, ...] = (
    "*.key", "*.pem", "*.p12", "*.pfx", "*.jks", "*.keystore", "*.kdbx",
    "id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*",
    ".env", ".env.*", "*.env", "*.env.*", ".netrc", ".pgpass", ".htpasswd",
)  # fmt: skip
#: Suffixes of plain data files, where a bare ``key`` stem is a key file rather than prose.
_KEY_DATA_SUFFIXES: frozenset[str] = frozenset({"json", "yaml", "yml", "txt", "toml", "ini", "conf", "cfg"})


def is_secret_file_name(name: str) -> bool:
    """Whether the file called *name* (a base name, not a path) looks like it holds a secret."""
    lowered = name.lower()
    if any(fnmatch.fnmatch(lowered, glob) for glob in SECRET_FILE_GLOBS):
        return True
    stem, _dot, suffix = lowered.rpartition(".") if "." in lowered.lstrip(".") else (lowered, "", "")
    return is_credential_file_stem(stem, data_file=suffix in _KEY_DATA_SUFFIXES)
