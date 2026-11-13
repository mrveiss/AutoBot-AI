# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Every Python service unit must be given AUTOBOT_LOGS_DIR (#20894).

Unset, `autobot_shared.log_dir.resolve_logs_dir` falls back to `$XDG_STATE_HOME/autobot/logs`, so a unit
that does not set it moves its logs on the next deploy. A Python service is a systemd unit template whose
`ExecStart=` runs python, uvicorn or celery (every such service reaches the resolver through
`logging_manager` / `ssot_config`). It passes when the unit itself, or an env template beside it, sets the
variable.
"""

from __future__ import annotations

import posixpath
import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests.python_filter_covers_its_guards_test import _filter_patterns, _is_covered

from tools.lint._scan_helpers import tracked_paths

_ROOT = repo_root()
_VAR = "AUTOBOT_LOGS_DIR"
_PYTHON_EXEC = re.compile(r"^ExecStart=.*(python|uvicorn|celery)", re.MULTILINE)
_SET = re.compile(rf"^(Environment=\"?)?{_VAR}=", re.MULTILINE)
_VALUE = re.compile(rf"^(?:Environment=)?\"?{_VAR}=([^\"\n]*)", re.MULTILINE)
_ENVFILE = re.compile(r"^EnvironmentFile=(.+)$", re.MULTILINE)
_STRICT = re.compile(r"^ProtectSystem=strict\s*$", re.MULTILINE)
_TOKEN = re.compile(r"(?:\{\{.*?\}\}|\S)+")  # one path; a `{{ jinja }}` expression holds spaces
_RWP = re.compile(r"^ReadWritePaths=(.+)$", re.MULTILINE)
_LOGS_DIRECTORY = re.compile(r"^LogsDirectory=(.+)$", re.MULTILINE)
_STATE_DIRECTORY = re.compile(r"^StateDirectory=(.+)$", re.MULTILINE)
# Concrete template directories (not root-relative `*.service` sweeps) so the python filter in
# .github/filters/python-paths.yml names every tree this guard reads; a unit outside them fails
# `test_narrowed_dirs_find_every_unit_the_whole_tree_sweep_finds` instead of going un-run.
_UNIT_DIRS = (
    "autobot-slm-backend/ansible/roles/*/templates",
    "autobot-slm-backend/ansible/templates/systemd",
    "autobot-infrastructure/*/templates",
    "scripts/systemd",
)
_UNIT_SUFFIXES = (".service", ".service.j2")
_ENV_SUFFIXES = (".env", ".env.j2")
_MIN_PYTHON_UNITS = 15  # live count when written: 15; a drop below this means discovery broke


def _python_units(root: Path) -> list[str]:
    units = tracked_paths(root, *(f"{d}/*{suffix}" for d in _UNIT_DIRS for suffix in _UNIT_SUFFIXES))
    return sorted(p for p in units if _PYTHON_EXEC.search((root / p).read_text(encoding="utf-8")))


def _norm(value: str) -> str:
    """A path as written in a unit or a task: quotes and the optional leading `-` (ignore-missing) dropped."""
    return value.strip().strip("\"'").lstrip("-").strip()


def _tasks_files(root: Path, env: str) -> list[str]:
    """The role's task files, which say where an env template is deployed to (empty outside a role)."""
    tasks = (root / env).parent.parent / "tasks"
    return sorted(str(p.relative_to(root)) for p in tasks.glob("*.yml")) if tasks.is_dir() else []


def _env_dests(root: Path, env: str) -> set[str]:
    """Every `dest:` the role's tasks give the env template (the `src:` line is followed by its `dest:`)."""
    dests: set[str] = set()
    for task_file in _tasks_files(root, env):
        lines = (root / task_file).read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if "src:" not in line or _norm(line.partition("src:")[2]) != Path(env).name:
                continue
            for follow in lines[i + 1 : i + 7]:
                if follow.strip().startswith("dest:"):
                    dests.add(_norm(follow.partition("dest:")[2]))
    return dests


def _env_beside(root: Path, unit: str) -> list[str]:
    """Env templates beside the unit that the unit really loads: an `EnvironmentFile=` names where one deploys."""
    loaded = {_norm(m) for m in _ENVFILE.findall((root / unit).read_text(encoding="utf-8"))}
    templates = (root / unit).parent
    beside = [str(p.relative_to(root)) for p in templates.iterdir() if p.name.endswith(_ENV_SUFFIXES)]
    return sorted(e for e in beside if _env_dests(root, e) & loaded)


