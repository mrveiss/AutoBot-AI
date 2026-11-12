# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared fixtures-as-functions for the pre-board guard lane's guards (#21359).

``preboard_guard_lane_21359_test.py`` reads the workflow and the roots; the verdict guard beside it
exercises the report on synthetic shard output. Both load the lane module the same way and build
the same synthetic shards, so that lives here once.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Iterator

from repo_tests._paths import repo_root

ROOT = repo_root()
LANE_MODULE = ROOT / "pipeline-scripts" / "preboard_guard_lane.py"
BASE_SHA = "b" * 40
PROMTOOL_FILE = "repo_tests/promtool_rules_test.py"
PROMTOOL_REASON = "promtool not found at the default location, Prometheus rule BEHAVIOUR is unverified"


def load_lane() -> Iterator[Any]:
    """The lane module, loaded under a private name and removed again (it registers itself nowhere)."""
    spec = importlib.util.spec_from_file_location("preboard_guard_lane_under_test", LANE_MODULE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(spec.name, None)


def env(**over: str) -> dict[str, str]:
    needs = {"guards": {"result": "success"}, "types": {"result": "success"}}
    base = {"NEEDS_JSON": json.dumps(needs), "RUN_ID": "1", "REF": "b", "SHA": "s", "BASE_REF": "main"}
    return {**base, **over}


def case(file: str, name: str, *, child: str = "", attrs: str = "") -> str:
    module = file[:-3].replace("/", ".")
    return f'<testcase classname="{module}" name="{name}" file="{file}"{attrs}>{child}</testcase>'


def passing(file: str, count: int) -> list[str]:
    return [case(file, f"test_{i}") for i in range(count)]


def failing(file: str, name: str) -> str:
    child = '<failure message="AssertionError: too big&#10;second line">trace</failure>'
    return case(file, name, child=child)


def skipped(file: str, name: str, reason: str) -> str:
    return case(file, name, child=f'<skipped type="pytest.skip" message="{reason}">skipped</skipped>')


def shard(number: int, splits: int, rc: int | None, rows: list[str], **meta: Any) -> dict[str, Any]:
    """One shard's artifact: its meta and a junit file made of *rows*."""
    base = {
        "shard": number,
        "splits": splits,
        "rc": rc,
        "merged": True,
        "base_sha": BASE_SHA,
        "behind_base": 0,
        "floor": 1,
        "roots": ["repo_tests"],
        "required_files": [],
    }
    junit = f'<testsuites><testsuite name="x">{"".join(rows)}</testsuite></testsuites>'
    return {"meta": {**base, **meta}, "junit": junit}


def write_shards(tmp_path: Path, shards: list[dict[str, Any]]) -> Path:
    for item in shards:
        folder = tmp_path / f"preboard-shard-{item['meta']['shard']}"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "shard-meta.json").write_text(json.dumps(item["meta"]), encoding="utf-8")
        (folder / "junit.xml").write_text(item["junit"], encoding="utf-8")
    return tmp_path


def verdict(lane: Any, tmp_path: Path, shards: list[dict[str, Any]], **environment: str) -> dict[str, Any]:
    return lane.report.build_result(env(**environment), write_shards(tmp_path, shards))
