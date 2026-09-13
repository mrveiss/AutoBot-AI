# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15577 guard: install.sh must resolve Redis's database from the named SSOT
key, not the retired ``AUTOBOT_REDIS_DB``.

``AUTOBOT_REDIS_DB`` was replaced repo-wide by the named ``AUTOBOT_REDIS_DB_*``
keys in #2813/#2922 and is set nowhere (not ``.env.example``, not the ansible
group_vars), so a script that still reads it always falls through to its
literal default instead of the configured database. ``install.sh`` was the
last reader left; this guard keeps it from creeping back in and keeps the
replacement (``AUTOBOT_REDIS_DB_MAIN``, which matches what
``code_analyzer.py`` and its siblings actually use via
``get_async_redis_client()``'s "main" default) present.
"""

from __future__ import annotations

import re
from pathlib import Path

_INSTALL_SH = Path(__file__).resolve().parent / "install.sh"

# Matches the retired bare name but not the surviving `_MAIN` (or any other
# named) suffix -- `AUTOBOT_REDIS_DB` followed by a non-identifier character.
_RETIRED_VAR = re.compile(r"AUTOBOT_REDIS_DB(?![A-Z_])")
_REPLACEMENT_VAR = "AUTOBOT_REDIS_DB_MAIN"


def test_install_sh_does_not_read_the_retired_redis_db_var():
    text = _INSTALL_SH.read_text(encoding="utf-8")
    matches = _RETIRED_VAR.findall(text)
    assert not matches, f"install.sh still reads the retired AUTOBOT_REDIS_DB: {matches}"


def test_install_sh_reads_the_named_main_redis_db_key():
    text = _INSTALL_SH.read_text(encoding="utf-8")
    assert text.count(_REPLACEMENT_VAR) >= 2, (
        f"install.sh should resolve both its .env template and its self-test " f"from {_REPLACEMENT_VAR}"
    )
