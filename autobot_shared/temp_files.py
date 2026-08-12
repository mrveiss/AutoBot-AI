# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Temporary-file helpers with guaranteed cleanup.

Issue #13208: several capture paths created a temp file with
``tempfile.NamedTemporaryFile(delete=False)`` so an external process (scrot,
import, ffmpeg, ...) could write to the path, then unlinked it *only on the
success path*. Every failure return leaked one file, permanently.

``delete=False`` is required whenever another process must open the path by
name, so the fix is not "stop using delete=False" but "make the unlink
unconditional". This module provides the single place that guarantee lives, so
new capture paths do not have to re-derive it.
"""

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


@contextmanager
def temporary_file_path(
    suffix: str = "",
    prefix: str = "autobot_",
    directory: Optional[str] = None,
) -> Iterator[str]:
    """Yield the path of a closed, empty temp file, removed on every exit path.

    The file exists and is empty when the block starts, and its descriptor is
    already closed, so an external process may write to the path by name. The
    file is removed when the block exits, whether it returned, raised, or was
    cancelled.

    Args:
        suffix: File suffix, e.g. ``".png"``.
        prefix: File name prefix.
        directory: Parent directory; the system temp dir when omitted.

    Yields:
        Absolute path to the temporary file.
    """
    fd, path = tempfile.mkstemp(suffix=suffix, prefix=prefix, dir=directory)
    os.close(fd)
    try:
        yield path
    finally:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError as exc:
            # Never let cleanup mask the caller's own outcome.
            logger.warning("Failed to remove temporary file %s: %s", path, exc)
