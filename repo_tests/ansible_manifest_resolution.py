# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which requirements manifest each ansible pip declaration site provisions (#15629).

`ansible_requirements_parity_test.py` first compared every ansible declaration
against the UNION of every manifest in the tree, so a declaration matching *any*
manifest's text read as agreement. A role provisions ONE component, so the only
manifest it can meaningfully agree with is that component's. `roles/ai-stack`
carried `fastapi>=0.115.0` and `uvicorn[standard]>=0.35.0`; the manifest it
provisions against declares `>=0.141.1` and `>=0.52.4`, but
`docs/guides/requirements-local.txt` states the older pair verbatim, so the union
found a match and the guard stayed silent until #15623 raised them by reading.

Resolution has two halves, and the split is the whole design.

`SITE_MANIFESTS` is the DECLARED half: one entry per declaration site, naming the
manifests that site provisions and saying why. It is exhaustive -- a site the walk
reaches that this table does not name fails the guard, so a new role cannot arrive
unresolved and read as a clean tree.

`derived_bindings()` is the MECHANICAL half. It re-reads the ansible tree for the
bindings the tree states about itself -- a pip task's `requirements:`, a
`build-filtered-requirements.sh` rewrite, a `copy:` that delivers a manifest, a
`synchronize:` that delivers a component tree, a `<venv>/bin/pip install -r` in a
shell task -- and resolves each to a repo-relative path. Every binding it derives
must appear in the declared entry for the same virtualenv, so the table cannot
drift away from the tree it describes without going red.

`provisioning_shapes()` is the same mechanical reading asked a different
question: not WHICH manifest fills a venv but HOW MANY KINDS of source do. A
`requirements:` install reads a manifest; a `name:` list restates packages
inline. A venv fed by both has two sources of truth and its contents depend on
which entry point ran last -- #15671, where `roles/npu-worker` installed five
packages `autobot-npu-worker/requirements.txt` had never heard of while
`playbooks/deploy-native-services.yml` installed that manifest into the same
venv. `MULTI_SOURCE_VENVS` records the venvs still in that state, shrink-only.

