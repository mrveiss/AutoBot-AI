# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One manifest of the browser worker's shipped files (#21852).

The worker's local modules were shipped by hand-copied lists in six deploy paths. A module a
list omitted made the worker die with MODULE_NOT_FOUND in that deployment, so every browser
tool failed there (seen in review of #21749). The list now lives once, in
``autobot-infrastructure/autobot-browser-worker/manifest.yml`` (``deploy.files``):

* the shell deploy paths read it through ``scripts/lib/browser_worker_files.sh`` and may not
  restate a module name;
* the compose volume lists cannot read it at runtime, so this guard holds them to it;
* a local ``require('./x')`` in the worker, or a worker module at all, that the manifest does
  not list fails here.

The guard parses JavaScript and shell with regexes, not Python, so ``_parse_cache`` has nothing
to memoise here.
"""

from __future__ import annotations

import re
import subprocess

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from autobot_shared.testfile_names import is_test_filename
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

yaml = pytest.importorskip("yaml")

_WORKER = "autobot-browser-worker"
_MANIFEST = "autobot-infrastructure/autobot-browser-worker/manifest.yml"
_HELPER = "scripts/lib/browser_worker_files.sh"
_ENTRY = "playwright-server.js"
_COMPOSE_DIR = "autobot-infrastructure/shared/docker/compose"
_COMPOSE = ("docker-compose.playwright.yml", "docker-compose.playwright-vnc.yml")
_SHELL = (
    "run_agent.sh",
    "autobot-infrastructure/shared/scripts/setup_browser_vnc.sh",
    "autobot-infrastructure/shared/scripts/setup/setup_repair.sh",
    "autobot-infrastructure/shared/scripts/infrastructure/deploy_browser_vnc_services.sh",
)
_REQUIRE = re.compile(r"""\brequire\(\s*['"](\.{1,2}/[^'"]+)['"]\s*\)""")


def _worker_sources(root) -> list[str]:
    """Tracked non-test `.js` directly in the worker directory. Empty is REACH's to refuse."""
    try:
        tracked = tracked_paths(root, _WORKER)
    except EmptyEnumeration:
        return []
    return [p for p in tracked if p.endswith(".js") and p.count("/") == 1 and not is_test_filename(p)]


REACH = declare(
    "browser-worker-one-manifest-21852",
    discover=_worker_sources,
    what="browser worker modules",
    floor=3,  # #19676: pinned while the declaration is new; drops once it has a base to compare to
    growth=10,
    roots=(_WORKER,),
)


def _manifest_files(text: str) -> list[str]:
    return list(yaml.safe_load(text)["deploy"]["files"])


def _required_modules(source: str) -> set[str]:
    """File names a worker source loads with a relative `require`, `.js` implied when absent."""
    names = {m.rsplit("/", 1)[-1] for m in _REQUIRE.findall(source)}
    return {n if n.endswith((".js", ".json")) else f"{n}.js" for n in names}


def _unshipped(sources: dict[str, str], shipped: list[str]) -> list[str]:
    """Worker modules, or modules they require, that the manifest does not list."""
    missing = {name for name in sources if name not in shipped}
    for text in sources.values():
        missing |= {n for n in _required_modules(text) if n not in shipped}
    return sorted(missing)


def _compose_drift(text: str, shipped: list[str]) -> list[str]:
    """Shipped files a compose file does not mount from the worker directory."""
    return [f for f in shipped if f"{_WORKER}/{f}:" not in text]


def _shell_drift(text: str, shipped: list[str]) -> list[str]:
    """Problems in a deploy script: no manifest read, or a module name restated.

    The entry file's name is allowed (log lines, existence checks); every other shipped module
    named literally is the hand-copied list returning.
    """
    problems = [] if "browser_worker_files" in text else ["does not read the manifest through browser_worker_files"]
    return problems + [f"restates {f}" for f in shipped if f != _ENTRY and f in text]


def _read(rel: str) -> str:
    return (repo_root() / rel).read_text(encoding="utf-8")


# --- detector controls -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "sources", "shipped", "expected"),
    [
        ("all shipped", {"a.js": "require('./b')", "b.js": ""}, ["a.js", "b.js"], []),
        ("a required module is not listed", {"a.js": "require('./b')", "b.js": ""}, ["a.js"], ["b.js"]),
        ("an unrequired module is not listed", {"a.js": "", "c.js": ""}, ["a.js"], ["c.js"]),
        ("a require of a file that is not in the tree", {"a.js": 'require("./gone.js")'}, ["a.js"], ["gone.js"]),
        ("a package require is not local", {"a.js": "require('express')"}, ["a.js"], []),
    ],
)
def test_the_require_detector_finds_an_unshipped_module(label, sources, shipped, expected) -> None:
    assert _unshipped(sources, shipped) == expected, label


