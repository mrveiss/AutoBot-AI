# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20941: every env/secrets render hides its diff and every root-key render is preceded by the reader.

Two classes, both swept across EVERY ansible task file in the repo (not a named list):
* a template/copy whose dest is an env or secrets file prints the file under `--diff` unless `diff: false`;
* a render of a template that writes AUTOBOT_SECRETS_ROOT_KEY writes it empty unless the shared reader ran first.
Each has a control proving the detector fires on the broken shape. The last test follows a populated SLM
secrets file through the reader's own pattern into the rendered env, offline (no hosts).
"""

from __future__ import annotations

import re
from pathlib import Path

import jinja2
import yaml
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

ROOT = repo_root()
_SECRET_FILE = re.compile(r"\.env\b|env\.j2|secrets|credentials", re.IGNORECASE)
_READERS = ("read_secrets_root_key.yml", "read_slm_secrets_root_key.yml")
_KEY = "AUTOBOT_SECRETS_ROOT_KEY"
#: The source of the key, rendered after its own back-fill: it is what the readers read.
_SOURCE_TEMPLATE = "slm-secrets.env.j2"
_PLAY_KEYS = ("pre_tasks", "tasks", "post_tasks", "handlers", "block", "rescue", "always")


def _ansible_files(root: Path = ROOT) -> list[Path]:
    try:
        found = tracked_paths(root, "*.yml", "*.yaml")
    except EmptyEnumeration:
        return []  # declare() contract: an empty tree is reported by the floor, not raised here
    return [root / f for f in found if "/ansible/" in f and "node_modules" not in f]


#: Measured 2026-11-08: 361 tracked ansible yml/yaml files; 250 leaves room for pruning before the sweep narrows.
REACH = declare(
    "ansible-secret-renders-20941",
    discover=_ansible_files,
    floor=361,  # mid-window: population 361, window (361, 361)
    what="tracked ansible yml/yaml files swept for env/secrets writes and root-key renders",
    roots=("autobot-slm-backend/ansible",),
)


def _walk(node):
    """Every task in execution order, descending into plays and block/rescue/always."""
    if isinstance(node, list):
        for item in node:
            yield from _walk(item)
    elif isinstance(node, dict):
        yield node
        for key in _PLAY_KEYS:
            yield from _walk(node.get(key))


def _load(path: Path):
    try:
        return list(_walk(yaml.safe_load(path.read_text(encoding="utf-8"))))
    except yaml.YAMLError:
        return []  # a Jinja-templated file, not a task list


def _module(task: dict, names=("template", "copy")) -> dict | None:
    for name in names:
        mod = task.get(f"ansible.builtin.{name}", task.get(name))
        if isinstance(mod, dict):
            return mod
    return None


def _secret_writes_without_diff_false(tasks) -> list[str]:
    bad = []
    for t in tasks:
        mod = _module(t)
        if mod and _SECRET_FILE.search(f"{mod.get('dest', '')} {mod.get('src', '')}") and t.get("diff") is not False:
            bad.append(f"{t.get('name')} -> {mod.get('dest')}")
    return bad


def test_every_env_or_secrets_write_in_every_ansible_file_hides_its_diff() -> None:
    files, checked, bad = REACH.examined(ROOT), 0, []
    for path in files:
        tasks = _load(path)
        checked += sum(
            1 for t in tasks if (m := _module(t)) and _SECRET_FILE.search(f"{m.get('dest', '')} {m.get('src', '')}")
        )
        bad += [f"{path.relative_to(ROOT)}: {b}" for b in _secret_writes_without_diff_false(tasks)]
    REACH.completed(len(files), ROOT)
    assert checked >= 25, f"only {checked} env/secrets writes seen over {len(files)} files: the sweep lost its reach"
    assert bad == [], "env/secrets written without `diff: false`:\n" + "\n".join(bad)


def test_control_a_secret_write_without_diff_false_is_caught() -> None:
    broken = [{"name": "x", "ansible.builtin.copy": {"dest": "/etc/app/agent-secrets.env", "content": "k"}}]
    assert _secret_writes_without_diff_false(broken) == ["x -> /etc/app/agent-secrets.env"]
    assert _secret_writes_without_diff_false([{**broken[0], "diff": False}]) == []
    assert _secret_writes_without_diff_false([{"name": "u", "ansible.builtin.copy": {"dest": "/etc/x.conf"}}]) == []


# --- the root-key reader precedes every render of a template that writes the key ----------------


def _key_templates() -> set[str]:
    names = {
        Path(f).name for f in tracked_paths(ROOT, "*.j2") if "/ansible/" in f and _KEY in (ROOT / f).read_text("utf-8")
    }
    return names - {_SOURCE_TEMPLATE}


def _renders_before_reading(tasks, key_templates: set[str]) -> list[str]:
    """Names of renders of a key-writing template with no reader include earlier in the same file."""
    read, bad = False, []
    for t in tasks:
        inc = t.get("ansible.builtin.include_tasks", t.get("include_tasks"))
        inc = inc.get("file") if isinstance(inc, dict) else inc
        read = read or (isinstance(inc, str) and inc.endswith(_READERS))
        mod = _module(t, ("template",))
        if mod and Path(str(mod.get("src"))).name in key_templates and not read:
            bad.append(str(t.get("name")))
    return bad


def test_every_render_of_a_root_key_template_is_preceded_by_the_reader() -> None:
    templates, renders, bad = _key_templates(), 0, []
    assert {"backend.env.j2", "ai-stack.env.j2"} <= templates, f"key templates moved: {sorted(templates)}"
    files = REACH.examined(ROOT)
    for path in files:
        tasks = _load(path)
        renders += sum(
            1 for t in tasks if (m := _module(t, ("template",))) and Path(str(m.get("src"))).name in templates
        )
        bad += [f"{path.relative_to(ROOT)}: {b}" for b in _renders_before_reading(tasks, templates)]
    REACH.completed(len(files), ROOT)
    assert renders >= 7, f"only {renders} key-template renders seen: the sweep lost its reach"
    assert bad == [], "root-key templates rendered with no reader before them:\n" + "\n".join(bad)


def test_control_a_render_with_no_reader_before_it_is_caught() -> None:
    render = {"name": "r", "ansible.builtin.template": {"src": "../roles/backend/templates/backend.env.j2"}}
    reader = {
        "name": "k",
        "ansible.builtin.include_tasks": {"file": "../roles/backend/tasks/read_secrets_root_key.yml"},
    }
    assert _renders_before_reading([render], {"backend.env.j2"}) == ["r"]
    assert _renders_before_reading([render, reader], {"backend.env.j2"}) == ["r"], "a reader AFTER does not count"
    assert _renders_before_reading([reader, render], {"backend.env.j2"}) == []


# --- populated SLM file -> reader -> rendered env, offline ----------------------------------------

_ANSIBLE = ROOT / "autobot-slm-backend" / "ansible"
_SHARED = _ANSIBLE / "_shared" / "tasks" / "read_slm_secrets_root_key.yml"
_ENV = jinja2.Environment(undefined=jinja2.ChainableUndefined)  # nosec B701 -- repo-owned templates, test data
_ENV.filters.update(bool=lambda v: str(v).lower() in ("1", "true", "yes"), dirname=lambda v: str(v).rsplit("/", 1)[0])


def _read_like_the_reader(slm_file: str) -> str:
    """The reader's own grep pattern and unquote filter, applied to a file body (what `command` + set_fact do)."""
    tasks = yaml.safe_load(_SHARED.read_text(encoding="utf-8"))
    argv = next(t for t in tasks if "ansible.builtin.command" in t)["ansible.builtin.command"]["argv"]
    pcre = next(a for a in argv if "AUTOBOT_SECRETS_ROOT_KEY" in a)
    pattern = re.compile(pcre.replace(r"\K", "(?P<key>").replace(r"\s", r"[ \t]") + ")")
    hits = [m.group("key") for ln in slm_file.splitlines() if (m := pattern.match(ln))]
    expose = next(t for t in tasks if "set_fact" in str(t) and "_slm_root_key_read" in str(t))
    unquote = expose["ansible.builtin.set_fact"]["_slm_root_key_read"]
    quotes = re.search(r"regex_replace\('(.+?)', ''\)|regex_replace\(\"(.+?)\", ''\)", unquote)
    assert quotes or "regex_replace" in unquote, "the reader no longer unquotes: re-point this test"
    value = (hits[0] if hits else "").strip()
    return re.sub(r"^[\"']|[\"']$", "", value)


