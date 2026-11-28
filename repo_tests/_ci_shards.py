# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The python-suite shard count, read from ``ci.yml``'s matrix (#19527).

The matrix list is the one definition of the count: the shard jobs read it
through ``strategy.job-total``. Every guard that needs the number asks here
instead of restating it, so changing the matrix cannot leave a test balancing
or checking a split CI no longer runs.
"""

from __future__ import annotations

import yaml
from repo_tests._paths import repo_root

CI_WORKFLOW = repo_root() / ".github" / "workflows" / "ci.yml"


def ci_document() -> dict:
    """``ci.yml`` parsed."""
    return yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))


def python_shard_count() -> int:
    """How many shards the python-shard matrix actually runs."""
    jobs = ci_document()["jobs"]
    assert "python-shard" in jobs, "FIX THE SWEEP: no python-shard job in ci.yml"
    shards = jobs["python-shard"]["strategy"]["matrix"]["shard"]
    assert isinstance(shards, list) and shards, "python-shard matrix is not a non-empty list"
    return len(shards)
