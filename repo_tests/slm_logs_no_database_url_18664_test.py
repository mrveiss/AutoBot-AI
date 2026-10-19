# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No SLM log call prints a database URL unredacted (#18664).

The migration runner logged ``postgresql://autobot:<password>@...`` at INFO on every
start; an external Docker test saw it 14 times, and 14 migrations did the same in their
own ``migrate`` / ``__main__``. Every log call that passes a database URL must pass it
through ``redact_url_credentials`` (autobot_shared/secret_redaction.py).

**What this does not cover.** It matches the variable names the SLM uses for database
URLs (db_url, database_url, dsn) in logger calls; a URL logged under another name, or
interpolated earlier into a message string, is not seen.
"""

from __future__ import annotations

import re

from repo_tests._paths import repo_root

from tools.lint._scan_helpers import tracked_paths

_ROOT = repo_root()
_URL_IN_LOG = re.compile(r"(?:(?:logger|logging|log)\.\w+|print)\((?P<args>.*\b(?:db_url|database_url|dsn)\b.*)\)")


def test_no_slm_log_call_passes_a_database_url_unredacted() -> None:
    files = tracked_paths(_ROOT, "autobot-slm-backend/*.py")
    assert len(files) > 200, f"read {len(files)} SLM files -- the scan is broken"
    leaks = []
    for rel in files:
        if rel.endswith("_test.py") or "/tests/" in rel:
            continue
        for n, line in enumerate((_ROOT / rel).read_text(encoding="utf-8").splitlines(), 1):
            m = _URL_IN_LOG.search(line)
            if m and "redact_url_credentials(" not in m.group("args") and '.split("@")' not in m.group("args"):
                leaks.append(f"{rel}:{n}: {line.strip()}")
    assert not leaks, "log calls print a database URL without redact_url_credentials:\n" + "\n".join(leaks)


def test_the_guard_sees_an_unredacted_call() -> None:
    assert _URL_IN_LOG.search('logger.info(f"Running migrations on PostgreSQL: {db_url}")')
    assert _URL_IN_LOG.search('logger.info("Migrating database: %s", db_url)')
    assert _URL_IN_LOG.search('logging.warning("db %s", database_url)')
    assert _URL_IN_LOG.search('print(f"using {dsn}")')
