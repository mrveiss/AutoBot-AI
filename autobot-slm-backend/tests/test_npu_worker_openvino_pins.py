# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No site that installs OpenVINO via pip may contradict the SSOT (#14447, #14452, #14453, #15408).

Seven sites in the repo pin or install `openvino` and this guard reaches all seven:

1. The `npu-worker` ansible role's inline package list (#14447).
2. `deploy-native-services.yml`'s inline package list (#14452).
3. `autobot-infrastructure/.../docker/requirements-npu.txt`, tracked by dependabot (#14453).
4. `agent_config/tasks/openvino.yml`'s inline `pip:` task -- live via
   `deploy-agent-config.yml` against `slm_nodes`, `install_openvino: true` by default.
5. `inventory/group_vars/aiml.yml`'s `packages.python` list -- confirmed **dormant**:
   `deploy-aiml.yml` reads neither `packages` nor `openvino` from this file, so it is
   also excluded from the constraints-applied check below (there is no pip task or
   `-c` convention in this file for any package, openvino or otherwise). Left in place
   per the never-delete-code rule rather than removed; fixed so it reproduces nothing
   the moment something does read it.
6. `autobot-npu-worker/resources/windows-npu-worker/requirements.txt` -- a live build
   path per its `BUILDING.md`.
7. `autobot-backend/code_analysis/` -- a standalone tool with its own `setup.py`
   (documented as such in `pyproject.toml`'s mypy exclusion, GH#7105), not part of the
   ansible-orchestrated fleet deploy. Its `src/` modules are imported live by the running
   backend via `PYTHONPATH` (`api/anti_pattern.py`, `code_intelligence/*`, etc.), but that
   import path never touches `setup.py`. `setup.py`'s `extras_require["npu"]` and
   `install.sh`'s `--npu` pip line are still real, documented, human/CI-runnable install
   paths in their own right -- this guard reads both. `README.md`'s matching instruction
   is prose rather than a parseable spec, and was once excluded for that reason; it drifted
   while unguarded (#15415) and is now covered by the documentation scan at the end of this
   file, along with every other live document that pins openvino.

Most of these drifted the same way: `openvino-dev` -- a deprecated meta-package frozen
at 2024.6.0 with no release compatible with openvino 2026.x -- installed alongside a
floor below the SSOT's, or (sites 4, 7) no floor at all. pip backtracks through old
`openvino-dev` versions pinning numpy lower until it reaches a numpy with no cp314
wheel, and the sdist build dies on `setuptools.build_meta` -- an error naming the build
backend and nothing about which requirement caused it. Site 7 never paired with
`openvino-dev`, so it does not reproduce that exact crash, but it did contradict the
SSOT floor -- the invariant this guard exists to hold everywhere `openvino` is pinned.

#15408: parity used to be asserted after the fact -- every one of the seven restated the
floor as a literal, so a dependabot bump of *one* left the other six wrong until someone
hand-edited them. `constraints/shared.txt` is now the single literal (matching the numpy
line already there, #10524): sites 1-4 and 6 declare a bare `openvino` and apply it via
`-c constraints/shared.txt` -- pip resolves the constraint, no literal to restate. Site 5
is dormant with no pip mechanism to attach a `-c` to, so it stays bare with no floor at
all (nothing to drift). Site 7's `setup.py` half stays a literal -- it is parsed with
`ast.parse` (never executed) rather than executed, so it cannot itself read a file at
build time the way `install.sh`'s shell line can -- so it is still checked against the
SSOT rather than deriving it; `install.sh`'s own pip line derives via the same bare + `-c`
pattern as the ansible sites. The floor is read out of `constraints/shared.txt` rather than
hardcoded here. Every site factory reads its source file with an uncaught
`Path.read_text()` -- a renamed or moved file raises `FileNotFoundError` and errors the
test rather than silently guarding nothing.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_ROLE_TASKS = _REPO_ROOT / "autobot-slm-backend" / "ansible" / "roles" / "npu-worker" / "tasks" / "main.yml"
_PLAYBOOK = _REPO_ROOT / "autobot-slm-backend" / "ansible" / "playbooks" / "deploy-native-services.yml"
_DOCKER_REQUIREMENTS = _REPO_ROOT / "autobot-infrastructure" / "autobot-npu-worker" / "docker" / "requirements-npu.txt"
_AGENT_CONFIG_TASKS = (
    _REPO_ROOT / "autobot-slm-backend" / "ansible" / "roles" / "agent_config" / "tasks" / "openvino.yml"
)
_AIML_GROUP_VARS = _REPO_ROOT / "autobot-slm-backend" / "ansible" / "inventory" / "group_vars" / "aiml.yml"
_WINDOWS_REQUIREMENTS = _REPO_ROOT / "autobot-npu-worker" / "resources" / "windows-npu-worker" / "requirements.txt"
_CODE_ANALYSIS_SETUP = _REPO_ROOT / "autobot-backend" / "code_analysis" / "setup.py"
_CODE_ANALYSIS_INSTALL_SH = _REPO_ROOT / "autobot-backend" / "code_analysis" / "install.sh"
# #15408: the SSOT moved from autobot-npu-worker/requirements.txt (a literal restated in
# six other places) to constraints/shared.txt (already the SSOT for numpy, #10524).
_SSOT_CONSTRAINTS = _REPO_ROOT / "constraints" / "shared.txt"

_ROLE_TASK_NAME = "Install OpenVINO and dependencies"
_PLAYBOOK_TASK_NAME = "Install OpenVINO runtime for NPU Worker"
_AGENT_CONFIG_TASK_NAME = "Set up OpenVINO environment in venv"


@dataclass(frozen=True)
class _Site:
    """One place in the repo that installs or pins OpenVINO independently of the SSOT."""

    label: str
    packages: list


def _normalize_names(value) -> list:
    """Ansible's `pip: name:` accepts a scalar string or a list -- always return a list."""
    if isinstance(value, str):
        return [value]
    return list(value)


def _bare_name(spec: str) -> str:
    """Strip extras/markers/version specifiers, leaving the distribution name."""
    return re.split(r"[<>=\[]", spec)[0].strip()


def _version_tuple(spec: str) -> tuple:
    return tuple(int(part) for part in re.findall(r"\d+", spec)[:3])


def _pip_task_from_task_list(tasks: list, task_name: str, module_key: str) -> dict:
    for task in tasks or []:
        if isinstance(task, dict) and task.get("name") == task_name:
            return task[module_key]
    raise AssertionError(f"no task named {task_name!r} — this guard is pinned to the wrong name")


def _extra_args_of(task: dict) -> str:
    return " ".join(str(task.get("extra_args", "")).split())


def _role_site() -> _Site:
    tasks = yaml.safe_load(_ROLE_TASKS.read_text(encoding="utf-8"))
    task = _pip_task_from_task_list(tasks, _ROLE_TASK_NAME, "ansible.builtin.pip")
    return _Site(label=f"npu-worker role ({_ROLE_TASKS.name})", packages=_normalize_names(task["name"]))


def _playbook_site() -> _Site:
    plays = yaml.safe_load(_PLAYBOOK.read_text(encoding="utf-8"))
    task = None
    for play in plays or []:
        try:
            task = _pip_task_from_task_list((play or {}).get("tasks", []), _PLAYBOOK_TASK_NAME, "pip")
            break
        except AssertionError:
            continue
    assert (
        task is not None
    ), f"no task named {_PLAYBOOK_TASK_NAME!r} in any play — this guard is pinned to the wrong name"
    return _Site(label=f"deploy-native-services.yml ({_PLAYBOOK.name})", packages=_normalize_names(task["name"]))


def _agent_config_site() -> _Site:
    tasks = yaml.safe_load(_AGENT_CONFIG_TASKS.read_text(encoding="utf-8"))
    task = _pip_task_from_task_list(tasks, _AGENT_CONFIG_TASK_NAME, "pip")
    return _Site(label=f"agent_config role ({_AGENT_CONFIG_TASKS.name})", packages=_normalize_names(task["name"]))


def _parse_requirements_file(path: Path) -> list:
    """Package spec lines from a pip requirements file, comments and `-c`/`-e` stripped."""
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    package_lines = [
        line.split("#", 1)[0].strip()
        for line in lines
        if line and not line.startswith("#") and not line.startswith("-c") and not line.startswith("-e")
    ]
    return [line for line in package_lines if line]


def _docker_requirements_site() -> _Site:
    return _Site(
        label=f"requirements-npu.txt ({_DOCKER_REQUIREMENTS.name})",
        packages=_parse_requirements_file(_DOCKER_REQUIREMENTS),
    )


def _windows_requirements_site() -> _Site:
    return _Site(
        label=f"windows-npu-worker requirements.txt ({_WINDOWS_REQUIREMENTS.name})",
        packages=_parse_requirements_file(_WINDOWS_REQUIREMENTS),
    )


def _aiml_site() -> _Site:
    """Dormant: `deploy-aiml.yml` reads neither `packages` nor `openvino` from this file."""
    data = yaml.safe_load(_AIML_GROUP_VARS.read_text(encoding="utf-8"))
    packages = data["packages"]["python"]
    return _Site(label=f"aiml group_vars, dormant ({_AIML_GROUP_VARS.name})", packages=list(packages))


def _setup_py_npu_extras() -> list:
    """`extras_require["npu"]` from code_analysis/setup.py, parsed with `ast` -- never executed."""
    tree = ast.parse(_CODE_ANALYSIS_SETUP.read_text(encoding="utf-8"), filename=str(_CODE_ANALYSIS_SETUP))
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "setup"):
            continue
        for kw in node.keywords:
            if kw.arg != "extras_require" or not isinstance(kw.value, ast.Dict):
                continue
            for key_node, value_node in zip(kw.value.keys, kw.value.values):
                if isinstance(key_node, ast.Constant) and key_node.value == "npu" and isinstance(value_node, ast.List):
                    return [elt.value for elt in value_node.elts if isinstance(elt, ast.Constant)]
    raise AssertionError(
        f"no extras_require['npu'] list found in {_CODE_ANALYSIS_SETUP.name} "
        "— this guard is pinned to the wrong shape"
    )


def _install_sh_npu_pip_line() -> str:
    """The `pip install ... openvino ...` line inside install.sh's `--npu` branch."""
    for line in _CODE_ANALYSIS_INSTALL_SH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("pip install") and "openvino" in stripped:
            return stripped
    raise AssertionError(
        f"no `pip install ... openvino ...` line found in {_CODE_ANALYSIS_INSTALL_SH.name} "
        "— this guard is pinned to the wrong line"
    )


def _install_sh_npu_packages() -> list:
    line = _install_sh_npu_pip_line()
    tokens = line.split()[2:]  # drop "pip install"
    packages = []
    skip_next = False
    for tok in tokens:
        if skip_next:
            skip_next = False
            continue
        if tok == "-c":
            skip_next = True
            continue
        if tok.startswith("-"):
            continue
        packages.append(tok.strip("\"'"))
    return packages


def _code_analysis_site() -> _Site:
    packages = _setup_py_npu_extras() + _install_sh_npu_packages()
    return _Site(label="code_analysis (setup.py extras_require['npu'] + install.sh --npu)", packages=packages)


_SITES: dict = {
    "role": _role_site,
    "playbook": _playbook_site,
    "requirements-npu.txt": _docker_requirements_site,
    "agent_config": _agent_config_site,
    "aiml (dormant)": _aiml_site,
    "windows-npu-worker": _windows_requirements_site,
    "code_analysis": _code_analysis_site,
}

# Sites where a constraints file can even be applied -- i.e. an actual pip
# invocation (a `pip:` task's `extra_args`, a requirements file's own `-c`
# line, or install.sh's pip line). `aiml.yml` is a bare version-string list
# with no pip task and no `-c` convention for *any* package in that file,
# openvino included -- there is nowhere in the file to put a constraints
# reference. If it is ever wired up, the constraints flag belongs at the call
# site that reads it, not here. `code_analysis`'s `setup.py` half has the same
# limitation (`extras_require` is a dependency list, not a pip invocation, so
# it cannot itself carry `-c`) -- but `install.sh`'s pip line can and does, so
# the site as a whole is not exempt.
_CONSTRAINTS_EXEMPT = {"aiml (dormant)"}
assert _CONSTRAINTS_EXEMPT <= _SITES.keys(), "an exemption names a site that no longer exists"

_PIP_TASK_SITES: dict = {
    "role": (_ROLE_TASKS, _ROLE_TASK_NAME, "ansible.builtin.pip"),
    "playbook": (_PLAYBOOK, _PLAYBOOK_TASK_NAME, "pip"),
    "agent_config": (_AGENT_CONFIG_TASKS, _AGENT_CONFIG_TASK_NAME, "pip"),
}
_REQUIREMENTS_FILE_SITES: dict = {
    "requirements-npu.txt": _DOCKER_REQUIREMENTS,
    "windows-npu-worker": _WINDOWS_REQUIREMENTS,
}


def _extra_args_for(site_name: str) -> str:
    """Constraints-bearing text for a site: a pip task's `extra_args`, a requirements
    file's `-c` line(s), or (for `code_analysis`) install.sh's pip line."""
    if site_name in _PIP_TASK_SITES:
        path, task_name, module_key = _PIP_TASK_SITES[site_name]
        if path is _PLAYBOOK:
            plays = yaml.safe_load(path.read_text(encoding="utf-8"))
            for play in plays or []:
                try:
                    task = _pip_task_from_task_list((play or {}).get("tasks", []), task_name, module_key)
                    return _extra_args_of(task)
                except AssertionError:
                    continue
            raise AssertionError(f"no task named {task_name!r} in any play")
        tasks = yaml.safe_load(path.read_text(encoding="utf-8"))
        return _extra_args_of(_pip_task_from_task_list(tasks, task_name, module_key))

    if site_name in _REQUIREMENTS_FILE_SITES:
        lines = [line.strip() for line in _REQUIREMENTS_FILE_SITES[site_name].read_text(encoding="utf-8").splitlines()]
        return " ".join(line for line in lines if line.startswith("-c"))

    if site_name == "code_analysis":
        return _install_sh_npu_pip_line()

    raise AssertionError(
        f"{site_name!r} has no known way to derive extra_args — this guard is pinned to the wrong site"
    )


def _ssot_openvino_floor() -> str:
    """The `openvino>=X` floor declared by constraints/shared.txt (#15408, #10524)."""
    for line in _SSOT_CONSTRAINTS.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*openvino\s*>=\s*([0-9][0-9.]*)", line)
        if match:
            return match.group(1)
    raise AssertionError("no `openvino>=` floor in the SSOT constraints file — this guard is pinned to the wrong file")


def test_the_sources_this_guard_reads_are_present():
    """Every site must parse and install something, or every rule below is vacuous."""
    for site_name, site_factory in _SITES.items():
        site = site_factory()
        assert site.packages, f"{site_name}: installs nothing"
    assert _ssot_openvino_floor(), "no floor derived from the SSOT"


@pytest.mark.parametrize("site_name", list(_SITES))
def test_the_deprecated_meta_package_is_not_installed(site_name: str):
    """`openvino-dev` has no release compatible with openvino 2026.x.

    Asserted on the parsed package names rather than the file text: a comment
    naming the package would match a substring search over the source and pass
    regardless of what is installed. That is not hypothetical — it is how the
    first version of this check (for the role site) failed.
    """
    site = _SITES[site_name]()
    offenders = [name for name in site.packages if _bare_name(name) == "openvino-dev"]

    assert not offenders, (
        f"{site.label} installs {offenders} — pip backtracks to a numpy with no cp314 wheel "
        "and provisioning dies in an sdist build (#14447, #14452, #14453)"
    )


@pytest.mark.parametrize("site_name", list(_SITES))
def test_the_floor_is_not_below_the_ssot(site_name: str):
    """A lower (or absent, unconstrained) floor lets the resolver walk backwards into
    pre-cp314 releases.

    This is what made the openvino-dev conflict fatal rather than merely
    unsatisfiable: with a floor below the SSOT's there was an older openvino to
    retreat to. #15408 changed most sites from an inline `>=` literal to a bare
    `openvino` that derives its floor from `-c constraints/shared.txt` -- a bare
    spec is compliant only if the site actually applies that constraint (proven
    here, not just delegated to `test_the_shared_constraints_are_applied`, so a
    site that goes bare *without* wiring up `-c` still fails this test too).
    `aiml (dormant)` has no pip mechanism to attach a `-c` to at all (see
    `_CONSTRAINTS_EXEMPT`) and is exempt from that half of the check.
    """
    site = _SITES[site_name]()
    specs = [name for name in site.packages if _bare_name(name) == "openvino"]
    assert specs, f"{site.label}: no longer installs openvino at all"

    ssot_floor = _ssot_openvino_floor()
    for spec in specs:
        match = re.search(r">=\s*([0-9][0-9.]*)", spec)
        if match is None:
            if site_name in _CONSTRAINTS_EXEMPT:
                continue
            assert "constraints/shared.txt" in _extra_args_for(site_name), (
                f"{site.label}: {spec!r} has no lower bound and does not apply "
                "constraints/shared.txt, so pip may resolve any older release (#15408)"
            )
            continue
        assert _version_tuple(match.group(1)) >= _version_tuple(ssot_floor), (
            f"{site.label} pins openvino>={match.group(1)} while {_SSOT_CONSTRAINTS.name} "
            f"declares >={ssot_floor} — this site has drifted below the SSOT (#14447, #14452, #14453)"
        )


@pytest.mark.parametrize("site_name", [name for name in _SITES if name not in _CONSTRAINTS_EXEMPT])
def test_the_shared_constraints_are_applied(site_name: str):
    """Without them, any dependency can drag numpy below its pinned floor.

    `constraints/shared.txt` is what keeps numpy on 2.x; bypassing it entirely
    is why a transitive pin could reach 1.25.2. `aiml (dormant)` is exempt — see
    `_CONSTRAINTS_EXEMPT`.
    """
    site = _SITES[site_name]()
    extra_args = _extra_args_for(site_name)

    assert "constraints/shared.txt" in extra_args, (
        f"{site.label} does not apply constraints/shared.txt, so a transitive dependency can "
        "drag numpy below its floor and force an unbuildable sdist (#14447, #14452, #14453)"
    )
    assert (
        "-c" in extra_args
    ), f"{site.label}: constraints/shared.txt is referenced but not passed as a `-c` constraints file"


# --- Documentation sites (#15415) -------------------------------------------------
#
# The seven sites above are parseable specs. Prose was originally left outside this
# guard for that reason, but a version pin is mechanically checkable whatever
# surrounds it, and the exclusion had a cost: when #15406 raised the floor to
# 2026.3.1, four documents kept publishing 2026.3.0 — including a `pip install`
# command a reader runs, directly under a comment asserting the floor matched the
# SSOT. Docs drift silently precisely because nothing reads them.
#
# Two document trees state past floors on purpose and must keep their original
# values: `docs/audit/` records dated measurements ("Re-measured against PyPI on
# 2026-08-25 ... the repo's floor is now openvino>=2026.3.0") and `docs/archives/`
# stores superseded plans. Rewriting either would falsify a record rather than fix a
# drift. The exclusion is by tree, not by filename, so a new dated audit is covered
# without editing this guard.

_HISTORICAL_DOC_TREES = ("docs/audit/", "docs/archives/")

# One per live document that pins openvino today. A floor, not a census: it exists so
# that a glob which silently stops matching fails loudly instead of guarding nothing.
_MIN_LIVE_DOC_PINS = 4

_DOC_PIN_RE = re.compile(r"openvino\s*>=\s*([0-9][0-9.]*)")


def _live_doc_pins() -> list[tuple[str, int, str]]:
    """Every `openvino>=` pin in Markdown outside the historical trees."""
    found: list[tuple[str, int, str]] = []
    for path in sorted(_REPO_ROOT.rglob("*.md")):
        relative = path.relative_to(_REPO_ROOT).as_posix()
        if relative.startswith(_HISTORICAL_DOC_TREES) or "node_modules/" in relative:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            match = _DOC_PIN_RE.search(line)
            if match:
                found.append((relative, number, match.group(1)))
    return found


def test_the_documentation_scan_reaches_the_known_pins():
    """A glob that matches nothing would make the drift check below vacuous."""
    pins = _live_doc_pins()

    assert len(pins) >= _MIN_LIVE_DOC_PINS, (
        f"only {len(pins)} live documentation pin(s) found, expected at least "
        f"{_MIN_LIVE_DOC_PINS} — this scan has stopped reaching the docs it guards"
    )


def test_no_document_publishes_a_floor_below_the_ssot():
    """A stale install instruction sends a reader to a version the repo rejects.

    Reported as a whole rather than one failure at a time: the floor moves in one
    commit and every document that missed it is the same defect, so a first-failure
    abort would hide the rest of the set behind a re-run.
    """
    ssot_floor = _ssot_openvino_floor()

    drifted = [(path, number, pin) for path, number, pin in _live_doc_pins() if pin != ssot_floor]

    assert not drifted, "documentation contradicts the SSOT openvino floor (#15415):\n" + "\n".join(
        f"  {path}:{number} says >={pin}, {_SSOT_CONSTRAINTS.name} declares >={ssot_floor}"
        for path, number, pin in drifted
    )