Where the tree states nothing the declared entry carries the reason instead, and
that is the point: `roles/tts-worker` never installs its worker's manifest, the
standalone ChromaDB venv has no manifest at all, and `roles/dependency_patching`
patches every venv on the host rather than one. Each of those is recorded AT the
site with its reason -- `EVERY_MANIFEST` for the host-wide patcher, an empty
manifest tuple for a venv no manifest feeds -- rather than folded back into a
union comparison where an unresolvable site would look exactly like a clean one.
"""

from __future__ import annotations

import functools
import pathlib
import re
from typing import Dict, NamedTuple, Tuple

import yaml

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_ANSIBLE_ROOT = _REPO_ROOT / "autobot-slm-backend" / "ansible"

# The manifests sites resolve to. Repo-relative, and every one of them is read by
# `requirement_files()` in the parity test, so a rename that misses this file
# fails `test_every_declared_manifest_exists` rather than resolving to nothing.
AI_STACK = "autobot-infrastructure/shared/docker/ai-stack/requirements-ai.txt"
BACKEND = "autobot-backend/requirements.txt"
BROWSER = "autobot-browser-worker/requirements.txt"
NPU = "autobot-npu-worker/requirements.txt"
NPU_DOCKER = "autobot-infrastructure/autobot-npu-worker/docker/requirements-npu.txt"

TTS = "autobot-tts-worker/requirements.txt"
GPU_TORCH = "requirements-gpu-torch.txt"
GPU = "requirements-gpu.txt"
ROOT_REQUIREMENTS = "requirements.txt"

# Not a path: the one resolution that legitimately spans the whole tree. Used by
# `roles/dependency_patching`, which renders its floors into a requirements file
# and installs them into EVERY autobot venv on the host, so a floor there must
# contradict no manifest. Written as an explicit resolution rather than as the
# default, which is exactly the difference #15629 is about.
EVERY_MANIFEST = "<every manifest in the tree>"


class Resolution(NamedTuple):
    """The manifests one declaration site provisions, and why those."""

    manifests: tuple[str, ...]  # () means no manifest feeds this environment
    reason: str
    # Packages this site versions that its own manifests do not declare at all.
    # The union hid these behind another component's text; naming them here keeps
    # an unanchored floor visible without pretending it is a divergence.
    unanchored: tuple[str, ...] = ()


_ROLES = "autobot-slm-backend/ansible/roles"
_INVENTORY = "autobot-slm-backend/ansible/inventory/group_vars"

# Keyed by (ansible file, environment) -- the environment being the pip task's
# `virtualenv:` text verbatim, its `executable:` when it installs outside a venv,
# or "" for the three shapes that declare packages without a task (group_vars
# `packages.python`, `python_security_updates`, `*_python_packages`).
SITE_MANIFESTS: dict[tuple[str, str], Resolution] = {
    (f"{_INVENTORY}/aiml.yml", ""): Resolution(
        (AI_STACK,),
        "deploy-aiml.yml runs roles/ai-stack, which installs this group's venv from the ai-stack "
        "manifest; the list itself is dormant and states no versions (#15596, #15621)",
    ),
    (f"{_INVENTORY}/backend.yml", ""): Resolution(
        (BACKEND,),
        "roles/backend installs the backend venv from the filtered copy of autobot-backend's "
        "manifest, which `backend.python.packages_file` names (#15596, #15621)",
    ),
    (f"{_INVENTORY}/browser.yml", ""): Resolution(
        (BROWSER,),
        "roles/browser provisions this group and the worker venv installs from the browser "
        "worker's own manifest (#15596, #15621)",
    ),
    (f"{_ROLES}/agent_config/tasks/openvino.yml", "{{ venv_dir }}"): Resolution(
        (ROOT_REQUIREMENTS,),
        "roles/agent_config/tasks/python_deps.yml installs {{ project_root }}/{{ requirements_file }} "
        "-- the deployed repo-root manifest -- into this same venv",
    ),
    (f"{_ROLES}/agent_config/tasks/playwright.yml", "{{ venv_dir }}"): Resolution(
        (ROOT_REQUIREMENTS,),
        "same venv as python_deps.yml, which installs the deployed repo-root manifest",
    ),
    (f"{_ROLES}/agent_config/tasks/python_env.yml", "{{ venv_dir }}"): Resolution(
        (ROOT_REQUIREMENTS,),
        "same venv as python_deps.yml, which installs the deployed repo-root manifest",
    ),
    (f"{_ROLES}/ai-stack/tasks/main.yml", "{{ ai_install_dir }}/venv"): Resolution(
        (AI_STACK,),
        "the role copies the ai-stack manifest to the install dir, filters it through "
        "scripts/build-filtered-requirements.sh and installs the result into this venv (#14272, #14809)",
    ),
    (f"{_ROLES}/backend/tasks/main.yml", "{{ backend_code_dir }}/venv"): Resolution(
        (BACKEND, GPU_TORCH, GPU),
        "the role rsyncs autobot-backend/ to the code dir, filters its manifest into the venv, and "
        "adds the two repo-root GPU manifests on a GPU host (#11134, #15162, #10288)",
    ),
    (f"{_ROLES}/browser/tasks/main.yml", "{{ browser_install_dir }}/venv"): Resolution(
        (BROWSER,),
        "the role rsyncs autobot-browser-worker/ to the install dir and update-all-nodes.yml "
        "installs that manifest into this venv, which now declares the web-server floors the "
        "role states rather than leaving them unanchored (#15660)",
    ),
    (f"{_ROLES}/common/tasks/main.yml", "pip3"): Resolution(
        (),
        "bootstraps pip/setuptools/wheel on the system interpreter before any component venv "
        "exists; no manifest feeds it, and it names no versions",
    ),
    (f"{_ROLES}/dependency_patching/defaults/main.yml", ""): Resolution(
        (EVERY_MANIFEST,),
        "python_security_updates is rendered into a requirements file and installed into every "
        "autobot venv on the host, so its floors must contradict no manifest (#15597)",
        unanchored=("filelock", "keras", "marshmallow", "urllib3", "werkzeug"),
    ),
    (f"{_ROLES}/dependency_patching/tasks/update-venv.yml", "{{ host_venv_path }}"): Resolution(
        (EVERY_MANIFEST,),
        "the task that installs the rendered security floors, once per venv the role finds on the host",
    ),
    (f"{_ROLES}/npu-worker/tasks/main.yml", "{{ npu_install_dir }}/venv"): Resolution(
        (NPU, NPU_DOCKER),
        "#15671: the role installs the worker manifest into this venv itself, in one pip "
        "invocation with -c constraints/shared.txt, so nothing is declared here that the "
        "manifest does not carry; update-all-nodes.yml installs the same file",
    ),
    (f"{_ROLES}/redis/tasks/chromadb.yml", "{{ chromadb_install_dir }}/venv"): Resolution(
        (BACKEND, AI_STACK),
        "the standalone ChromaDB service venv has no manifest of its own, so the floor is bound to "
        "the two manifests whose components read this instance, as the site states (#15598)",
    ),
    (f"{_ROLES}/slm_agent/defaults/main.yml", ""): Resolution(
        (),
        "the agent venv is fed from autobot_shared/pyproject.toml's dependency set, not from a "
        "requirements manifest; the list names no versions (#14278, #12142)",
    ),
    (f"{_ROLES}/slm_agent/tasks/main.yml", "{{ slm_agent_venv }}"): Resolution(
        (),
        "installs slm_agent_python_packages, whose versions come from autobot_shared/pyproject.toml",
    ),
    (f"{_ROLES}/tts-worker/tasks/main.yml", "{{ tts_install_dir }}/venv"): Resolution(
        (TTS,),
        "the role populates the worker venv itself and never installs the worker's manifest, so the "
        "floors here are that manifest's text by intent rather than by a task (#15598). #15660 "
        "added pocket-tts and scipy to that manifest, so every floor here now has an anchor",
    ),
}

#: The two shapes a pip task can fill a venv from. Kept as names rather than
#: booleans because the failure they describe is "which of these was it", and a
#: guard message naming the shape is the whole value of measuring it.
MANIFEST_SOURCE = "manifest"
INLINE_SOURCE = "inline"

#: Packaging bootstrap, not a component's packages. Every venv upgrades these
#: before anything else, so counting a `name:` list holding only them as an
#: inline source would put every venv in `MULTI_SOURCE_VENVS` and make the
#: record say nothing about any of them.
_BOOTSTRAP = frozenset({"pip", "setuptools", "wheel"})

#: First token on a `name:` entry, before any extras or specifier.
_DISTRIBUTION = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")

#: Venvs the ansible tree fills from BOTH shapes, with the reason each is not
#: yet one. Asserted by exact set equality and shrink-only, the same contract as
#: `unanchored` above: a venv that starts being filled two ways fails, and an
#: entry left behind after its venv was fixed fails just as loudly.
#:
#: #15671 removed `/opt/autobot/autobot-npu-worker/venv` from this record by
#: moving `roles/npu-worker`'s two inline lists into the worker's manifest and
#: installing from it. The three below are #15684.
MULTI_SOURCE_VENVS: dict[str, str] = {
    "/opt/autobot/autobot-ai-stack/venv": (
        "roles/ai-stack installs the filtered requirements-ai manifest (#14272, #14809) and keeps "
        "a conditional `name:` fallback list for a host where that manifest is absent; the two are "
        "hand-kept against each other, which is how the fallback's floors drifted until #15623"
    ),
    "/opt/autobot/autobot-browser-worker/venv": (
        "roles/browser installs playwright, playwright-stealth, uvicorn and fastapi as a `name:` "
        "list while update-all-nodes.yml installs autobot-browser-worker/requirements.txt into the "
        "same venv; #15660 made the manifest declare all four, so the two agree in text -- but the "
        "role still restates them, so both sides must be edited together"
    ),
    "/opt/autobot/venv": (
        "roles/agent_config/python_deps.yml installs the deployed repo-root manifest and "
        "roles/backend_services installs /opt/autobot/app/requirements.txt, while "
        "roles/agent_config's openvino.yml and playwright.yml add bare `name:` lists to the same venv"
    ),
}

#: Shared reasons, so nine entries do not become nine chances to word one fact
#: three different ways.
_AGENT_CONFIG = "python_deps.yml installs it here, from a path of two vars the walk cannot resolve"
_CHROMADB = "the standalone ChromaDB venv has no manifest; bound to its readers' by intent (#15598)"

#: Declared bindings the ansible walk cannot derive, with the reason each is
#: real anyway. Shrink-only: if the wiring for one ever becomes derivable, the
#: entry must go, and `test_no_logical_only_exception_is_stale` fails while it
#: lingers.
#:
#: Without this list the containment check is one-directional -- it catches a
#: manifest the tree installs and the table omits, but not a manifest the table
#: names after its install task is deleted. A declared entry that quietly stops
#: being true is the drift this module exists to prevent, so the reverse has to
#: be asserted too, and the genuine exceptions named rather than tolerated.
#:
#: It went from one entry to ten in #15671, and not one of the nine is new
#: drift. The reverse check used to SKIP any site the walk derived nothing for,
#: so it could not tell a structurally underivable binding from one whose
#: install task had been deleted -- deriving nothing is exactly what both look
#: like. Dropping that skip is what makes a vanished binding fail, and it is
#: what obliges every underivable-but-real binding to be named here rather than
#: to pass in silence.
LOGICAL_ONLY: Dict[Tuple[str, str], str] = {
    (f"{_ROLES}/npu-worker/tasks/main.yml", NPU_DOCKER): "delivered by the NPU worker image build, not a pip task",
    (f"{_INVENTORY}/aiml.yml", AI_STACK): "installed by roles/ai-stack; a group_vars list is not a pip task",
    (f"{_INVENTORY}/backend.yml", BACKEND): "installed by roles/backend, filtered; this list is not a pip task",
    (f"{_INVENTORY}/browser.yml", BROWSER): "installed by roles/browser; this list is not a pip task",
    (f"{_ROLES}/agent_config/tasks/openvino.yml", ROOT_REQUIREMENTS): _AGENT_CONFIG,
    (f"{_ROLES}/agent_config/tasks/playwright.yml", ROOT_REQUIREMENTS): _AGENT_CONFIG,
    (f"{_ROLES}/agent_config/tasks/python_env.yml", ROOT_REQUIREMENTS): _AGENT_CONFIG,
    (f"{_ROLES}/redis/tasks/chromadb.yml", BACKEND): _CHROMADB,
    (f"{_ROLES}/redis/tasks/chromadb.yml", AI_STACK): _CHROMADB,
    (f"{_ROLES}/tts-worker/tasks/main.yml", TTS): "the role fills this venv from name: lists and never installs it",
}

_PIP_TASK_KEYS = ("pip", "ansible.builtin.pip")
_SYNCHRONIZE_KEYS = ("synchronize", "ansible.posix.synchronize")
_COPY_KEYS = ("copy", "ansible.builtin.copy", "template", "ansible.builtin.template")
_SHELL_KEYS = ("shell", "ansible.builtin.shell", "command", "ansible.builtin.command")
_FILTER_SCRIPT = "build-filtered-requirements.sh"

# Whitespace-split, but a `{{ ... }}` template counts as one token: without that,
# `-r {{ backend_code_dir }}/requirements.txt` splits into three and the path is lost.
_TOKEN = re.compile(r"(?:\{\{[^{}]*\}\}|[^\s{}])+")
_VARIABLE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
# Where a deploy path is stated relative to the checked-out source tree, the rest of
# it IS the repo-relative path. `{{ playbook_dir }}` is deliberately absent: its depth
# depends on which playbook included the role, so `../..` from it cannot be resolved.
_CODE_SOURCE = re.compile(r"\{\{[^{}]*code_source_dir[^{}]*\}\}|/opt/autobot/src|/opt/autobot/code_source")


class _Edges(NamedTuple):
    """What the ansible tree states about where a venv's packages come from."""

    written_from: dict[str, str]  # a written requirements path -> the path it was written from
    mirrors: dict[str, str]  # a deployed directory -> the source tree it mirrors
    installs: list[tuple[str, str, str]]  # (ansible file, virtualenv text, requirements path)
    sources: list[tuple[str, str, str]]  # (ansible file, virtualenv text, source shape)