def _unset(root: Path, units: list[str]) -> list[str]:
    """Units that neither set the variable themselves nor load an env template beside them that does."""
    missing: list[str] = []
    for unit in units:
        files = [unit, *_env_beside(root, unit)]
        if not any(_SET.search((root / f).read_text(encoding="utf-8")) for f in files):
            missing.append(unit)
    return missing


def _writable_roots(text: str) -> list[str]:
    """Paths a `ProtectSystem=strict` unit may write: ReadWritePaths= tokens, LogsDirectory=, StateDirectory=."""
    roots = [_norm(tok).lstrip("+") for line in _RWP.findall(text) for tok in _TOKEN.findall(line)]
    roots += [f"/var/log/{n}" for line in _LOGS_DIRECTORY.findall(text) for n in line.split()]
    roots += [f"/var/lib/{n}" for line in _STATE_DIRECTORY.findall(text) for n in line.split()]
    return [r.rstrip("/") for r in roots]


def _unwritable(root: Path, units: list[str]) -> list[str]:
    """Units whose configured log directory a `ProtectSystem=strict` sandbox leaves read-only."""
    bad: list[str] = []
    for unit in units:
        text = (root / unit).read_text(encoding="utf-8")
        if not _STRICT.search(text):
            continue
        roots = _writable_roots(text)
        for f in [unit, *_env_beside(root, unit)]:
            for value in _VALUE.findall((root / f).read_text(encoding="utf-8")):
                if not any(value.strip() == r or value.strip().startswith(r + "/") for r in roots):
                    bad.append(f"{unit} -> {value.strip()}")
    return bad


_OUTPUT = re.compile(r"^Standard(?:Output|Error)=(?:append|file|truncate):(\S+)", re.MULTILINE)
_DEFAULT = re.compile(r"^(\w+):\s*(.+?)\s*(?:\s#.*)?$", re.MULTILINE)
_JINJA = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


def _role_defaults(root: Path, unit: str) -> dict[str, str]:
    """The `name: value` lines of the unit's role defaults (empty outside a role); `autobot.base_dir` is `<base>`."""
    path = (root / unit).parent.parent / "defaults" / "main.yml"
    found = {"autobot.base_dir": "<base>"}
    if path.is_file():
        found.update({k: v.strip("\"'") for k, v in _DEFAULT.findall(path.read_text(encoding="utf-8"))})
    return found


def _resolve(value: str, defaults: dict[str, str]) -> str:
    """Substitute `{{ name }}` from the role defaults until nothing more resolves (a cycle stops at the cap)."""
    for _ in range(8):
        value = _JINJA.sub(lambda m: defaults.get(m.group(1), m.group(0)), value)
    return value.strip().rstrip("/")


def _colliding(root: Path, units: list[str]) -> list[str]:
    """Units whose systemd-appended output directory is the directory `AUTOBOT_LOGS_DIR` resolves to.

    systemd appends `<name>.log` there while the application's rotating handler writes `<name>.log` too: the
    records duplicate, and after a rotation systemd's descriptor follows the renamed file.
    """
    bad: list[str] = []
    for unit in units:
        defaults = _role_defaults(root, unit)
        text = (root / unit).read_text(encoding="utf-8")
        out = {_resolve(posixpath.dirname(t), defaults) for t in _OUTPUT.findall(text)}
        for f in [unit, *_env_beside(root, unit)]:
            apps = {_resolve(v, defaults) for v in _VALUE.findall((root / f).read_text(encoding="utf-8"))}
            bad += [f"{unit} -> {d}" for d in sorted(apps & out)]
    return bad


def test_application_log_dir_differs_from_the_units_service_output_dir() -> None:
    bad = _colliding(_ROOT, _python_units(_ROOT))
    assert not bad, f"{_VAR} equals the dir the unit's StandardOutput=/StandardError= append: writes to: {bad}"


def test_control_a_shared_output_and_application_dir_is_caught(tmp_path: Path) -> None:
    """Control: the same directory (also via a role default) is reported; a distinct application dir is not."""
    unit, role = "roles/r/templates/svc.service.j2", tmp_path / "roles" / "r"
    (role / "defaults").mkdir(parents=True)
    (role / "defaults" / "main.yml").write_text(
        'out_dir: /var/log/x\napp_dir: "{{ out_dir }}"\nother_dir: "{{ autobot.base_dir }}/logs"\n', encoding="utf-8"
    )
    out = "StandardOutput=append:{{ out_dir }}/svc.log\n"
    _unit(role / "templates", out + f'Environment="{_VAR}={{{{ app_dir }}}}"\n')
    assert _colliding(tmp_path, [unit]) == [f"{unit} -> /var/log/x"]
    _unit(role / "templates", out + f'Environment="{_VAR}={{{{ other_dir }}}}"\n')
    assert _colliding(tmp_path, [unit]) == []


