# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One tracked home per static data file (#18556).

``error_messages.yaml`` lived in three places, ``prometheus.yml`` and ``permission_rules.yaml``
each had a second copy kept in step by a drift script, and the Grafana datasource and Prometheus
config each had a drifted infrastructure fork that only a broken installer script read. The
earlier guard rejected only *byte-identical* copies, so every drifted fork passed it.

This guard asks a different question: for each guarded file NAME, which tracked paths may carry
it? ``_ALLOWED`` answers with an explicit list. Any other tracked file with that basename fails,
whatever its bytes, so a re-added copy cannot hide by drifting by one line. The enumeration is the
whole repository (git decides what exists), not a list of roots that a copy could slip outside of.

An allow-list entry that is no longer tracked fails too, so the list shrinks when the work it
points at lands instead of rotting into a licence for a file that is gone.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Iterable

import pytest
import yaml
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from autobot_shared.paths import scrubbed_git_env
from autobot_shared.system_knowledge_paths import SYSTEM_KNOWLEDGE_RUNTIME_REL, SYSTEM_KNOWLEDGE_TEMPLATES_REL
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

#: guarded basename -> the ONLY tracked paths allowed to carry it.
_ALLOWED: dict[str, frozenset[str]] = {
    "error_messages.yaml": frozenset({"autobot-backend/static/error_messages.yaml"}),
    # Three unrelated files share this basename; none is a copy of another:
    #  * the Docker scrape config, mounted whole by docker-compose;
    #  * the Docker Grafana datasource, mounted by docker-compose;
    #  * the Ansible monitoring role's Prometheus TASK file (the fleet config is the template
    #    prometheus.yml.j2, a different basename). The role is the only fleet install path.
    # The infrastructure forks of the scrape config and the datasource were folded into the role
    # and removed; re-adding either is the failure this guard exists for.
    "prometheus.yml": frozenset(
        {
            "autobot-monitoring/prometheus.yml",
            "autobot-monitoring/grafana/provisioning/datasources/prometheus.yml",
            "autobot-slm-backend/ansible/roles/monitoring/tasks/prometheus.yml",
        }
    ),
    # The 492-line infrastructure ruleset is NOT a copy of the 5-line backend file: Docker
    # overwrites the backend file with it. Which one is canonical is the policy decision owned by
    # #17852; until it lands both stay, and the list shrinks there.
    "permission_rules.yaml": frozenset(
        {
            "autobot-backend/config/permission_rules.yaml",
            "autobot-infrastructure/shared/config/permission_rules.yaml",
        }
    ),
    # #18884: the Docker image ships the backend registry; the infrastructure copy (a different,
    # loader-incompatible file that overwrote it) is removed.
    "llm_models.yaml": frozenset({"autobot-backend/config/llm_models.yaml"}),
}
#: #18577: the system-knowledge templates live ONLY under the template dir of
#: ``autobot_shared.system_knowledge_paths``. Its runtime dir is where the managers write their
#: copies (data/* is gitignored), so nothing under it may be tracked: a second template tree.
_TEMPLATES_PREFIX = f"{SYSTEM_KNOWLEDGE_TEMPLATES_REL.as_posix()}/"
_RUNTIME_ONLY_PREFIX = f"{SYSTEM_KNOWLEDGE_RUNTIME_REL.as_posix()}/"
#: Roots that hold an allowed file today: the reach claim (every one must be populated).
_ROOTS = ("autobot-backend", "autobot-slm-backend", "autobot-infrastructure", "autobot-monitoring")
#: Whole-repo pathspecs: a copy outside every root above must still be seen.
_PATHSPECS = (*(f"*{name}" for name in _ALLOWED), f"{_RUNTIME_ONLY_PREFIX}*")


def _name(rel: str) -> str:
    return rel.rsplit("/", 1)[-1]


