# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Environment, deployment mode and debug: one home, every copy pinned (#19315, #19316).

``autobot_shared/deployment_profile.py`` holds the defaults and the profile table. Two sweeps keep
it the only home:

* **code copies** -- a literal fallback for one of ``PROFILE_VARS`` in Python: a two-argument
  ``os.getenv``/``os.environ.get`` with a non-empty fallback (``""`` means "unset"), a ``Field(default=<literal>, alias=...)`` or an
  ``EnvVarSpec(name=..., default=<literal>)``. Each is a second default, so the count must be 0.
* **profile writers** -- every tracked file that assigns one of the variables (``KEY=value``,
  ``KEY: value``, compose ``- KEY=value``, Dockerfile ``ENV KEY=value``). Each file is declared in
  :data:`PROFILE_CARRIERS` with the profile(s) it carries, and each value must equal that profile's
  value in ``PROFILES``. An undeclared writer, a value off its profile, or any write of the legacy
  ``AUTOBOT_ENV`` fails.

The contrast tests rebuild a re-added copy of each kind and require the sweep to flag it.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from autobot_shared import deployment_profile as profile
from autobot_shared.paths import scrubbed_git_env

_ROOT = repo_root()

#: Tracked paths never swept: prose, timing data and tests (which set the variables on purpose).
_EXCLUDE = ("docs", "*.md", ".test_durations", "*_test.py", "test_*.py", "*/tests/*", "repo_tests")

#: file -> the profile(s) it carries. Shrink-only: an entry whose file writes none of the variables
#: is reported. ``generate-env-files.py`` emits several profiles (broken pending #18565).
PROFILE_CARRIERS: dict[str, tuple[str, ...]] = {
    ".env.example": ("development",),
    "docker-compose.override.example.yml": ("development",),
    ".env.localhost": ("dev-localhost",),
    ".env.native-vm": ("dev-native-vm",),
    "autobot-slm-backend/ansible/roles/backend/templates/backend.env.j2": ("fleet",),
    "docker-compose.yml": ("single-host",),
    "docker/backend/Dockerfile": ("single-host",),
    "docker/slm/Dockerfile": ("single-host",),
    "autobot-infrastructure/shared/scripts/install-bare-metal.sh": ("single-host",),
    "autobot-infrastructure/shared/scripts/generate-env-files.py": (
        "development",
        "dev-localhost",
        "dev-native-vm",
        "single-host",
    ),
    "autobot-infrastructure/shared/config/deployment/distributed.yml": ("distributed",),
    "autobot-infrastructure/shared/config/deployment/kubernetes.yml": ("kubernetes",),
    "autobot-infrastructure/shared/config/deployment/local.yml": ("local",),
    "autobot-infrastructure/shared/scripts/deployment/deploy_hybrid.sh": ("hybrid",),
    "autobot-infrastructure/shared/scripts/distributed/start-coordinator.sh": ("distributed",),
    "autobot-slm-backend/ansible/deploy-autobot-native.sh": ("native",),
    "autobot-slm-backend/ansible/deploy-hybrid.sh": ("hybrid",),
    "autobot-slm-backend/ansible/deploy-native.sh": ("native",),
    "autobot-slm-backend/ansible/inventory/group_vars/backend.yml": ("ansible-backend",),
    "autobot-slm-backend/ansible/roles/distributed_setup/tasks/config.yml": ("distributed",),
    "autobot-slm-backend/ansible/roles/distributed_setup/templates/distributed.env.j2": ("distributed",),
}

_VAR_ALT = "|".join(sorted(profile.PROFILE_VARS, key=len, reverse=True))
#: A line that assigns one of the variables a literal value. A templated value (``${...}``,
#: ``{expr}``) captures as empty and is not a literal copy.
_WRITE = re.compile(
    r"""^\s*(?:-\s*|ENV\s+|export\s+|line:\s*["']|["'])?(""" + _VAR_ALT + r""")["']?\s*[=:]\s*["']?([A-Za-z0-9_.-]*)"""
)