def _rendered_key_lines(rel: str, key: str) -> list[str]:
    text = (_ANSIBLE / rel).read_text(encoding="utf-8")
    return [
        ln for ln in _ENV.from_string(text).render(autobot_secrets_root_key=key).splitlines() if ln.startswith(_KEY)
    ]


def test_a_populated_slm_file_reaches_both_service_envs_and_a_tag_filtered_run_reads_it() -> None:
    slm_file = "# SLM secrets\nOTHER=1\nexport AUTOBOT_SECRETS_ROOT_KEY='root-key-sample'\n"  # pragma: allowlist secret
    key = _read_like_the_reader(slm_file)
    assert key == "root-key-sample"
    for rel in ("roles/backend/templates/backend.env.j2", "roles/ai-stack/templates/ai-stack.env.j2"):
        assert _rendered_key_lines(rel, key) == [f"{_KEY}=root-key-sample"], rel
    # `--tags config`: every include of the reader carries `config` in the tags it applies to the reader's tasks.
    for rel in ("roles/ai-stack/tasks/env_files.yml", "roles/backend/tasks/read_secrets_root_key.yml"):
        inc = next(t for t in _load(_ANSIBLE / rel) if _SHARED.name in str(t.get("ansible.builtin.include_tasks")))
        assert "config" in inc["ansible.builtin.include_tasks"]["apply"]["tags"], rel


def test_controls_an_empty_or_commented_slm_file_yields_no_key() -> None:
    assert _read_like_the_reader("") == ""
    assert _read_like_the_reader("# AUTOBOT_SECRETS_ROOT_KEY=nope\nMY_AUTOBOT_SECRETS_ROOT_KEY=x\n") == ""
    assert _read_like_the_reader('AUTOBOT_SECRETS_ROOT_KEY="quoted"\n') == "quoted"  # pragma: allowlist secret
