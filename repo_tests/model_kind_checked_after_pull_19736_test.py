# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A pulled model is checked for the KIND its role needs, not just its name (#19736).

``_shared/tasks/assert_model_kinds.yml`` asks the model server (``ollama show`` -> Capabilities)
what each model can do. The embedding role's model must have ``embedding``, every other pulled
model ``completion``; a mismatch fails the install naming the model. These tests run the task's
real shell under ``sh`` (the shell module's default) against a fake ``ollama`` that prints a chosen
capability list, and evaluate the task's own ``when:`` conditions against that output.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest
import yaml
from repo_tests._ansible_tasks import eval_when, loop_items, play_vars, when_of
from repo_tests._paths import repo_root

_ANS = "autobot-slm-backend/ansible"
_TASK = f"{_ANS}/_shared/tasks/assert_model_kinds.yml"
_SCRIPT = f"{_ANS}/_shared/files/check_model_kinds.sh"
_BARE_METAL = "autobot-infrastructure/shared/scripts/install-bare-metal.sh"
_BARE_METAL_LIB = "autobot-infrastructure/shared/scripts/lib/pull-embedding-model.sh"
_SITES = (
    f"{_ANS}/roles/agent_config/tasks/ollama.yml",
    f"{_ANS}/playbooks/deploy-hybrid-docker.yml",
    f"{_ANS}/playbooks/deploy-native-services.yml",
    f"{_ANS}/roles/llm/tasks/main.yml",
)

# What the fake CLI answers per model: a capability list, or None for "not installed".
_CAPS = {"embedder": ["embedding"], "chatty": ["completion", "tools"], "nocaps": []}


def _tasks(rel: str) -> list[dict]:
    """Every top-level item of every document (deploy-hybrid-docker.yml is multi-document)."""
    docs = yaml.safe_load_all((repo_root() / rel).read_text(encoding="utf-8"))
    return [item for doc in docs if doc for item in doc]


def _fake_ollama(bin_dir: Path, reachable: bool = True) -> Path:
    head = ['[ "$1" = list ] && exit 0', '[ "$1" = show ] || exit 2'] if reachable else ["exit 1"]
    lines = ["#!/bin/sh", *head, 'case "$2" in']
    for model, caps in _CAPS.items():
        body = "printf '  Model\\n    arch x\\n\\n'"
        if caps:
            body += "; printf '  Capabilities\\n" + "".join(f"    {c}    \\n" for c in caps) + "\\n'"
        lines.append(f"  {model}) {body} ;;")
    lines += ["  *) echo 'Error: model not found' >&2; exit 1 ;;", "esac"]
    cli = bin_dir / "ollama"
    cli.write_text("\n".join(lines) + "\n", encoding="utf-8")
    cli.chmod(cli.stat().st_mode | stat.S_IEXEC)
    return cli


def _run(tmp_path: Path, embedding: str, completion: list[str], reachable: bool = True):
    cli = _fake_ollama(tmp_path, reachable)
    env = {
        **os.environ,
        "MODEL_CLI": str(cli),
        "EMBEDDING_MODEL": embedding,
        "COMPLETION_MODELS": "\n".join(completion),
    }
    return subprocess.run(["sh", str(repo_root() / _SCRIPT)], capture_output=True, text=True, check=False, env=env)


def _probe(tmp_path: Path, embedding: str, completion: list[str]) -> list[str]:
    out = _run(tmp_path, embedding, completion)
    assert out.returncode == 0, out.stdout + out.stderr
    return out.stdout.split("\n")[:-1]


def test_the_right_kinds_pass(tmp_path: Path) -> None:
    assert _probe(tmp_path, "embedder", ["chatty"]) == ["OK embedder embedding", "OK chatty completion"]


def test_a_chat_model_in_the_embedding_role_is_the_wrong_kind(tmp_path: Path) -> None:
    assert _probe(tmp_path, "chatty", []) == ["WRONG-KIND chatty needs=embedding has=[completion tools]"]


def test_an_embedding_model_in_a_chat_role_is_the_wrong_kind(tmp_path: Path) -> None:
    assert _probe(tmp_path, "", ["embedder"]) == ["WRONG-KIND embedder needs=completion has=[embedding]"]


def test_the_embedding_model_in_the_pull_list_is_judged_once_as_an_embedder(tmp_path: Path) -> None:
    assert _probe(tmp_path, "embedder", ["chatty", "embedder"]) == ["OK embedder embedding", "OK chatty completion"]


@pytest.mark.parametrize(("model", "line"), [("ghost", "ABSENT ghost"), ("nocaps", "UNKNOWN nocaps")])
def test_an_undescribed_model_is_reported_not_judged(tmp_path: Path, model: str, line: str) -> None:
    assert _probe(tmp_path, "", [model]) == [line]


def test_an_unreachable_model_server_fails_the_probe_instead_of_reading_absent(tmp_path: Path) -> None:
    out = _run(tmp_path, "embedder", ["chatty"], reachable=False)
    assert out.returncode != 0 and out.stdout.startswith("UNREACHABLE ")
    probe = _tasks(_TASK)[0]
    assert eval_when(probe["failed_when"], _model_kind_probe={"rc": out.returncode})
    assert not eval_when(probe["failed_when"], _model_kind_probe={"rc": 0})


def _fires(kind: str, lines: list[str]) -> bool:
    task = next(t for t in _tasks(_TASK) if kind in t)
    return eval_when(when_of(task), _model_kind_probe={"stdout_lines": lines})


@pytest.mark.parametrize(
    ("embedding", "completion", "fails", "reports"),
    [
        ("embedder", ["chatty"], False, False),
        ("chatty", [], True, False),
        ("", ["embedder"], True, False),
        ("", ["ghost", "nocaps"], False, True),
    ],
)
def test_the_install_fails_exactly_on_a_wrong_kind_verdict(
    tmp_path: Path, embedding: str, completion: list[str], fails: bool, reports: bool
) -> None:
    lines = _probe(tmp_path, embedding, completion)
    assert _fires("ansible.builtin.fail", lines) is fails
    assert _fires("ansible.builtin.debug", lines) is reports


def _includes_check(node) -> list[dict]:
    if isinstance(node, list):
        return [inc for item in node for inc in _includes_check(item)]
    if not isinstance(node, dict):
        return []
    target = node.get("ansible.builtin.include_tasks", "")
    target = target.get("file", "") if isinstance(target, dict) else str(target)
    found = [node] if target.endswith("assert_model_kinds.yml") else []
    for key in ("tasks", "block", "rescue", "always", "pre_tasks", "post_tasks"):
        found += _includes_check(node.get(key))
    return found


@pytest.mark.parametrize("site", _SITES)
def test_each_wired_pull_site_names_its_embedding_role(site: str) -> None:
    includes = _includes_check(_tasks(site))
    assert len(includes) == 1, f"{site} must run the kind check once after its pull"
    assert includes[0]["vars"]["model_kind_embedding"].startswith("{{ ")
    assert "model_kind_completion" in includes[0]["vars"]


def test_a_loop_reference_is_read_only_through_names_the_play_loads() -> None:
    assert loop_items("{{ ollama_models }}", {"ollama_models": ["a"]}) == [["a"]]
    assert loop_items("{{ ollama_models }}", {}) == []
    assert loop_items(["a", "b"], {}) == [["a", "b"]]


def test_the_hybrid_play_reads_the_embedding_model_from_the_shared_list() -> None:
    playbook = repo_root() / _SITES[1]
    names = [play_vars(p, playbook) for p in _tasks(_SITES[1]) if isinstance(p, dict) and "vars_files" in p]
    assert names and names[0]["ollama_embedding_model"] in names[0]["ollama_models"]


def test_the_task_runs_the_one_script() -> None:
    assert _tasks(_TASK)[0]["ansible.builtin.script"] == "../files/check_model_kinds.sh"
    assert (repo_root() / _TASK).parent.joinpath("../files/check_model_kinds.sh").resolve() == repo_root() / _SCRIPT


def _run_bare_metal_check(tmp_path: Path, reachable: bool = True):
    """The installer's real library, sourced, against a fake model server answering every model as ``caps``."""
    head = ['[ "$1" = list ] && exit 0', '[ "$1" = pull ] && exit 0'] if reachable else ["exit 1"]
    cli = tmp_path / "ollama"
    body = "printf '  Capabilities\\n    %s\\n\\n' \"$FAKE_CAPS\""
    cli.write_text("\n".join(["#!/bin/sh", *head, body]) + "\n", encoding="utf-8")
    cli.chmod(0o755)
    stubs = 'log_warn() { echo "WARN $*"; }; log_error() { echo "ERROR $*"; }'
    script = f'{stubs}\nsource "{repo_root() / _BARE_METAL_LIB}"\npull_embedding_model'
    return lambda caps: subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "FAKE_CAPS": caps},
    )


