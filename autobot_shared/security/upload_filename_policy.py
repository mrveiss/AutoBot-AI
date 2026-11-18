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

#19088: every ``UploadFile`` route gates its filename here. The name rules are
one set; only the *allow-list of types* is per purpose (documents, audio,
images, ZIP, tarball), each defined once below. Lives in ``autobot_shared`` so
the SLM backend, which cannot import ``autobot-backend``, uses the same gate.
``autobot-backend/security/upload_filename_policy.py`` re-exports it.
"""

import unicodedata
from pathlib import Path
from typing import Iterable

from autobot_shared.ssot_constants import SecurityConstants

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

#: Audio containers (the SSOT capability set, #13512/#13615).
AUDIO_EXTENSIONS = frozenset(SecurityConstants.ALLOWED_AUDIO_EXTENSIONS)

#: Raster images a vision model can take (the chat vision picker offers webp).
IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"})

#: A plugin or theme package.
ZIP_EXTENSIONS = frozenset({".zip"})

#: A role code package (compound suffix, so matched on the name's end).
TARBALL_EXTENSIONS = frozenset({".tar.gz", ".tgz"})

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


def is_safe_file(filename: str, allowed: Iterable[str] | None = None) -> bool:
    """True when *filename* is a bare, allowed, non-deceptive upload name.

    *allowed* is the route's extension allow-list (one of the sets above);
    omitted, it is the general document list ``ALLOWED_EXTENSIONS``.

    The rules run on the name as given AND on its NFKC form, so a fullwidth
    solidus (U+FF0F), a division slash (U+2215) or fullwidth dots that fold to
    ``/`` or ``..`` are refused like the ASCII ones (#18704).
    """
    if not filename:
        return False
    allow = ALLOWED_EXTENSIONS if allowed is None else frozenset(allowed)
    return _passes(filename, allow) and _passes(unicodedata.normalize("NFKC", filename), allow)


def require_safe_upload(filename: str | None, allowed: Iterable[str] | None = None) -> str:
    """Return *filename* when it passes ``is_safe_file``, else raise HTTP 400.

    The one call every ``UploadFile`` route makes before it persists or
    processes the upload (#19088). The detail names no path or type list.
    """
    if not filename or not is_safe_file(filename, allowed):
        from fastapi import HTTPException  # noqa: PLC0415 -- keep the policy importable without fastapi

        raise HTTPException(status_code=400, detail="Upload file name or type is not allowed")
    return filename


def _passes(name: str, allowed: frozenset[str]) -> bool:
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
    lowered = name.lower()
    extension = Path(name).suffix.lower()
    # Deny first: an executable type added to the allow-list by mistake stays refused.
    if extension in _DANGEROUS_EXTENSIONS:
        return False
    # endswith so a compound entry (".tar.gz") matches; a bare ".py" is no name.
    return any(lowered.endswith(ext) and len(lowered) > len(ext) for ext in allowed)