def test_every_python_service_unit_sets_the_log_dir() -> None:
    units = _python_units(_ROOT)
    assert len(units) >= _MIN_PYTHON_UNITS, f"discovery found only {len(units)} python units"
    missing = _unset(_ROOT, units)
    assert not missing, f"unit(s) leave {_VAR} unset, so their logs move to the XDG state dir: {missing}"


def _swept_files(root: Path) -> list[str]:
    """Every unit and env template the sweep reads: the discovered units plus the env templates beside them."""
    files = set(_python_units(root))
    envs = {e for u in list(files) for e in _env_beside(root, u)}
    files |= envs | {t for e in envs for t in _tasks_files(root, e)}
    return sorted(files)


def test_every_swept_file_is_under_the_python_filter() -> None:
    """The guard runs only when the python filter fires, so every file it reads must match a filter pattern.

    A new template directory, or a unit moved out of the listed ones, fails here rather than silently
    leaving the guard un-run when that tree changes. Replaces recording this test as uncovered debt.
    """
    patterns = _filter_patterns()
    outside = [f for f in _swept_files(_ROOT) if not _is_covered(f, patterns)]
    assert not outside, f"swept file(s) outside .github/filters/python-paths.yml `python`: {outside}"


def test_narrowed_dirs_find_every_unit_the_whole_tree_sweep_finds() -> None:
    """Count equality: discovery over the concrete dirs equals the old root-relative whole-tree sweep (15)."""
    everywhere = sorted(
        p
        for p in tracked_paths(_ROOT, *(f"*{suffix}" for suffix in _UNIT_SUFFIXES))
        if ("/templates/" in p or p.startswith("scripts/systemd"))
        and _PYTHON_EXEC.search((_ROOT / p).read_text(encoding="utf-8"))
    )
    narrowed = _python_units(_ROOT)
    assert narrowed == everywhere, f"missed by the narrowed dirs: {sorted(set(everywhere) - set(narrowed))}"
    assert len(narrowed) >= _MIN_PYTHON_UNITS


def test_control_an_uncovered_dir_is_reported() -> None:
    """Control: a unit in a directory no pattern names is flagged, one in a named directory is not."""
    patterns = _filter_patterns()
    # A plain `.service`: the filter's `**/*.j2` (#20884) covers every `.j2` anywhere, so only a non-`.j2` path
    # can sit in a directory no pattern names.
    assert not _is_covered("some/new/dir/svc.service", patterns)
    assert _is_covered("autobot-slm-backend/ansible/roles/redis/templates/svc.service.j2", patterns)


def test_control_a_unit_without_the_variable_is_caught(tmp_path: Path) -> None:
    """Control: the detector reports a unit that omits the variable and passes one that sets it."""
    bad = tmp_path / "roles" / "bad" / "templates"
    bad.mkdir(parents=True)
    (bad.parent / "tasks").mkdir()
    (bad.parent / "tasks" / "main.yml").write_text(
        "- template:\n    src: svc.env.j2\n    dest: /etc/svc.env\n", encoding="utf-8"
    )
    (bad / "svc.service.j2").write_text(
        "[Service]\nExecStart=/x/venv/bin/uvicorn main:app\nEnvironmentFile=/etc/svc.env\n", encoding="utf-8"
    )
    (bad / "svc.env.j2").write_text("REDIS_HOST=h\n", encoding="utf-8")
    assert _unset(tmp_path, ["roles/bad/templates/svc.service.j2"]) == ["roles/bad/templates/svc.service.j2"]
    (bad / "svc.env.j2").write_text("REDIS_HOST=h\nAUTOBOT_LOGS_DIR={{ d }}\n", encoding="utf-8")
    assert _unset(tmp_path, ["roles/bad/templates/svc.service.j2"]) == []
    (bad / "svc.env.j2").write_text("REDIS_HOST=h\n", encoding="utf-8")
    (bad / "svc.service.j2").write_text(
        '[Service]\nEnvironment="AUTOBOT_LOGS_DIR={{ d }}"\nExecStart=/x/python m\n', encoding="utf-8"
    )
    assert _unset(tmp_path, ["roles/bad/templates/svc.service.j2"]) == []