def _violations(paths: Iterable[str]) -> list[str]:
    """Every way ``paths`` departs from ``_ALLOWED``, in either direction.

    An empty ``paths`` is NOT clean: every allowed path is then reported missing, so a scan that
    examined nothing cannot read as a pass.
    """
    paths = list(paths)
    present = {rel for rel in paths if _name(rel) in _ALLOWED}
    found = [
        f"{rel}: tracked under the runtime-only {_RUNTIME_ONLY_PREFIX} (templates live in {_TEMPLATES_PREFIX})"
        for rel in sorted(rel for rel in paths if rel.startswith(_RUNTIME_ONLY_PREFIX))
    ]
    found += [
        f"{rel}: not an allowed path for {_name(rel)} (allowed: {sorted(_ALLOWED[_name(rel)])})"
        for rel in sorted(present)
        if rel not in _ALLOWED[_name(rel)]
    ]
    for name, allowed in _ALLOWED.items():
        found += [f"{rel}: allow-listed for {name} but no longer tracked" for rel in sorted(allowed - present)]
    return found


def _population(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, *_PATHSPECS)
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _name(rel) in _ALLOWED or rel.startswith(_RUNTIME_ONLY_PREFIX)]


REACH = declare(
    "one-static-data-copy-scan",
    discover=_population,
    # Window against 8 files is [6, 8]; pinned mid-window.
    floor=7,
    what="tracked files named like a guarded static data file",
    roots=_ROOTS,
    growth=2,
)


def test_each_guarded_data_file_is_only_at_an_allowed_path() -> None:
    found = _violations(REACH.examined(repo_root()))
    assert not found, f"#18556: {found}"


def test_the_allow_list_names_only_guarded_basenames() -> None:
    for name, allowed in _ALLOWED.items():
        assert allowed, name
        assert {_name(rel) for rel in allowed} == {name}


_CLEAN = [rel for allowed in _ALLOWED.values() for rel in sorted(allowed)]


def test_contrast_the_allowed_set_passes() -> None:
    assert _violations(_CLEAN) == []


def test_contrast_an_empty_scan_is_not_clean() -> None:
    assert len(_violations([])) == len(_CLEAN)


@pytest.mark.parametrize("name", sorted(_ALLOWED))
def test_contrast_a_readded_copy_at_any_other_path_fails(name: str) -> None:
    found = _violations([*_CLEAN, f"somewhere/else/{name}"])
    assert [v for v in found if v.startswith(f"somewhere/else/{name}: not an allowed path")]


@pytest.mark.parametrize(
    "removed_fork",
    [
        "autobot-infrastructure/shared/config/prometheus/prometheus.yml",
        "autobot-infrastructure/shared/docker/monitoring/prometheus.yml",
        "autobot-infrastructure/shared/config/grafana/provisioning/datasources/prometheus.yml",
        "autobot-infrastructure/shared/config/error_messages.yaml",
        "autobot-infrastructure/shared/config/llm_models.yaml",
    ],
)
def test_contrast_each_removed_fork_fails_if_it_returns(removed_fork: str) -> None:
    assert any(v.startswith(f"{removed_fork}:") for v in _violations([*_CLEAN, removed_fork]))


def test_contrast_an_allow_listed_path_that_vanished_fails() -> None:
    gone = "autobot-infrastructure/shared/config/permission_rules.yaml"
    assert any(v.startswith(f"{gone}: allow-listed") for v in _violations([p for p in _CLEAN if p != gone]))