def test_the_bare_metal_install_stops_on_a_chat_model_in_the_embedding_role(tmp_path: Path) -> None:
    out = _run_bare_metal_check(tmp_path)("completion")
    assert out.returncode == 1 and "WRONG-KIND nomic-embed-text:latest" in out.stdout


def test_the_bare_metal_install_accepts_an_embedder(tmp_path: Path) -> None:
    out = _run_bare_metal_check(tmp_path)("embedding")
    assert out.returncode == 0 and "ERROR" not in out.stdout


def test_the_bare_metal_install_only_warns_when_the_server_is_unreachable(tmp_path: Path) -> None:
    out = _run_bare_metal_check(tmp_path, reachable=False)("embedding")
    assert out.returncode == 0 and "WARN Could not check" in out.stdout


def test_the_bare_metal_install_pulls_through_the_library() -> None:
    text = (repo_root() / _BARE_METAL).read_text(encoding="utf-8")
    assert "lib/pull-embedding-model.sh" in text
    assert "nomic-embed-text" not in text, "the name's one home is agent_config's defaults"


def _copied_scripts(tmp_path: Path, defaults: str | None) -> Path:
    """The library at its real depth in a temporary tree; defaults None leaves the Ansible tree out."""
    lib = tmp_path / "autobot-infrastructure/shared/scripts/lib/pull-embedding-model.sh"
    lib.parent.mkdir(parents=True)
    lib.write_text((repo_root() / _BARE_METAL_LIB).read_text(encoding="utf-8"), encoding="utf-8")
    if defaults is not None:
        target = tmp_path / _ANS / "roles/agent_config/defaults/main.yml"
        target.parent.mkdir(parents=True)
        target.write_text(defaults, encoding="utf-8")
    return lib


