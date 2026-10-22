# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The redis drop-in's memory cap is something systemd accepts (Issue #19124).

`MemoryLimit={{ redis_memory_limit | upper }}` rendered "6GB". systemd takes
K/M/G/T only, logged "Invalid memory limit '6GB', ignoring" and ran redis with
no cgroup cap at all. The cap now derives from maxmemory by redis's unit rules,
with headroom (owner decision on #19124).
"""

import re

import jinja2
import pytest
import yaml
from repo_tests._paths import repo_root

_ROLE = repo_root() / "autobot-slm-backend" / "ansible" / "roles" / "redis"
_TEMPLATE = _ROLE / "templates" / "redis-stack-override.conf.j2"
_SYSTEMD_SIZE = re.compile(r"^[0-9]+[KMGT]?$")


def _render(memory_limit: str) -> dict[str, str]:
    role_vars = yaml.safe_load((_ROLE / "vars" / "main.yml").read_text(encoding="utf-8"))
    env = jinja2.Environment(undefined=jinja2.StrictUndefined, trim_blocks=True, keep_trailing_newline=True)
    text = env.from_string(_TEMPLATE.read_text(encoding="utf-8")).render(
        {**role_vars, "redis_memory_limit": memory_limit, "redis_config_file": "/etc/redis-stack.conf"}
    )
    return dict(line.split("=", 1) for line in text.splitlines() if line.startswith("Memory"))


def test_the_shipped_limit_renders_with_headroom() -> None:
    directives = _render(
        yaml.safe_load((_ROLE / "vars" / "main.yml").read_text(encoding="utf-8"))["redis_memory_limit"]
    )
    assert directives == {"MemoryHigh": "9216M", "MemoryMax": "12288M"}


@pytest.mark.parametrize(
    ("limit", "high", "max_"),
    [
        ("6gb", "9216M", "12288M"),
        ("512mb", "768M", "1024M"),
        ("2g", "2862M", "3815M"),
        ("1073741824", "1536M", "2048M"),
    ],
    ids=["gb", "mb", "g-decimal", "bare-bytes"],
)
def test_every_redis_unit_becomes_a_size_systemd_accepts(limit: str, high: str, max_: str) -> None:
    directives = _render(limit)
    assert directives == {"MemoryHigh": high, "MemoryMax": max_}
    assert all(_SYSTEMD_SIZE.match(v) for v in directives.values()), directives


def test_the_deprecated_cgroup_v1_spelling_is_gone() -> None:
    assert "MemoryLimit=" not in _TEMPLATE.read_text(encoding="utf-8")


@pytest.mark.parametrize("limit", ["6GiB", "lots", "0gb", ""], ids=["iec-suffix", "word", "zero", "empty"])
def test_an_unparseable_limit_fails_the_render(limit: str) -> None:
    with pytest.raises(jinja2.UndefinedError):
        _render(limit)