def _git(root: Path, *args: str) -> list[str]:
    spec = [f":(exclude){p}" for p in _EXCLUDE]
    cmd = ["git", *args, "--", ".", *spec]
    out = subprocess.run(cmd, cwd=root, env=scrubbed_git_env(), capture_output=True, text=True, check=False)
    return out.stdout.splitlines()


def candidate_files(root: Path) -> list[str]:
    """Tracked, non-excluded files that mention any of the variables."""
    return _git(root, "grep", "-l", "-E", _VAR_ALT)


def writes_in(path: str, text: str) -> list[tuple[str, int, str, str]]:
    """``(path, line, var, value)`` for every literal assignment in *text*."""
    out = []
    for no, line in enumerate(text.splitlines(), 1):
        m = _WRITE.match(line)
        if m and m.group(2):
            out.append((path, no, m.group(1), m.group(2)))
    return out


def profile_writes(root: Path) -> list[tuple[str, int, str, str]]:
    """Every literal assignment across the candidate files."""
    found = []
    for rel in candidate_files(root):
        found += writes_in(rel, (root / rel).read_text(encoding="utf-8", errors="replace"))
    return found


def write_findings(writes: list[tuple[str, int, str, str]]) -> list[str]:
    """Writers outside :data:`PROFILE_CARRIERS`, or off their declared profile."""
    bad = []
    for path, no, var, value in writes:
        carried = PROFILE_CARRIERS.get(path)
        if carried is None:
            bad.append(f"{path}:{no}: {var}={value} -- undeclared writer; add it to PROFILE_CARRIERS")
            continue
        allowed = {profile.PROFILES[p][var] for p in carried if var in profile.PROFILES[p]}
        if value not in allowed:
            bad.append(f"{path}:{no}: {var}={value} -- profile(s) {carried} allow {sorted(allowed)}")
    return bad


def _literal(node: ast.AST | None) -> object:
    return node.value if isinstance(node, ast.Constant) else None


def _kw(call: ast.Call, *names: str) -> object:
    return next((_literal(k.value) for k in call.keywords if k.arg in names), None)


def _is_env_read(call: ast.Call) -> bool:
    func = call.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    return name in ("getenv", "get") and len(call.args) == 2


def _copied_var(call: ast.Call) -> object:
    """The variable *call* restates a literal default for, or ``None``."""
    name = getattr(call.func, "attr", None) or getattr(call.func, "id", None)
    if _is_env_read(call) and _literal(call.args[1]) not in (None, ""):  # "" is the unset sentinel
        return _literal(call.args[0])
    if name == "Field" and _kw(call, "default") is not None:
        return _kw(call, "alias", "validation_alias")
    if name == "EnvVarSpec" and _kw(call, "default") is not None:
        return _kw(call, "name")
    return None


def code_copies_in(path: str, source: str) -> list[str]:
    """``path:line: VAR`` for every literal default of a profile variable in *source*."""
    out = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and _copied_var(node) in profile.PROFILE_VARS:
            out.append(f"{path}:{node.lineno}: {_copied_var(node)}")
    return out


def code_copies(root: Path) -> list[str]:
    """Literal-default copies across every candidate Python file."""
    found = []
    for rel in candidate_files(root):
        if rel.endswith(".py"):
            found += code_copies_in(rel, (root / rel).read_text(encoding="utf-8"))
    return found


#: The writer census, with its floor proven against the live population by the reach meta-test.
WRITES = declare(
    "deployment-profile-writers-19315",
    discover=profile_writes,
    floor=31,  # 36 live; window [26, 36], pin 31
    growth=10,
    what="literal assignments of AUTOBOT_ENVIRONMENT/ENV/DEPLOYMENT_MODE/DEBUG",
)


# --- the live tree ---------------------------------------------------------------------------


def test_every_profile_writer_carries_a_declared_profile() -> None:
    writes = WRITES.examined(_ROOT)
    assert write_findings(list(writes)) == []