def _git_env() -> dict[str, str]:
    """Hermetic: no global or system config, so a global ignore rule cannot untrack a file here."""
    return {**scrubbed_git_env(), "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, env=_git_env())


def _tracked_tree(root: Path, files: dict[str, bytes]) -> None:
    subprocess.run(["git", "init", "-q", str(root)], check=True, env=_git_env())
    for rel, body in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
    _git(root, "add", "-A")


def test_contrast_a_drifted_readded_copy_in_a_real_git_tree_fails(tmp_path: Path) -> None:
    """End to end through the real enumerator: the re-added copy differs from the canonical one."""
    canonical = {rel: f"canonical {rel}\n".encode() for rel in _CLEAN}
    clean, dirty = tmp_path / "clean", tmp_path / "dirty"
    _tracked_tree(clean, canonical)
    fork = "autobot-infrastructure/shared/config/prometheus/prometheus.yml"
    _tracked_tree(dirty, {**canonical, fork: b"environment: production  # drifted\n"})
    assert _violations(_population(clean)) == []
    found = _violations(_population(dirty))
    assert [v for v in found if v.startswith(f"{fork}: not an allowed path")]


def test_a_global_ignore_rule_cannot_untrack_a_file_in_the_throwaway_tree(tmp_path: Path, monkeypatch) -> None:
    """The helpers ignore the ambient git config: a global `core.excludesFile` naming a guarded file
    would otherwise leave it untracked, and the end-to-end test above would pass for the wrong reason."""
    ignore, config = tmp_path / "ignore", tmp_path / "gitconfig"
    ignore.write_text("prometheus.yml\n", encoding="utf-8")
    config.write_text(f"[core]\n\texcludesFile = {ignore}\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    fork = "autobot-infrastructure/shared/config/prometheus/prometheus.yml"
    _tracked_tree(tmp_path / "repo", {fork: b"x\n"})
    assert fork in _population(tmp_path / "repo")


@pytest.mark.parametrize(
    "returned",
    [
        f"{_RUNTIME_ONLY_PREFIX}tools/file_analysis.yaml",
        f"{_RUNTIME_ONLY_PREFIX}.imported",
        f"{_RUNTIME_ONLY_PREFIX}workflows/brand_new_but_drifted.yaml",
    ],
)
def test_contrast_a_tracked_runtime_system_knowledge_file_fails(returned: str) -> None:
    assert any(v.startswith(f"{returned}: tracked under the runtime-only") for v in _violations([*_CLEAN, returned]))


# --------------------------------------------------------------------------------------------------
# #19310: ONE template tree, recognised by CONTENT. The basename guard above sees a copy only at a
# path it already names; a template tree re-added under any other directory passed it.
# --------------------------------------------------------------------------------------------------

#: The import's template schema (``SystemKnowledgeManager``): a ``metadata`` mapping beside a
#: ``tools`` list (tool templates) or an ``objective`` (workflow and procedure templates).
_TEMPLATE_BODY_KEYS = frozenset({"tools", "objective"})


def _is_template(text: str) -> bool:
    """Whether ``text`` parses as one system-knowledge template, whatever its path or name."""
    if "metadata:" not in text:  # cheap pre-filter; the parse below decides
        return False
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError:  # multi-document or Jinja YAML: not loadable by the import either
        return False
    return isinstance(doc, dict) and isinstance(doc.get("metadata"), dict) and bool(_TEMPLATE_BODY_KEYS & doc.keys())


def _templates(root: Path) -> list[str]:
    """Every tracked YAML in the repository whose content is a template."""
    try:
        tracked = tracked_paths(root, "*.yaml", "*.yml")
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_template((root / rel).read_text(encoding="utf-8", errors="replace"))]


def _template_violations(templates: Iterable[str]) -> list[str]:
    return [
        f"{rel}: a system-knowledge template outside {_TEMPLATES_PREFIX} -- a second template tree"
        for rel in sorted(templates)
        if not rel.startswith(_TEMPLATES_PREFIX)
    ]


TEMPLATES = declare(
    "one-system-knowledge-template-tree",
    discover=_templates,
    # Measured 2026-10-23: 14 tracked templates, all under the template dir; window [12, 14].
    floor=13,
    what="tracked YAML files whose content is a system-knowledge template",
    roots=(SYSTEM_KNOWLEDGE_TEMPLATES_REL.parts[0],),
    growth=2,
)


def test_system_knowledge_templates_live_in_one_tree() -> None:
    found = _template_violations(TEMPLATES.examined(repo_root()))
    assert not found, f"#19310: {found}"


_TOOL_TEMPLATE = "metadata:\n  category: file_analysis\ntools:\n  - name: file\n"
_WORKFLOW_TEMPLATE = 'metadata:\n  name: "Incident Response"\nobjective: "Respond"\n'


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (_TOOL_TEMPLATE, True),
        (_WORKFLOW_TEMPLATE, True),
        ("metadata:\n  name: x\nspec:\n  replicas: 1\n", False),  # metadata without a template body
        ("tools:\n  - name: file\n", False),  # body without metadata
        ("metadata: {a: 1}\n---\ntools: []\n", False),  # multi-document
        ("collections:\n  facts: {}\n", False),
    ],
)
def test_contrast_template_recognition(text: str, expected: bool) -> None:
    assert _is_template(text) is expected


