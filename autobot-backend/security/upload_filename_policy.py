# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one upload-filename policy, shared by every upload route (#18704).

``api/files.py`` and ``api/conversation_files.py`` each carried an
``is_safe_file``. Only the general file API refused a name with a path
component, so a conversation upload accepted ``a/b.txt``; their allow-lists
also drifted although both said they were "consistent with" the other. Owner
decision 2026-10-17: the strict rules for both, one allow-list (the union:
the general list plus ``.xls``, which conversation uploads already took).
"""

import unicodedata
from pathlib import Path

# Allowed file extensions for security
ALLOWED_EXTENSIONS = frozenset(
    {
        # Text and data formats
        ".txt",
        ".md",
        ".json",
        ".yaml",
        ".yml",
        ".xml",
        ".csv",
        ".log",
        ".cfg",
        ".ini",
        ".conf",
        # Code files
        ".py",
        ".js",
        ".ts",
        ".sh",
        ".bat",
        ".sql",
        # Web files
        ".html",
        ".css",
        # Office document formats (Microsoft)
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        # Office document formats (OpenDocument/LibreOffice)
        ".odt",  # OpenDocument Text (Writer)
        ".ods",  # OpenDocument Spreadsheet (Calc)
        ".odp",  # OpenDocument Presentation (Impress)
        ".odg",  # OpenDocument Graphics (Draw)
        # Image formats
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".svg",
        ".ico",
    }
)

# Issue #380: Module-level frozenset for dangerous filename characters
_DANGEROUS_FILENAME_CHARS = frozenset({"<", ">", '"', "|", "?", "*", "\0", "\r", "\n"})

# Issue #398: Module-level sets for is_safe_file validation
_DANGEROUS_FILENAMES = frozenset(
    {
        ".htaccess",
        ".env",
        "passwd",
        "shadow",
        "config",
        "web.config",
        "autoexec.bat",
        "boot.ini",
        "hosts",
        "httpd.conf",
        "nginx.conf",
    }
)

_DANGEROUS_EXTENSIONS = frozenset(
    {
        ".exe",
        ".cmd",
        ".com",
        ".scr",
        ".pif",
        ".vbs",
        ".jar",
        ".app",
        ".deb",
        ".rpm",
        ".dmg",
        ".pkg",
        ".msi",
    }
)


#: Slash and backslash lookalikes NFKC does NOT fold to "/" or "\\" (the
#: fullwidth forms it does fold, and the fold is checked separately): division
#: slash, fraction slash, big solidus, big reverse solidus (#18704).
_SEPARATOR_LOOKALIKES = frozenset({"\u2215", "\u2044", "\u29f8", "\u29f9"})


def is_safe_file(filename: str) -> bool:
    """True when *filename* is a bare, allowed, non-deceptive upload name.

    The rules run on the name as given AND on its NFKC form, so a fullwidth
    solidus (U+FF0F), a division slash (U+2215) or fullwidth dots that fold to
    ``/`` or ``..`` are refused like the ASCII ones (#18704).
    """
    if not filename:
        return False
    return _passes(filename) and _passes(unicodedata.normalize("NFKC", filename))


def _passes(name: str) -> bool:
    # Control and format characters: C0, DEL, C1 and the BIDI overrides that
    # let "report\u202efdp.sh" display with a fake extension (#18704).
    if any(unicodedata.category(c) in ("Cc", "Cf") for c in name):
        return False
    if any(char in name for char in _DANGEROUS_FILENAME_CHARS):
        return False
    # A bare name, never a path (#13394); backslash explicitly, because
    # Path.name is platform-dependent and "dir\\evil.py" is one POSIX component (#13162).
    if "/" in name or "\\" in name or Path(name).name != name or name in (".", ".."):
        return False
    if any(char in _SEPARATOR_LOOKALIKES for char in name):
        return False
    if len(name) > 255 or name.lower() in _DANGEROUS_FILENAMES:
        return False
    extension = Path(name).suffix.lower()
    # Deny first: an executable type added to the allow-list by mistake stays refused.
    return extension not in _DANGEROUS_EXTENSIONS and extension in ALLOWED_EXTENSIONS
