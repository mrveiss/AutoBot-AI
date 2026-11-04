# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One encryption-at-rest core in ``autobot_shared`` (#17981).

``field_encryption`` sealed values without binding them to their record, while
``secrets_envelope`` did, so both lived in the same package and disagreed on
the property that matters. #17981 made ``field_encryption`` a facade over the
envelope core. This guard stops the next copy.

Like the #17941 stripper ratchet, it reads the syntax tree, not the text. A
module that names a cipher in a comment or docstring (``user_management/models/
mfa.py`` does) is not a cipher implementation, and neither is this file.

Scope: ``autobot_shared`` only. Cipher users in the backend, the SLM and the
infrastructure scripts are tracked on #17981's list until each moves.
"""

from __future__ import annotations

import ast
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOT = repo_root()

#: AEAD and token-cipher constructors from ``cryptography``, plus the raw ``Cipher`` primitive.
_CIPHERS = frozenset({"AESGCM", "AESCCM", "AESOCB3", "AESSIV", "ChaCha20Poly1305", "Cipher", "Fernet", "MultiFernet"})

#: The canonical core. Exempt by identity, not pending migration.
_CANONICAL = frozenset({"autobot_shared/secrets_envelope.py"})

#: Other cipher users, each with a reason it is not yet on the core. **This list
#: only shrinks**: an entry is removed when that module moves onto the envelope
#: core; nothing may be added. Each is tracked on #17981's list. Each entry
#: names the ciphers the module uses today, so a pending module cannot pick up
#: a second one while it waits.
_PENDING: dict[str, frozenset[str]] = {
    # A legacy-key adapter. It reproduces the old per-company Fernet
    # derivation byte for byte so pre-envelope data stays readable.
    "autobot_shared/legacy_secret_keys.py": frozenset({"Fernet"}),
    # Passphrase-derived AES-GCM with no AAD: the same unbound shape #17981 fixed.
    "autobot_shared/passphrase_encryption.py": frozenset({"AESGCM"}),
}


def _cipher_names(source: str) -> set[str]:
    """Cipher names a module imports or references in code (comments and strings are ignored)."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            found |= {a.name for a in node.names if a.name in _CIPHERS}
        elif isinstance(node, ast.Name) and node.id in _CIPHERS:
            found.add(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in _CIPHERS:
            found.add(node.attr)
    return found


def _source_files(root: Path) -> list[str]:
    try:
        return tracked_paths(
            root,
            "autobot_shared/*.py",
            exclude=("*_test.py", "test_*.py", "conftest.py", "autobot_shared/tests/*", "autobot_shared/*/tests/*"),
        )
    except EmptyEnumeration:
        return []


def _all_python(root: Path) -> int:
    try:
        return len(tracked_paths(root, "autobot_shared/*.py"))
    except EmptyEnumeration:
        return 0


#: Measured 2026-11-03: 342 of 546 tracked ``autobot_shared`` .py files (63%) are non-test source;
#: 0.5 leaves room for test growth before the scan is meaningfully narrower.
REACH = declare(
    "one-aead-core",
    discover=_source_files,
    reference=_all_python,
    min_fraction=0.5,
    what="non-test python source in autobot_shared",
    roots=("autobot_shared",),
)


def _population() -> set[str]:
    examined = REACH.examined(_ROOT)
    found = {p for p in examined if _cipher_names((_ROOT / p).read_text(encoding="utf-8"))}
    REACH.completed(len(examined), _ROOT)
    return found


def test_no_new_cipher_implementation_in_autobot_shared():
    population = _population()
    assert _CANONICAL <= population, "the scan no longer sees the canonical core: the instrument is broken"
    new = population - _CANONICAL - _PENDING.keys()
    assert not new, (
        f"{sorted(new)} use a cipher directly. Seal through autobot_shared.secrets_envelope "
        "(or the field_encryption facade) instead of adding a second core (#17981)."
    )


def test_each_pending_module_uses_only_its_recorded_ciphers():
    grown = {
        rel: sorted(used - allowed)
        for rel, allowed in _PENDING.items()
        if (used := _cipher_names((_ROOT / rel).read_text(encoding="utf-8"))) - allowed
    }
    assert not grown, f"pending modules picked up another cipher: {grown}. Move them onto the envelope core (#17981)."


def test_the_pending_list_names_only_current_users():
    stale = _PENDING.keys() - _population()
    assert not stale, f"{sorted(stale)} no longer use a cipher: delete them from _PENDING (the list only shrinks)"


def test_the_facade_itself_has_no_cipher():
    source = (_ROOT / "autobot_shared/field_encryption.py").read_text(encoding="utf-8")
    assert not _cipher_names(source), "field_encryption must delegate to secrets_envelope, not seal itself"


def test_the_detector_reads_code_not_prose():
    prose = '"""Uses AESGCM."""\n# Fernet here\nNOTE = "ChaCha20Poly1305"\n'
    code = "from cryptography.fernet import Fernet\nFernet(b'k')\n"
    assert _cipher_names(prose) == set()
    assert _cipher_names(code) == {"Fernet"}
    raw = "from cryptography.hazmat.primitives.ciphers import Cipher\nCipher(a, m)\n"
    assert _cipher_names(raw) == {"Cipher"}
    assert "autobot_shared/user_management/models/mfa.py" not in _population()