@pytest.mark.parametrize(
    ("label", "text", "expected"),
    [
        (
            "every file mounted",
            "- ../x/autobot-browser-worker/a.js:/app/a.js\n- ../x/autobot-browser-worker/b.js:/app/b.js",
            [],
        ),
        ("one file missing", "- ../x/autobot-browser-worker/a.js:/app/a.js", ["b.js"]),
        (
            "a file from another directory",
            "- ../x/other/b.js:/app/b.js\n- ../x/autobot-browser-worker/a.js:/a",
            ["b.js"],
        ),
    ],
)
def test_the_compose_detector_finds_a_missing_mount(label, text, expected) -> None:
    assert _compose_drift(text, ["a.js", "b.js"]) == expected, label


@pytest.mark.parametrize(
    ("label", "text", "expected"),
    [
        ("reads the manifest", 'for f in $(browser_worker_files "$R"); do cp "$f"; done', []),
        (
            "a hand-copied list",
            "for f in playwright-server.js session-store.js; do scp $f; done",
            ["does not read the manifest through browser_worker_files", "restates session-store.js"],
        ),
        ("the entry named in a message", 'browser_worker_files "$R"; echo playwright-server.js', []),
    ],
)
def test_the_shell_detector_finds_a_restated_list(label, text, expected) -> None:
    assert _shell_drift(text, [_ENTRY, "session-store.js"]) == expected, label


# --- the live tree -----------------------------------------------------------------------------


def test_the_scan_is_not_vacuous() -> None:
    assert f"{_WORKER}/{_ENTRY}" in REACH.examined(repo_root())


def test_the_manifest_ships_every_worker_module_and_every_module_it_requires() -> None:
    root = repo_root()
    names = REACH.examined(root)
    sources = {rel.rsplit("/", 1)[-1]: _read(rel) for rel in names}
    missing = _unshipped(sources, _manifest_files(_read(_MANIFEST)))
    REACH.completed(names, root)
    assert (
        not missing
    ), f"#21852: not in {_MANIFEST} deploy.files: {missing}; the worker would die with MODULE_NOT_FOUND."


def test_every_manifest_file_exists_in_the_worker() -> None:
    root = repo_root()
    gone = [f for f in _manifest_files(_read(_MANIFEST)) if not (root / _WORKER / f).is_file()]
    assert not gone, f"#21852: deploy.files names files absent from {_WORKER}/: {gone}"


@pytest.mark.parametrize("name", _COMPOSE)
def test_a_compose_file_mounts_every_shipped_file(name: str) -> None:
    drift = _compose_drift(_read(f"{_COMPOSE_DIR}/{name}"), _manifest_files(_read(_MANIFEST)))
    assert (
        not drift
    ), f"#21852: {name} does not mount {drift} from {_WORKER}/; add them or the worker dies in that deploy."


@pytest.mark.parametrize("rel", _SHELL)
def test_a_deploy_script_reads_the_manifest(rel: str) -> None:
    problems = _shell_drift(_read(rel), _manifest_files(_read(_MANIFEST)))
    assert not problems, f"#21852: {rel}: {problems}; read the list through {_HELPER}."


def test_the_shell_reader_returns_exactly_the_manifest_list() -> None:
    root = repo_root()
    out = subprocess.run(["bash", str(root / _HELPER), str(root)], capture_output=True, text=True, check=True)
    assert out.stdout.split() == _manifest_files(_read(_MANIFEST))


def test_the_shell_reader_refuses_a_manifest_that_lists_nothing(tmp_path) -> None:
    target = tmp_path / "autobot-infrastructure" / "autobot-browser-worker"
    target.mkdir(parents=True)
    (target / "manifest.yml").write_text("deploy:\n  source: x/\n", encoding="utf-8")
    out = subprocess.run(["bash", str(repo_root() / _HELPER), str(tmp_path)], capture_output=True, text=True)
    assert out.returncode != 0 and "lists nothing" in out.stderr