@functools.cache
def ansible_documents() -> tuple[tuple[str, object], ...]:
    """Every parsed YAML document under the ansible tree, with its repo-relative path."""
    parsed: list[tuple[str, object]] = []
    for path in sorted(_ANSIBLE_ROOT.rglob("*.yml")):
        relative = path.relative_to(_REPO_ROOT).as_posix()
        try:
            loaded = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
        except yaml.YAMLError:
            continue  # a Jinja-templated file ansible renders before parsing
        parsed.extend((relative, document) for document in loaded if document is not None)
    return tuple(parsed)


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text)


def _shell_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and isinstance(value.get("cmd"), str):
        return value["cmd"]
    return ""


def _filter_rewrite(command: str) -> tuple[str, str] | None:
    """``build-filtered-requirements.sh SOURCE root > OUTPUT`` -> ``(OUTPUT, SOURCE)``."""
    tokens = _tokens(command)
    for index, token in enumerate(tokens):
        if not token.endswith(_FILTER_SCRIPT) or index + 1 >= len(tokens):
            continue
        if ">" not in tokens[index:] or tokens.index(">", index) + 1 >= len(tokens):
            continue
        return tokens[tokens.index(">", index) + 1], tokens[index + 1]
    return None


def _shell_install(command: str) -> tuple[str, str] | None:
    """``<venv>/bin/pip install -r MANIFEST`` -> ``(<venv>, MANIFEST)``."""
    tokens = _tokens(command)
    venv = next((t.split("/bin/pip")[0] for t in tokens if "/bin/pip" in t), None)
    if venv is None or "-r" not in tokens or tokens.index("-r") + 1 >= len(tokens):
        return None
    return venv, tokens[tokens.index("-r") + 1]