def test_no_carrier_entry_is_stale() -> None:
    writers = {w[0] for w in profile_writes(_ROOT)}
    assert sorted(set(PROFILE_CARRIERS) - writers) == [], "drop the entries that no longer write a variable"


def test_no_python_file_restates_a_default() -> None:
    files = [f for f in candidate_files(_ROOT) if f.endswith(".py")]
    assert len(files) >= 5, f"the sweep reached only {files}"
    assert code_copies(_ROOT) == []


def test_every_carried_profile_exists() -> None:
    assert {p for ps in PROFILE_CARRIERS.values() for p in ps} <= set(profile.PROFILES)


# --- the home --------------------------------------------------------------------------------


def test_a_missing_value_never_means_development_or_debug() -> None:
    assert profile.DEFAULT_PROFILE == "production"
    assert profile.ENVIRONMENT_DEFAULT == "production"
    assert profile.DEBUG_DEFAULT is False
    assert profile.DEPLOYMENT_MODE_DEFAULT == "", "unset mode is auto-detect (owner ruling on #19315, #12771)"


def test_the_fleet_writes_production_explicitly() -> None:
    writes = [w for w in profile_writes(_ROOT) if PROFILE_CARRIERS.get(w[0]) == ("fleet",)]
    assert (profile.ENVIRONMENT_VAR, "production") in {(w[2], w[3]) for w in writes}


@pytest.mark.parametrize(
    ("environ", "in_container", "expected"),
    [
        ({"AUTOBOT_DEPLOYMENT_MODE": "distributed"}, False, "distributed"),
        ({}, False, "local"),
        ({}, True, "docker_local"),
        ({"AUTOBOT_DEPLOYMENT_MODE": "hybrid"}, True, "docker_local"),  # not a mode: detection decides
    ],
)
def test_one_resolver_explicit_wins_else_detects(environ: dict, in_container: bool, expected: str) -> None:
    from autobot_shared import service_registry_core as core

    with patch.dict(os.environ, environ, clear=True), patch.object(core.os.path, "exists", return_value=in_container):
        assert core.resolve_deployment_mode().value == expected


def test_ssot_fields_take_their_defaults_from_the_home() -> None:
    from autobot_shared.ssot_config import AutoBotConfig

    with patch.dict(os.environ, {}, clear=True):
        cfg = AutoBotConfig(_env_file=None)
    assert (cfg.environment, cfg.deployment_mode, cfg.debug) == (
        profile.ENVIRONMENT_DEFAULT,
        profile.DEPLOYMENT_MODE_DEFAULT,
        profile.DEBUG_DEFAULT,
    )


@pytest.mark.parametrize(
    ("environ", "expected"),
    [
        ({"AUTOBOT_ENV": "staging"}, "staging"),
        ({"AUTOBOT_ENVIRONMENT": "development", "AUTOBOT_ENV": "staging"}, "development"),
        ({}, "production"),
    ],
)
def test_autobot_env_is_an_alias_of_autobot_environment(environ: dict, expected: str) -> None:
    from autobot_shared.ssot_config import AutoBotConfig

    with patch.dict(os.environ, environ, clear=True):
        assert AutoBotConfig(_env_file=None).environment == expected
    assert profile.environment_name(environ) == expected


def test_registry_documents_the_home_defaults() -> None:
    from autobot_shared.env_registry import REGISTRY

    for var in (profile.ENVIRONMENT_VAR, profile.ENVIRONMENT_ALIAS_VAR):
        assert REGISTRY[var].default == profile.ENVIRONMENT_DEFAULT
    assert REGISTRY[profile.DEPLOYMENT_MODE_VAR].default == profile.DEPLOYMENT_MODE_DEFAULT


