# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""B3 (#13539): `backend_install_dir` must mean the BACKEND COMPONENT directory
everywhere it is defined -- never the deploy root.

roles/backend/templates/autobot-backend.service.j2 (and the celery / celery-beat
/ mcp-bridge units, which share the same line) derive autobot_shared's
PYTHONPATH entry as `{{ backend_install_dir | dirname }}/autobot_shared`. That
`| dirname` is only correct if `backend_install_dir` is the component directory
(`.../autobot-backend`, one level BELOW the deploy root) -- the meaning
`roles/backend/defaults/main.yml` and `roles/ai-stack/defaults/main.yml` give it.
`setup-user-backend.yml`, `fix-backend-environment.yml` (which renders this same
template directly),`deploy-backend-remote.yml` and `deploy-backend-local.yml`
(both of which run the `backend` role) used to override it with the deploy ROOT
instead, so `| dirname` walked one level too far and the rendered unit's
autobot_shared PYTHONPATH entry pointed outside the deploy tree entirely
(`/opt/autobot_shared` instead of `/opt/autobot/autobot_shared`) -- silent
because nothing imports from that path today, so the unit merely runs with a
narrower PYTHONPATH than intended, and it would defeat pinning outright once a
release root is anything other than /opt/autobot.

This module renders the REAL `Environment="PYTHONPATH=...` line extracted from
the real template (never a copied rule) against every scope that defines
`backend_install_dir`, and asserts the rendered autobot_shared segment is a
sibling of that scope's own deploy root -- `test_the_root_meaning_would_have_
rendered_the_wrong_pythonpath` is the contrast mutation restoring the historical
root-meaning override and showing the same render goes wrong.
"""

from __future__ import annotations

import re
from pathlib import Path

import jinja2
import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ANSIBLE_ROOT = _REPO_ROOT / "autobot-slm-backend" / "ansible"

_BACKEND_TEMPLATE = _ANSIBLE_ROOT / "roles" / "backend" / "templates" / "autobot-backend.service.j2"
_BACKEND_DEFAULTS = _ANSIBLE_ROOT / "roles" / "backend" / "defaults" / "main.yml"
_AI_STACK_DEFAULTS = _ANSIBLE_ROOT / "roles" / "ai-stack" / "defaults" / "main.yml"

#: playbooks that override backend_install_dir at play scope and, before
#: #13539, fed the ROOT meaning into the shared template above.
_CONSUMER_PLAYBOOKS = {
    "setup-user-backend": _ANSIBLE_ROOT / "setup-user-backend.yml",
    "fix-backend-environment": _ANSIBLE_ROOT / "playbooks" / "fix-backend-environment.yml",
    "deploy-backend-remote": _ANSIBLE_ROOT / "playbooks" / "deploy-backend-remote.yml",
    "deploy-backend-local": _ANSIBLE_ROOT / "playbooks" / "deploy-backend-local.yml",
}


def _load_plays(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _play_vars(path: Path) -> dict:
    """The first play in the file that actually declares `vars:`.

    deploy-backend-remote.yml/deploy-backend-local.yml both open with an
    `import_playbook: pre-flight-code-sync.yml` entry that carries no `vars:`
    at all; the real play is the second document.
    """
    for play in _load_plays(path):
        if isinstance(play, dict) and "vars" in play:
            return play["vars"]
    raise AssertionError(f"no play in {path} declares a vars: block")


def _ansible_jinja_env():
    """A jinja2.Environment carrying the one Ansible filter these templates
    use (`dirname` = os.path.dirname) -- plain jinja2 does not ship it."""
    jinja2 = pytest.importorskip("jinja2")
    env = jinja2.Environment()  # nosec B701  # compiling repo-owned defaults, never user input
    env.filters["dirname"] = lambda value: str(Path(str(value)).parent)
    return env


def _resolve(raw: dict) -> dict:
    """Iteratively render a flat vars mapping against itself (see the B4
    sibling test for why this needs more than one pass).

    Unrelated keys these playbooks also declare (redis_host from inventory
    group vars, hostvars[groups[...]] lookups, etc.) cannot render standalone
    here -- irrelevant to the backend_install_dir/backend_deployed_root chain
    under test, so a render failure just leaves that one key untouched rather
    than aborting resolution of everything else.
    """
    env = _ansible_jinja_env()
    context = {k: v for k, v in raw.items() if isinstance(v, (str, int, float, bool))}
    for _ in range(6):
        progressed = False
        for key, value in list(context.items()):
            if isinstance(value, str) and "{{" in value:
                try:
                    rendered = env.from_string(value).render(**context)
                except jinja2.exceptions.TemplateError:
                    continue
                if rendered != value:
                    context[key] = rendered
                    progressed = True
        if not progressed:
            break
    return context


def _pythonpath_line() -> str:
    """The real PYTHONPATH Environment= line, selected by its variable name so a
    reformat elsewhere in the unit cannot silently point this test at the wrong
    line."""
    text = _BACKEND_TEMPLATE.read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if line.strip().startswith('Environment="PYTHONPATH=')]
    assert len(lines) == 1, (
        f"expected exactly one PYTHONPATH Environment= line in {_BACKEND_TEMPLATE}, found {len(lines)}"
    )
    return lines[0].strip()


def _render_pythonpath(context: dict) -> str:
    env = _ansible_jinja_env()
    return env.from_string(_pythonpath_line()).render(**context)


def _autobot_shared_entry(rendered_pythonpath: str) -> str:
    """Pull the `.../autobot_shared` colon-delimited entry out of a rendered
    `Environment="PYTHONPATH=a:b:c:d"` line."""
    match = re.search(r'PYTHONPATH=([^"]+)"', rendered_pythonpath)
    assert match, f"could not find a PYTHONPATH value in {rendered_pythonpath!r}"
    entries = match.group(1).split(":")
    shared_entries = [entry for entry in entries if entry.endswith("/autobot_shared")]
    assert len(shared_entries) == 1, (
        f"expected exactly one autobot_shared PYTHONPATH entry, found {shared_entries} in {rendered_pythonpath!r}"
    )
    return shared_entries[0]


def test_the_pythonpath_line_was_actually_extracted() -> None:
    """An empty/renamed line would make every render below vacuous."""
    line = _pythonpath_line()
    assert "backend_install_dir" in line
    assert "autobot_shared" in line


def test_component_meaning_renders_the_shared_dir_as_a_sibling_of_the_component() -> None:
    """roles/backend/defaults/main.yml's OWN meaning, rendered through the
    template's own expression -- the positive baseline every consumer must match."""
    defaults = _resolve(yaml.safe_load(_BACKEND_DEFAULTS.read_text(encoding="utf-8")))
    rendered = _render_pythonpath(defaults)
    shared_entry = _autobot_shared_entry(rendered)
    expected = str(Path(defaults["backend_install_dir"]).parent / "autobot_shared")
    assert shared_entry == expected, (
        f"roles/backend/defaults/main.yml's own backend_install_dir "
        f"({defaults['backend_install_dir']!r}) no longer renders autobot_shared as its own "
        f"sibling ({expected!r}); got {shared_entry!r}."
    )
    assert shared_entry == "/opt/autobot/autobot_shared", rendered


@pytest.mark.parametrize("name, path", sorted(_CONSUMER_PLAYBOOKS.items()))
def test_each_consumer_renders_the_same_correct_pythonpath_entry(name: str, path: Path) -> None:
    """The B3 fix, proved against the REAL template: each of these four
    playbooks used to override backend_install_dir with the deploy root; each
    must now render the identical, correct autobot_shared PYTHONPATH entry."""
    context = _resolve(_play_vars(path))
    assert "backend_install_dir" in context, f"{path} no longer defines backend_install_dir"
    rendered = _render_pythonpath(context)
    shared_entry = _autobot_shared_entry(rendered)
    expected = str(Path(context["backend_install_dir"]).parent / "autobot_shared")
    assert shared_entry == expected, (
        f"{path.relative_to(_REPO_ROOT)} renders autobot_shared's PYTHONPATH entry as "
        f"{shared_entry!r}, not the {expected!r} sibling of its own backend_install_dir "
        f"({context['backend_install_dir']!r}) -- the two-meanings regression B3 exists to "
        "prevent (#13539)."
    )
    assert shared_entry == "/opt/autobot/autobot_shared", rendered


@pytest.mark.parametrize("name, path", sorted(_CONSUMER_PLAYBOOKS.items()))
def test_the_root_meaning_would_have_rendered_the_wrong_pythonpath(name: str, path: Path) -> None:
    """Contrast mutation: reproduce the PRE-#13539 override (backend_install_dir
    = the deploy root instead of the component dir) for this exact consumer and
    show the same render now disagrees with the correct baseline."""
    context = _resolve(_play_vars(path))
    deployed_root = context.get("backend_deployed_root")
    assert deployed_root, (
        f"{path.relative_to(_REPO_ROOT)} no longer defines backend_deployed_root -- "
        "update this test's contrast input to match wherever the deploy root now lives"
    )
    mutated = dict(context)
    mutated["backend_install_dir"] = deployed_root  # the historical (wrong) override
    rendered = _render_pythonpath(mutated)
    shared_entry = _autobot_shared_entry(rendered)
    correct_expected = str(Path(context["backend_install_dir"]).parent / "autobot_shared")
    assert shared_entry != correct_expected, (
        f"{path.relative_to(_REPO_ROOT)}: feeding the historical root-meaning override "
        f"({deployed_root!r}) into backend_install_dir unexpectedly still rendered the "
        f"correct autobot_shared entry ({shared_entry!r}); this contrast mutation is not "
        "discriminating anything (#13539/B3)."
    )
    assert shared_entry == "/opt/autobot_shared", rendered