def _names_a_component_package(value: object) -> bool:
    """True when a pip ``name:`` states a package that is not packaging bootstrap.

    ``name:`` is a single string or a list of them, and every venv in the tree
    opens with ``name: pip``. Reading that as an inline source would make every
    venv multi-source and the record below meaningless, so bootstrap names are
    read as what they are -- preparing the venv, not filling it.
    """
    entries = [value] if isinstance(value, str) else value if isinstance(value, list) else []
    for entry in entries:
        if not isinstance(entry, str):
            continue
        match = _DISTRIBUTION.match(entry.strip())
        if match and re.sub(r"[-_.]+", "-", match.group(1)).lower() not in _BOOTSTRAP:
            return True
    return False


# Only a pip task carrying BOTH a literal `requirements:` and a literal
# `virtualenv:` produces a derived edge. A `name:`-list pip task is invisible
# here whether or not a manifest exists behind it, so the three "no manifest"
# sites are asserted by their recorded reason rather than cross-checked.
def _record_task(key: object, value: object, path: str, edges: _Edges) -> None:
    """Record the delivery and install edges one task key opens."""
    if key in _PIP_TASK_KEYS and isinstance(value, dict):
        if isinstance(value.get("requirements"), str) and isinstance(value.get("virtualenv"), str):
            edges.installs.append((path, value["virtualenv"], value["requirements"]))
            edges.sources.append((path, value["virtualenv"], MANIFEST_SOURCE))
        if isinstance(value.get("virtualenv"), str) and _names_a_component_package(value.get("name")):
            edges.sources.append((path, value["virtualenv"], INLINE_SOURCE))
    if key in _SYNCHRONIZE_KEYS and isinstance(value, dict):
        source, destination = str(value.get("src", "")), str(value.get("dest", ""))
        if source.endswith("/") and destination.endswith("/"):
            edges.mirrors.setdefault(destination, source)
    if key in _COPY_KEYS and isinstance(value, dict):
        source, destination = str(value.get("src", "")), str(value.get("dest", ""))
        if "requirement" in destination.lower() and source:
            edges.written_from.setdefault(destination, source)
    if key in _SHELL_KEYS:
        _record_shell(_shell_text(value), path, edges)


