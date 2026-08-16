# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Prometheus must scrape ports the services actually bind (#14315).

The `autobot-backend` job targeted `:8443` over https — the nginx TLS front —
and nothing listens there. Measured on a live host:

    autobot-backend  down  dial tcp <host>:8443: connect: connection refused

So Prometheus has never collected a single backend series, and #13765's cgroup
alerting has never had data to evaluate. The rules load, the collector runs, the
metric is computed — and the target was never up.

The endpoint was never the problem. On the uvicorn port it answers 200 and
exports 120 `autobot_cgroup_memory` series across 8 units, chromadb included.

A literal port in a scrape config is a second source of truth for something the
service already declares. These assert it stays derived.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

_TEMPLATE = Path(__file__).resolve().parents[2] / "ansible" / "roles" / "monitoring" / "templates" / "prometheus.yml.j2"


def _job(name: str) -> str:
    """The raw text block for one scrape job."""
    text = _TEMPLATE.read_text(encoding="utf-8")
    start = text.index(f'- job_name: "{name}"')
    nxt = text.find("- job_name:", start + 1)
    return text[start : nxt if nxt != -1 else len(text)]


def test_the_template_still_defines_the_backend_job():
    """Guard the guard: a rename makes every assertion below vacuous."""
    assert '- job_name: "autobot-backend"' in _TEMPLATE.read_text(encoding="utf-8")


def test_the_backend_target_derives_its_port():
    """A literal is a second source of truth for something the backend role
    already declares (`backend_port: 8001 # uvicorn: plain HTTP port`), and it
    drifted to a port nothing listens on."""
    job = _job("autobot-backend")
    assert "backend_port" in job, "the backend scrape target hardcodes a port instead of deriving it"
    assert ":8443" not in job, (
        "the backend job targets 8443 — the nginx TLS front, where nothing listens. "
        "Prometheus reported `connection refused` and collected no backend series at all (#14315)"
    )


def test_the_backend_job_scrapes_the_uvicorn_port_over_http():
    """The slm-backend job above it already documents this distinction: plain
    http on the uvicorn port, not the TLS front. The backend job did the
    opposite."""
    job = _job("autobot-backend")
    scheme = re.search(r"^\s*scheme:\s*(\S+)", job, re.MULTILINE)
    assert (
        scheme and scheme.group(1) == "http"
    ), f"backend job scheme is {scheme.group(1) if scheme else 'unset'} — the uvicorn port serves plain http"


@pytest.mark.parametrize("job_name", ["autobot-backend", "slm", "slm-backend"])
def test_no_scrape_job_targets_a_tls_front_port(job_name: str):
    """8443 is nginx. Every job here scrapes an application directly."""
    assert ":8443" not in _job(job_name), f"{job_name} scrapes the TLS front rather than the app"


def test_the_rendered_config_is_valid_yaml():
    """Prometheus refuses its ENTIRE configuration if any part is malformed, so
    a broken scrape block silently removes every alert too."""
    text = _TEMPLATE.read_text(encoding="utf-8")
    rendered = re.sub(r"\{%.*?%\}", "", text, flags=re.DOTALL)
    rendered = re.sub(r"\{\{.*?\}\}", "PLACEHOLDER", rendered, flags=re.DOTALL)
    parsed = yaml.safe_load(rendered)
    assert "scrape_configs" in parsed
    names = {j.get("job_name") for j in parsed["scrape_configs"]}
    assert "autobot-backend" in names
