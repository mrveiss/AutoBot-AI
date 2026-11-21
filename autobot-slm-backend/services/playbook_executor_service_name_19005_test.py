# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`execute_playbook` refuses a non-unit-name `service_name` and hands Ansible caller vars as `!unsafe` (#19005).

`manage-service.yml` references `{{ service_name }}`, which Ansible templates when the extra var is
read. The executor is the one chokepoint every caller goes through, so it validates the name before
anything is synced, staged or spawned, and writes caller-supplied values so they are never templated.

The real executor is loaded from disk (the package conftest stubs `services.*`); no Ansible binary
and no subprocess is involved -- `asyncio.create_subprocess_exec` is patched and asserted unawaited.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yaml

from services.unit_names import UNIT_NAME_EXTRA_VAR_KEYS

_SLM_ROOT = Path(__file__).resolve().parent.parent
if str(_SLM_ROOT) not in sys.path:
    sys.path.insert(0, str(_SLM_ROOT))


def _load_real_playbook_executor():
    spec = importlib.util.spec_from_file_location(
        "playbook_executor_under_service_name_19005_test", _SLM_ROOT / "services" / "playbook_executor.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["playbook_executor_under_service_name_19005_test"] = module
    spec.loader.exec_module(module)
    return module


playbook_executor = _load_real_playbook_executor()

_HOSTILE = [
    "{{ lookup('pipe', 'id') }}",
    "a b",
    'x"y',
    "a;b",
    "a\nb",
    "-H",
    "x" * 300,
    123,
    "",
    "../x",
    "redis\u2010stack",
    "r\u00e9dis",
]
_SECRET = "s3cr3t-{{ not_a_template }}"  # pragma: allowlist secret  # nosec B105  # test fixture


class _AnsibleLikeLoader(yaml.SafeLoader):
    """SafeLoader that reads `!unsafe` as a plain scalar, as Ansible's loader does (minus the taint)."""


_AnsibleLikeLoader.add_constructor("!unsafe", lambda loader, node: loader.construct_scalar(node))
_BODY = "- hosts: all\n  tasks: []\n"


class _Run:
    """One `execute_playbook` call with every collaborator but the validator faked."""

    def __init__(self, tmp_path, monkeypatch):
        ansible_dir = tmp_path / "ansible"
        ansible_dir.mkdir()
        (ansible_dir / "manage-service.yml").write_text(_BODY, encoding="utf-8")
        inventory = tmp_path / "inv.yml"
        inventory.write_text("all:\n", encoding="utf-8")
        self.stage = tmp_path / "stage"
        self.stage.mkdir()
        self.executor = playbook_executor.PlaybookExecutor(ansible_dir=ansible_dir)
        self.sync = AsyncMock(return_value=None)
        self.written: dict = {}

        async def _run_subprocess(cmd, *_a, **_kw):
            evars = next(a for a in cmd if a.startswith("@"))[1:]
            self.written["text"] = await asyncio.to_thread(Path(evars).read_text, encoding="utf-8")
            return {"output": "ok", "returncode": 0, "timed_out": False}

        self.run_subprocess = AsyncMock(side_effect=_run_subprocess)
        monkeypatch.setattr(self.executor, "_update_code_source", self.sync)
        monkeypatch.setattr(self.executor, "_build_dynamic_inventory", AsyncMock(return_value=inventory))
        monkeypatch.setattr(self.executor, "_stage_dir_for_run", lambda _detach: str(self.stage))
        monkeypatch.setattr(self.executor, "_run_subprocess", self.run_subprocess)
        monkeypatch.setattr(self.executor, "_find_ansible_playbook", lambda: "ansible-playbook")
        monkeypatch.setattr(self.executor, "_build_ansible_env", dict)
        monkeypatch.setattr(playbook_executor, "fetch_deploy_secrets", AsyncMock(return_value={"hf_token": _SECRET}))

    def run_playbook(self, extra_vars):
        with patch.object(asyncio, "create_subprocess_exec", new=AsyncMock()) as spawn:
            self.spawn = spawn
            return asyncio.run(self.executor.execute_playbook("manage-service.yml", extra_vars=extra_vars))


@pytest.mark.parametrize("key", sorted(UNIT_NAME_EXTRA_VAR_KEYS))
@pytest.mark.parametrize("name", _HOSTILE, ids=lambda n: repr(n)[:30])
def test_a_hostile_unit_extra_var_raises_and_nothing_is_synced_or_spawned(tmp_path, monkeypatch, name, key):
    run = _Run(tmp_path, monkeypatch)

    with pytest.raises(ValueError, match="invalid systemd unit name"):
        run.run_playbook({key: name, "service_action": "restarted"})

    run.sync.assert_not_awaited()
    run.run_subprocess.assert_not_awaited()
    run.spawn.assert_not_awaited()


def test_a_valid_service_name_proceeds_to_the_spawn(tmp_path, monkeypatch):
    run = _Run(tmp_path, monkeypatch)

    result = run.run_playbook({"service_name": "redis-stack.service", "service_action": "restarted"})

    assert result["success"] is True
    run.run_subprocess.assert_awaited_once()


@pytest.mark.parametrize("key", sorted(UNIT_NAME_EXTRA_VAR_KEYS))
def test_a_valid_unit_extra_var_proceeds_for_every_unit_bearing_key(tmp_path, monkeypatch, key):
    run = _Run(tmp_path, monkeypatch)

    assert run.run_playbook({key: "redis-stack-server"})["success"] is True
    run.run_subprocess.assert_awaited_once()


def test_extra_vars_without_a_service_name_are_not_validated(tmp_path, monkeypatch):
    run = _Run(tmp_path, monkeypatch)

    assert run.run_playbook({"role_name": "{{ anything }}"})["success"] is True
    assert run.run_playbook(None)["success"] is True


def test_caller_vars_are_written_unsafe_and_a_merged_secret_round_trips(tmp_path, monkeypatch):
    run = _Run(tmp_path, monkeypatch)

    run.run_playbook({"service_name": "redis-stack.service", "service_action": "restarted"})

    text = run.written["text"]
    assert "service_name: !unsafe 'redis-stack.service'" in text
    assert "service_action: !unsafe 'restarted'" in text
    assert "!unsafe" not in text.split("hf_token:")[1].splitlines()[0], "merged secrets must stay plain"
    assert _AnsibleLikeLoader(text).get_single_data()["hf_token"] == _SECRET


def test_an_unsafe_tag_is_written_for_template_syntax_instead_of_the_raw_string(tmp_path):
    from services.inventory_builder import write_temp_extra_vars

    path = write_temp_extra_vars(
        {"a": "{{ x }}", "n": 3, "l": ["{{ y }}", 1], "secret": "{{ z }}"}, str(tmp_path), unsafe_keys=("a", "n", "l")
    )

    lines = path.read_text(encoding="utf-8").splitlines()
    assert any(line.startswith("a: !unsafe") for line in lines)
    assert "n: 3" in lines
    assert "- !unsafe '{{ y }}'" in "\n".join(lines)
    assert "- 1" in lines
    assert not any(line.startswith("secret: !unsafe") for line in lines)
    assert oct(path.stat().st_mode & 0o777) == "0o600"


def test_secrets_the_executor_merges_are_written_plain_when_the_caller_passes_none(tmp_path, monkeypatch):
    """The wizard passes no extra vars: its secrets arrive only through the executor's own merge (#19005)."""
    run = _Run(tmp_path, monkeypatch)

    run.run_playbook(None)

    assert "!unsafe" not in run.written["text"]
    assert _AnsibleLikeLoader(run.written["text"]).get_single_data() == {"hf_token": _SECRET}