def _record_shell(command: str, path: str, edges: _Edges) -> None:
    if _FILTER_SCRIPT in command:
        rewrite = _filter_rewrite(command)
        if rewrite is not None:
            edges.written_from.setdefault(*rewrite)
    if "/bin/pip" in command:
        install = _shell_install(command.replace("\n", " "))
        if install is not None:
            edges.installs.append((path, install[0], install[1]))
            edges.sources.append((path, install[0], MANIFEST_SOURCE))


def _walk_edges(node: object, path: str, edges: _Edges) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            _record_task(key, value, path, edges)
            _walk_edges(value, path, edges)
    elif isinstance(node, list):
        for item in node:
            _walk_edges(item, path, edges)


@functools.cache
def _edges() -> _Edges:
    edges = _Edges({}, {}, [], [])
    for path, document in ansible_documents():
        _walk_edges(document, path, edges)
    return edges


def _literals(mapping: object, found: dict[str, str]) -> None:
    """Top-level string scalars only -- a nested mapping's keys are not variable names.

    Templated values are kept as well as literal ones. Storing only literals made
    `_substitute`'s multi-pass loop dead: every scope value would already be
    final, so the first pass reached a fixed point and the comment promising that
    a variable defined in terms of another resolves was describing behaviour the
    data could not produce. A role stating ``venv_dir: "{{ install_root }}/venv"``
    then contributed no entry at all, and `environment_key` fell back to the
    verbatim text — so the same venv named two ways keyed two different bindings.
    """
    if not isinstance(mapping, dict):
        return
    for key, value in mapping.items():
        if isinstance(key, str) and isinstance(value, str):
            found.setdefault(key, value)


