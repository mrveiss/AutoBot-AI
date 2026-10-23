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


# --- one base plus overlays (owner decision 2026-10-19, #18555 AC1) ---

_BASE = ".env.base"
_OVERLAYS = (".env.localhost", ".env.native-vm", ".env.network", ".env.network-template")
_ASSIGNMENT = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")


def _pairs(text: str) -> dict[str, str]:
    return {m[1]: m[2] for line in text.splitlines() if (m := _ASSIGNMENT.match(line.strip()))}


def redundant_overlay_keys(base: str, overlays: dict[str, str]) -> list[str]:
    """`<overlay>: KEY` for every key an overlay sets to exactly the base value."""
    shared = _pairs(base)
    return sorted(
        f"{name}: {k}" for name, text in overlays.items() for k, v in _pairs(text).items() if shared.get(k) == v
    )


def test_overlays_hold_only_what_differs_from_the_base() -> None:
    files = _env_files()
    assert _BASE in files and set(_OVERLAYS) <= set(files), sorted(files)
    assert _pairs(files[_BASE]), ".env.base sets no key"
    redundant = redundant_overlay_keys(files[_BASE], {n: files[n] for n in _OVERLAYS})
    assert not redundant, f"an overlay repeats a base key with the same value -- delete it there: {redundant}"


#: Root env files that are not native overlays, each for a stated reason.
_NOT_OVERLAYS = {
    _BASE: "the base the overlays build on",
    ".env.example": "the annotated reference for a native install -- every option, not an environment",
}


def unknown_native_env_files(paths: list[str]) -> list[str]:
    """Root .env.<env> files that are neither a known overlay nor a stated exception."""
    return sorted(p for p in paths if "/" not in p and p not in _NOT_OVERLAYS and p not in _OVERLAYS)


def test_every_native_env_file_is_a_known_overlay() -> None:
    """A new root .env.<env> must join the family deliberately, not drift beside it. The paths come
    from REACH.examined (`_env_files`), so the env-file-family-18555-scan floor covers this sweep."""
    files = list(_env_files())
    assert set(_OVERLAYS) <= set(files)
    assert not unknown_native_env_files(files)


def test_the_overlay_check_catches_a_stray_env_file() -> None:
    assert unknown_native_env_files([".env.base", ".env.localhost", ".env.staging", "docker/.env.docker"]) == [
        ".env.staging"
    ]


def test_the_redundancy_check_sees_a_repeat_and_allows_an_override() -> None:
    base = "AUTOBOT_BACKEND_PORT=8001\nAUTOBOT_REDIS_HOST=\n"
    overlays = {".env.x": "AUTOBOT_BACKEND_PORT=8001\nAUTOBOT_REDIS_HOST=127.0.0.1\n"}
    assert redundant_overlay_keys(base, overlays) == [".env.x: AUTOBOT_BACKEND_PORT"]


def _script(name: str):
    import importlib.util

    path = _ROOT / "autobot-infrastructure" / "shared" / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.replace("-", "_").removesuffix(".py"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_validator_checks_base_plus_overlay(tmp_path: Path) -> None:
    """27's review: validate-env-files.py read each overlay alone and reported the base keys missing."""
    validator = _script("validate-env-files.py")
    (tmp_path / ".env.base").write_text("AUTOBOT_BACKEND_PORT=8001\nAUTOBOT_REDIS_HOST=\n", encoding="utf-8")
    (tmp_path / ".env.localhost").write_text("AUTOBOT_REDIS_HOST=127.0.0.1\n", encoding="utf-8")
    assert validator.effective_env_vars(tmp_path / ".env.localhost") == {
        "AUTOBOT_BACKEND_PORT": "8001",
        "AUTOBOT_REDIS_HOST": "127.0.0.1",
    }
    (tmp_path / ".env").write_text("X=1\n", encoding="utf-8")
    assert validator.effective_env_vars(tmp_path / ".env") == {"X": "1"}, "a non-overlay file took the base"


def test_the_generator_writes_overlay_only_output() -> None:
    """27's review: a regenerated overlay must not repeat the base and trip the guard."""
    generator = _script("generate-env-files.py")
    base = "AUTOBOT_BACKEND_PORT=8001\nREDIS_PORT=6379\n"
    content = "# header\nAUTOBOT_BACKEND_PORT=8001\nREDIS_PORT=6380\nAUTOBOT_X=1\n"
    assert generator.strip_base_keys(content, base) == "# header\nREDIS_PORT=6380\nAUTOBOT_X=1\n"
