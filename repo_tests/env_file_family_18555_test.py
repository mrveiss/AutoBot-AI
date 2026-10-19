# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""One env-file family, one format per host key (#18555).

The repo root carried a second Docker env file, `.env.docker`, beside the
canonical `docker/.env.docker` every doc and CI job passes to compose. The fork
had drifted: its `AUTOBOT_OLLAMA_HOST=http://ollama:11434` is a URL where
compose expects a host, so `http://${AUTOBOT_OLLAMA_HOST}:11434` became
`http://http://ollama:11434:11434` (and the service is `autobot-ollama`).

The format rule (docs/developer/ENV_VARS.md, "Env-file family"):
  * `*_HOST` is a bare host name or IP -- no scheme, no port, no path;
  * `*_URL` / `*_ENDPOINT` carry the scheme;
  * `OLLAMA_HOST` is Ollama's own variable, documented upstream as host[:port].
"""

from __future__ import annotations

import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOT = repo_root()
_CANONICAL_DOCKER_ENV = "docker/.env.docker"
#: Keys whose owner is not AutoBot and whose documented format differs.
_UPSTREAM_KEYS = frozenset({"OLLAMA_HOST"})
_LINE = re.compile(r"^\s*(?:#\s*)?([A-Z][A-Z0-9_]*)=(.*)$")


_ROOTS = (".env", "autobot-frontend/", "autobot-slm-backend/", "docker/")


def _population(root: Path) -> list[str]:
    """Every tracked env file -- `.env*` or `*.env` by name."""
    try:
        paths = tracked_paths(root, "*.env*")
    except EmptyEnumeration:
        return []
    return [p for p in paths if (n := p.rsplit("/", 1)[-1]).startswith(".env") or n.endswith(".env")]


REACH = declare(
    "env-file-family-18555-scan",
    discover=_population,
    # Mid-window from REACH.window(): population 8, window (4, 8) -> 6.
    floor=6,
    growth=4,
    what="tracked env files",
    roots=_ROOTS,
)


def _env_files() -> dict[str, str]:
    return {p: (_ROOT / p).read_text(encoding="utf-8") for p in REACH.examined(_ROOT)}


def _value(raw: str) -> str:
    return re.sub(r"\s+#.*$", "", raw.strip()).strip("\"'")


def _shape(key: str, value: str) -> str | None:
    """The format class of a host-ish value, or None when there is nothing to judge."""
    if not value or value.startswith("${") or value.startswith("YOUR_") or key in _UPSTREAM_KEYS:
        return None
    if key.endswith("_HOST"):
        return "url" if "://" in value else "host:port" if re.search(r":\d+$", value) else "host"
    if key.endswith(("_URL", "_ENDPOINT")):
        return "url" if re.match(r"^[a-z][a-z0-9+.-]*://", value) else "not-a-url"
    return None


def format_violations(files: dict[str, str]) -> list[str]:
    """Every host key off the rule, and every key whose format differs between files."""
    shapes: dict[str, dict[str, str]] = {}
    for path, text in files.items():
        for line in text.splitlines():
            m = _LINE.match(line)
            shape = m and _shape(m.group(1), _value(m.group(2)))
            if shape:
                shapes.setdefault(m.group(1), {})[path] = shape
    wrong = [
        f"{p}: {k} is {s}"
        for k, by in shapes.items()
        for p, s in by.items()
        if s not in ("host", "url") or (s == "url" and k.endswith("_HOST"))
    ]
    split = [f"{k} disagrees: {by}" for k, by in shapes.items() if len(set(by.values())) > 1]
    return sorted(wrong) + sorted(split)


def docker_env_forks(paths: list[str]) -> list[str]:
    """Any Docker env file other than the canonical one."""
    return sorted(p for p in paths if "docker" in p.rsplit("/", 1)[-1] and p != _CANONICAL_DOCKER_ENV)


def test_the_family_is_read() -> None:
    files = _env_files()
    assert _CANONICAL_DOCKER_ENV in files and ".env.example" in files, sorted(files)


def test_every_host_key_follows_one_format() -> None:
    assert not format_violations(_env_files())


def test_there_is_one_docker_env_file() -> None:
    assert not docker_env_forks(list(_env_files()))


#: The fork as it stood on main before #18555, reduced to the lines that matter.
_REINTRODUCED = "AUTOBOT_LLM_PROVIDER=ollama\nAUTOBOT_OLLAMA_HOST=http://ollama:11434\n"


def test_the_guards_fail_on_a_reintroduced_fork() -> None:
    files = dict(_env_files())
    files[".env.docker"] = _REINTRODUCED
    found = format_violations(files)
    assert ".env.docker: AUTOBOT_OLLAMA_HOST is url" in found
    assert any(f.startswith("AUTOBOT_OLLAMA_HOST disagrees") for f in found)
    assert docker_env_forks(list(files)) == [".env.docker"]


def test_a_host_with_a_port_and_a_url_without_a_scheme_are_caught() -> None:
    found = format_violations({"a/.env": "AUTOBOT_REDIS_HOST=redis:6379\nAUTOBOT_REDIS_URL=redis-host:6379\n"})
    assert found == ["a/.env: AUTOBOT_REDIS_HOST is host:port", "a/.env: AUTOBOT_REDIS_URL is not-a-url"]


def test_the_canonical_docker_file_exists() -> None:
    assert Path(_ROOT / _CANONICAL_DOCKER_ENV).is_file()