def _collect_play_vars(node: object, found: dict[str, str]) -> None:
    """Every `vars:` mapping in a play or task, at any depth."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "vars":
                _literals(value, found)
            elif isinstance(value, (dict, list)):
                _collect_play_vars(value, found)
    elif isinstance(node, list):
        for item in node:
            _collect_play_vars(item, found)


@functools.cache
def _scopes() -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    """``(role dir -> its defaults/vars, ansible file -> its own `vars:` blocks)``."""
    role_scope: dict[str, dict[str, str]] = {}
    file_scope: dict[str, dict[str, str]] = {}
    for path, document in ansible_documents():
        for suffix in ("/defaults/main.yml", "/vars/main.yml"):
            if path.endswith(suffix):
                _literals(document, role_scope.setdefault(path[: -len(suffix)], {}))
        _collect_play_vars(document, file_scope.setdefault(path, {}))
    return role_scope, file_scope


def _role_of(path: str) -> str:
    parts = path.split("/")
    return "/".join(parts[:4]) if path.startswith(f"{_ROLES}/") else ""


def _scope_for(path: str) -> dict[str, str]:
    role_scope, file_scope = _scopes()
    return dict(role_scope.get(_role_of(path), {}), **file_scope.get(path, {}))


def _substitute(text: str, scope: dict[str, str]) -> str:
    for _ in range(3):  # three passes resolve a var defined in terms of another
        expanded = _VARIABLE.sub(lambda match: scope.get(match.group(1), match.group(0)), text)
        if expanded == text:
            break
        text = expanded
    return text


def environment_key(path: str, environment: str) -> str:
    """A venv's identity: its deploy path where that resolves, else its text verbatim."""
    return _substitute(environment, _scope_for(path))


def _existing_suffix(text: str) -> str | None:
    """The longest >=2-component tail of a deploy path that names a repo file."""
    tail = text.split("}}")[-1]
    parts = [part for part in tail.split("/") if part not in ("", ".", "..")]
    for start in range(len(parts) - 1):
        candidate = "/".join(parts[start:])
        if (_REPO_ROOT / candidate).is_file():
            return candidate
    return None