def test_contrast_a_template_tree_readded_at_a_new_path_fails(tmp_path: Path) -> None:
    """End to end: the copy carries no guarded basename and sits outside every guarded prefix."""
    canonical = {f"{_TEMPLATES_PREFIX}tools/file_analysis.yaml": _TOOL_TEMPLATE.encode()}
    clean, dirty = tmp_path / "clean", tmp_path / "dirty"
    _tracked_tree(clean, canonical)
    copy = "system_knowledge/tools/renamed_drifted.yml"
    _tracked_tree(dirty, {**canonical, copy: (_TOOL_TEMPLATE + "  - name: binwalk\n").encode()})
    assert _template_violations(_templates(clean)) == []
    assert [v for v in _template_violations(_templates(dirty)) if v.startswith(f"{copy}: a system-knowledge template")]


# --------------------------------------------------------------------------------------------------
# #19310: the runtime dir is spelled ONCE, in ``autobot_shared/system_knowledge_paths.py``. A
# relative literal elsewhere resolves against the working directory instead of the project root.
# --------------------------------------------------------------------------------------------------

_PATHS_MODULE = "autobot_shared/system_knowledge_paths.py"
#: The runtime dir (or its ``_backups`` sibling) as one string, or its two segments joined by
#: ``/`` or ``,``. Written here only through the constant, so this file passes its own scan.
_DATA, _SK = SYSTEM_KNOWLEDGE_RUNTIME_REL.parts
_RUNTIME_LITERAL = re.compile(r"""\bdata(?:/|["']\)?\s*[/,]\s*["'])system_knowledge""")
#: Every tracked text type the literal could be written in.
_TEXT_PATTERNS = tuple(
    f"*.{ext}"
    for ext in (
        "py", "ts", "js", "mjs", "vue", "md", "sh", "yml", "yaml", "j2",
        "json", "toml", "txt", "conf", "service", "ini", "cfg", "html",
    )
)  # fmt: skip


def _text_files(root: Path) -> list[str]:
    try:
        return tracked_paths(root, *_TEXT_PATTERNS)
    except EmptyEnumeration:
        return []


def _all_tracked(root: Path) -> int:
    try:
        return len(tracked_paths(root))
    except EmptyEnumeration:
        return 0


def _literal_hits(rel: str, text: str) -> list[str]:
    return [
        f"{rel}:{n}: {line.strip()}" for n, line in enumerate(text.splitlines(), 1) if _RUNTIME_LITERAL.search(line)
    ]


#: Measured 2026-10-23: 12,073 text files of 12,318 tracked (0.980).
TEXT_FILES = declare(
    "system-knowledge-runtime-literal-scan",
    discover=_text_files,
    reference=_all_tracked,
    min_fraction=0.9,
    what="tracked text files scanned for a hand-spelled system-knowledge runtime path",
)


def test_the_runtime_dir_is_spelled_only_in_the_paths_module() -> None:
    root = repo_root()
    found = [
        hit
        for rel in TEXT_FILES.examined(root)
        if rel != _PATHS_MODULE
        for hit in _literal_hits(rel, (root / rel).read_text(encoding="utf-8", errors="replace"))
    ]
    assert not found, f"#19310: resolve it through system_knowledge_dirs(): {found}"


def test_the_paths_module_still_spells_it() -> None:
    """Control: the exempt module is the one place the literal is written, so the scan can see it."""
    assert _literal_hits(_PATHS_MODULE, (repo_root() / _PATHS_MODULE).read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        (f'self.knowledge_base_dir = Path("{_DATA}/{_SK}")', True),
        (f'root / "{_DATA}" / "{_SK}" / "autobot_identity.md"', True),
        (f"path.join(PROJECT_ROOT, '{_DATA}', '{_SK}')", True),
        (f'Path("{_DATA}") / "{_SK}"', True),
        (f'Path("{_DATA}/{_SK}_backups")', True),
        ("from autobot_shared.system_knowledge_paths import system_knowledge_dirs", False),
        ('Path("metadata/system_knowledge")', False),
        ('Path("data") / "conversations"', False),
    ],
)
def test_contrast_runtime_literal_recognition(line: str, expected: bool) -> None:
    assert bool(_RUNTIME_LITERAL.search(line)) is expected