# --- contrast: a re-added copy is caught -------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        'import os\nX = os.getenv("AUTOBOT_ENV", "development")\n',
        'import os\nX = os.environ.get("AUTOBOT_ENVIRONMENT", "production")\n',
        'D = Field(default=True, alias="AUTOBOT_DEBUG")\n',
        'S = EnvVarSpec(name="AUTOBOT_DEPLOYMENT_MODE", type=str, default="distributed")\n',
    ],
)
def test_a_reintroduced_code_default_is_flagged(source: str) -> None:
    assert len(code_copies_in("feature.py", source)) == 1


@pytest.mark.parametrize("call", ['os.getenv("AUTOBOT_ENVIRONMENT")', 'os.environ.get("AUTOBOT_DEPLOYMENT_MODE", "")'])
def test_a_presence_read_is_not_a_copy(call: str) -> None:
    assert code_copies_in("feature.py", f"import os\nX = {call}\n") == []


@pytest.mark.parametrize(
    ("path", "text"),
    [
        ("docker-compose.yml", "    environment:\n      - AUTOBOT_ENVIRONMENT=development\n"),
        (".env.example", "AUTOBOT_DEBUG=false\n"),
        ("new-installer.sh", "AUTOBOT_ENVIRONMENT=production\n"),
        (".env.localhost", "AUTOBOT_ENV=development\n"),
    ],
)
def test_a_writer_off_its_profile_or_undeclared_is_flagged(path: str, text: str) -> None:
    writes = writes_in(path, text)
    assert len(writes) == 1 and len(write_findings(writes)) == 1


def test_a_templated_value_is_not_a_literal_write() -> None:
    assert writes_in("x.sh", 'AUTOBOT_ENVIRONMENT="${AUTOBOT_ENVIRONMENT:-$(detect)}"\n') == []


# --- one normalisation (#19315 security review) -------------------------------------------------


@pytest.mark.parametrize(
    ("environ", "expected"),
    [
        ({"AUTOBOT_ENVIRONMENT": ""}, "production"),
        ({"AUTOBOT_ENVIRONMENT": "   "}, "production"),
        ({"AUTOBOT_ENVIRONMENT": " Development "}, "development"),
        ({"AUTOBOT_ENVIRONMENT": "PRODUCTION"}, "production"),
        ({"AUTOBOT_ENVIRONMENT": "", "AUTOBOT_ENV": "Test"}, "test"),
    ],
)
def test_ssot_and_the_home_normalise_alike(environ: dict, expected: str) -> None:
    from autobot_shared.ssot_config import AutoBotConfig

    with patch.dict(os.environ, environ, clear=True):
        assert AutoBotConfig(_env_file=None).environment == expected
    assert profile.environment_name(environ) == expected


@pytest.mark.parametrize("name", ["Production", "prod", "", " production ", "garbage", "staging", None])
def test_only_the_allow_list_is_non_production(name: str | None) -> None:
    assert profile.is_non_production(name) is False


@pytest.mark.parametrize("name", ["development", "dev", "test", "ci", " CI "])
def test_the_allow_list_is_non_production(name: str) -> None:
    assert profile.is_non_production(name) is True


def test_a_conflict_and_an_unknown_value_each_warn_once(caplog: pytest.LogCaptureFixture) -> None:
    profile._warned.clear()
    with caplog.at_level("WARNING", logger=profile.__name__):
        for _ in range(3):
            profile.resolve_environment("development", "production")
            profile.resolve_environment("prdo", None)
    messages = [r.getMessage() for r in caplog.records]
    assert sum("differ; AUTOBOT_ENVIRONMENT wins" in m for m in messages) == 1
    assert sum("Unknown environment 'prdo'" in m for m in messages) == 1


def test_a_value_set_only_in_dotenv_reaches_environment_name(tmp_path: Path) -> None:
    from autobot_shared import ssot_config

    dotenv = tmp_path / ".env"
    dotenv.write_text("AUTOBOT_ENVIRONMENT=Development\n", encoding="utf-8")
    with patch.dict(os.environ, {}, clear=True):
        loaded = ssot_config.AutoBotConfig(_env_file=str(dotenv))
        with patch.object(ssot_config, "get_config", return_value=loaded):
            assert profile.environment_name() == "development"