def _repo_relative(text: str) -> str | None:
    """A deploy-time requirements path -> the repo file it was delivered from."""
    match = _CODE_SOURCE.search(text)
    if match is not None:
        candidate = text[match.end() :]
        if candidate.startswith("/") and "{{" not in candidate:
            stripped = candidate.lstrip("/")
            return stripped if (_REPO_ROOT / stripped).is_file() else None
    return _existing_suffix(text)


def _delivered_from(path: str) -> str:
    """Follow the writes that produced a requirements file back to its source."""
    written_from = _edges().written_from
    for _ in range(5):
        if path not in written_from:
            break
        path = written_from[path]
    return path


def _mirrored(path: str) -> list[str]:
    """The same path rewritten through every deployed directory that mirrors a source tree."""
    return [
        source + path[len(destination) :]
        for destination, source in _edges().mirrors.items()
        if path.startswith(destination)
    ]


def _resolve_manifest(path: str, scope: dict[str, str]) -> str | None:
    source = _delivered_from(path)
    for candidate in (source, *_mirrored(source)):
        resolved = _repo_relative(_substitute(candidate, scope))
        if resolved is not None:
            return resolved
    return None


@functools.cache
def derived_bindings() -> dict[str, frozenset[str]]:
    """``environment key -> repo manifests the ansible tree itself installs into it``."""
    bindings: dict[str, set[str]] = {}
    for path, environment, requirements in _edges().installs:
        manifest = _resolve_manifest(requirements, _scope_for(path))
        if manifest is not None:
            bindings.setdefault(environment_key(path, environment), set()).add(manifest)
    return {key: frozenset(value) for key, value in bindings.items()}


@functools.cache
def provisioning_shapes() -> dict[str, frozenset[str]]:
    """``environment key -> the source shapes the ansible tree fills that venv from``.

    Keyed the same way `derived_bindings()` is, so a venv named two ways -- the
    role's `{{ npu_install_dir }}/venv` and the playbook's `{{ npu_venv }}` --
    resolves to one entry rather than to two that never meet. That collapse IS
    the measurement: #15671 is invisible until both files are read as filling
    the same venv.
    """
    shapes: dict[str, set[str]] = {}
    for path, environment, shape in _edges().sources:
        shapes.setdefault(environment_key(path, environment), set()).add(shape)
    return {key: frozenset(value) for key, value in shapes.items()}


#: An install whose requirements path resolves to no repo manifest.
UNRESOLVED = "<unresolved>"


def manifests_installed_by_file(environment: str) -> dict[str, frozenset[str]]:
    """``ansible file -> the manifests it installs into one venv``, per file.

    `derived_bindings()` unions across files, so ONE file resolving is enough to
    make a venv look bound to a manifest -- a second file installing a different
    one, or a path the resolver returns None for, disappears into that union.
    Per file is what proves every path into a venv reads the same manifest,
    which is the claim #15671 actually makes.
    """
    per_file: dict[str, set[str]] = {}
    for path, text, requirements in _edges().installs:
        if environment_key(path, text) != environment:
            continue
        manifest = _resolve_manifest(requirements, _scope_for(path))
        per_file.setdefault(path, set()).add(manifest or UNRESOLVED)
    return {path: frozenset(manifests) for path, manifests in per_file.items()}


def files_filling(environment: str) -> frozenset[str]:
    """The ansible files whose pip tasks fill one venv, by environment key.

    Public because a guard proving a venv is filled from ONE shape has to prove
    the venv is filled by more than one file first -- otherwise a rename that
    split the two keys apart would leave that guard passing over a single site
    and say nothing.
    """
    return frozenset(path for path, text, _ in _edges().sources if environment_key(path, text) == environment)


def multi_source_venvs() -> frozenset[str]:
    """Venvs filled from more than one source shape -- the #15671 class."""
    return frozenset(key for key, shapes in provisioning_shapes().items() if len(shapes) > 1)