def _source_from_root(lib: Path) -> subprocess.CompletedProcess:
    """As main() runs it: set -e, sourced, then the ``cd /``, then the read the env file needs."""
    script = f'set -euo pipefail\nsource "{lib}"\ncd /\nmodel="$(embedding_model_name)"\necho "MODEL=$model"'
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False, cwd="/")


def test_an_absent_ansible_tree_stops_the_install_and_writes_no_model(tmp_path: Path) -> None:
    out = _source_from_root(_copied_scripts(tmp_path, None))
    assert out.returncode != 0
    assert "MODEL=" not in out.stdout


def test_a_defaults_file_with_no_model_stops_the_install(tmp_path: Path) -> None:
    out = _source_from_root(_copied_scripts(tmp_path, "other: 1\n"))
    assert out.returncode != 0
    assert "MODEL=" not in out.stdout


@pytest.mark.parametrize(
    "line",
    [
        'ollama_embedding_model: "m:latest"',
        "ollama_embedding_model: 'm:latest'",
        "ollama_embedding_model: m:latest  # x",
    ],
    ids=["double", "single", "bare-with-comment"],
)
def test_the_model_reads_in_any_yaml_quoting_after_the_cd(tmp_path: Path, line: str) -> None:
    out = _source_from_root(_copied_scripts(tmp_path, line + "\n"))
    assert out.returncode == 0 and out.stdout.strip() == "MODEL=m:latest"


def test_the_installer_cannot_skip_or_empty_the_model_silently() -> None:
    text = (repo_root() / _BARE_METAL).read_text(encoding="utf-8")
    assert "AUTOBOT_EMBEDDING_MODEL=${embedding_model}" in text
    assert text.index('embedding_model="$(embedding_model_name)"') < text.index(
        "AUTOBOT_EMBEDDING_MODEL=${embedding_model}"
    )
    assert "&& pull_embedding_model" not in text
    main = text[text.index("main() {") :]
    assert main.index("lib/pull-embedding-model.sh") < main.index("cd /")
