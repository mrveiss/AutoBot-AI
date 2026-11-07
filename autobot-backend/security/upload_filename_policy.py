# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Backend import path for the one upload-filename policy (#18704, #19088).

The implementation lives in ``autobot_shared.security.upload_filename_policy``
so the SLM backend can use the same gate. This module is the re-export routes
and tests in ``autobot-backend`` import; it holds no rules of its own.
"""

from autobot_shared.security.upload_filename_policy import (  # noqa: F401
    _DANGEROUS_EXTENSIONS,
    _DANGEROUS_FILENAME_CHARS,
    _DANGEROUS_FILENAMES,
    ALLOWED_EXTENSIONS,
    AUDIO_EXTENSIONS,
    IMAGE_EXTENSIONS,
    TARBALL_EXTENSIONS,
    ZIP_EXTENSIONS,
    is_safe_file,
    require_safe_upload,
)
