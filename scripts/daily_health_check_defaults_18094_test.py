# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#18094: daily_health_check takes its service URL defaults from ssot_config."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import daily_health_check  # noqa: E402

from autobot_shared.ssot_config import config as ssot_config  # noqa: E402

_IPV4 = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")


def test_source_has_no_literal_ip():
    source = Path(daily_health_check.__file__).read_text(encoding="utf-8")

    assert _IPV4.findall(source) == []


def test_default_urls_come_from_ssot_config(monkeypatch):
    for name in ("AUTOBOT_BACKEND_URL", "CHROMADB_URL", "SLM_URL"):
        monkeypatch.delenv(name, raising=False)

    check = daily_health_check.HealthCheck()

    assert check.backend_url == ssot_config.backend_url
    assert check.slm_url == ssot_config.slm_url
    assert check.chromadb_url == f"http://{ssot_config.vm.chromadb}:{ssot_config.port.chromadb}"


def test_explicit_env_still_wins(monkeypatch):
    monkeypatch.setenv("AUTOBOT_BACKEND_URL", "http://backend.example:1")
    monkeypatch.setenv("CHROMADB_URL", "http://chroma.example:2")

    check = daily_health_check.HealthCheck()

    assert check.backend_url == "http://backend.example:1"
    assert check.chromadb_url == "http://chroma.example:2"