def test_every_configured_log_dir_is_writable_under_the_units_sandbox() -> None:
    """`ProtectSystem=strict` makes every path read-only but ReadWritePaths/LogsDirectory/StateDirectory."""
    bad = _unwritable(_ROOT, _python_units(_ROOT))
    assert not bad, f"{_VAR} points where the unit's sandbox forbids writing: {bad}"


def _unit(directory: Path, body: str, env_file: str = "") -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "svc.service.j2").write_text(
        f"[Service]\nExecStart=/x/uvicorn m:a\n{env_file}{body}", encoding="utf-8"
    )


def test_control_a_read_only_log_dir_is_caught(tmp_path: Path) -> None:
    """Control: strict sandboxing with the dir outside every writable path is reported; each grant clears it."""
    unit = "t/svc.service.j2"
    body = f"Environment={_VAR}=/opt/x/logs\nProtectSystem=strict\n"
    _unit(tmp_path / "t", body + "ReadWritePaths=/opt/x/data\n")
    assert _unwritable(tmp_path, [unit]) == [f"{unit} -> /opt/x/logs"]
    for grant in ("ReadWritePaths=/opt/x/logs\n", "ReadWritePaths=/opt/x\n", "ReadWritePaths=-/opt/x/logs\n"):
        _unit(tmp_path / "t", body + grant)
        assert _unwritable(tmp_path, [unit]) == [], grant
    _unit(tmp_path / "t", f"Environment={_VAR}=/var/log/autobot\nProtectSystem=strict\nLogsDirectory=autobot\n")
    assert _unwritable(tmp_path, [unit]) == []
    _unit(tmp_path / "t", f"Environment={_VAR}=/opt/x/logs\n")  # no sandbox: nothing to forbid
    assert _unwritable(tmp_path, [unit]) == []


def test_control_a_sibling_env_template_the_unit_never_loads_does_not_count(tmp_path: Path) -> None:
    """Control: a beside-env that sets the variable satisfies the unit only if an EnvironmentFile= names its dest."""
    role = tmp_path / "roles" / "r"
    (role / "tasks").mkdir(parents=True)
    (role / "tasks" / "main.yml").write_text(
        "- template:\n    src: svc.env.j2\n    dest: /etc/autobot/svc.env\n", encoding="utf-8"
    )
    (role / "templates").mkdir()
    (role / "templates" / "svc.env.j2").write_text("AUTOBOT_LOGS_DIR=/l\n", encoding="utf-8")
    unit = "roles/r/templates/svc.service.j2"
    _unit(role / "templates", "")
    assert _unset(tmp_path, [unit]) == [unit]  # sibling sets it, but the unit never loads it
    _unit(role / "templates", "", env_file="EnvironmentFile=-/etc/autobot/other.env\n")
    assert _unset(tmp_path, [unit]) == [unit]
    _unit(role / "templates", "", env_file="EnvironmentFile=-/etc/autobot/svc.env\n")
    assert _unset(tmp_path, [unit]) == []


_COMPOSE_SETTING = re.compile(rf"^\s*-\s*{_VAR}=(.*)$", re.MULTILINE)
_COMPOSE_OVERRIDABLE = re.compile(rf"^\$\{{{_VAR}:-[^}}]+\}}$")


def _fixed_compose_settings(text: str) -> list[str]:
    """`AUTOBOT_LOGS_DIR=` values in a compose file that ignore an operator-supplied value."""
    return [v for v in _COMPOSE_SETTING.findall(text) if not _COMPOSE_OVERRIDABLE.match(v.strip())]


def test_compose_services_let_the_operator_override_the_log_dir() -> None:
    text = (_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert _COMPOSE_SETTING.search(text), "docker-compose.yml no longer sets the variable: discovery broke"
    assert not _fixed_compose_settings(text), f"literal {_VAR} ignores the operator's value; use ${{{_VAR}:-/app/logs}}"


def test_control_a_literal_compose_value_is_caught() -> None:
    assert _fixed_compose_settings(f"    environment:\n      - {_VAR}=/app/logs\n") == ["/app/logs"]
    assert _fixed_compose_settings(f"      - {_VAR}=${{{_VAR}:-/app/logs}}\n") == []
