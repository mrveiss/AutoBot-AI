# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#16627 (P1b of #13568): the SLM generates the Redis credential once, and every
consumer reads it back and authenticates as ``default`` while the server stays nopass.

The role YAML is parsed and the touched Jinja lines are rendered; nothing runs against
a host.
"""

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")
jinja2 = pytest.importorskip("jinja2")

_ANSIBLE = Path(__file__).resolve().parents[1] / "ansible"
_ROLES = _ANSIBLE / "roles"
_SLM_TASKS = "roles/slm_manager/tasks/main.yml"
_READ_TASK = "read_redis_password.yml"

#: Stand-in values the Jinja lines are rendered with -- not credentials.
_PW = "pw-sample"  # pragma: allowlist secret
_LEGACY_PW = "legacy-sample"  # pragma: allowlist secret
_PINNED_PW = "pinned-sample"  # pragma: allowlist secret


def _text(rel: str) -> str:
    return (_ANSIBLE / rel).read_text(encoding="utf-8")


def _tasks(rel: str) -> list:
    return yaml.safe_load(_text(rel)) or []


def _index(tasks: list, needle: str) -> int:
    for i, task in enumerate(tasks):
        if needle in task.get("name", ""):
            return i
    raise AssertionError(f"no task named like {needle!r}")


def _render(source: str, env: dict | None = None, **variables) -> str:
    environment = jinja2.Environment()
    environment.globals["lookup"] = lambda _kind, key: (env or {}).get(key, "")
    return environment.from_string(source).render(**variables)


# --- generation (#16627 AC1) --------------------------------------------------------


def test_a_fresh_install_generates_the_password_once_and_keeps_a_provided_one():
    tasks = _tasks(_SLM_TASKS)
    gen = next(t for t in tasks if "slm_redis_password" in (t.get("ansible.builtin.set_fact") or {}))
    value = gen["ansible.builtin.set_fact"]["slm_redis_password"]
    assert "lookup('password'" in value
    assert "if (slm_redis_password" in value, "a pinned value must win over generation"
    assert gen["when"] == "not slm_secrets_stat.stat.exists"
    assert gen["no_log"] is True


def test_existing_installs_are_backfilled_with_the_username_before_the_password():
    tasks = _tasks(_SLM_TASKS)
    user = _index(tasks, "Add AUTOBOT_REDIS_USERNAME")
    password = _index(tasks, "Add AUTOBOT_REDIS_PASSWORD")
    assert user < password, "a generated password never lands before its username"
    for key in ("AUTOBOT_REDIS_USERNAME", "AUTOBOT_REDIS_PASSWORD"):
        check = tasks[_index(tasks, f"Check if {key} present")]
        assert f"grep -q '^{key}=.\\+'" in check["ansible.builtin.shell"]["cmd"], "append only when absent or empty"
        edit = tasks[_index(tasks, f"Add {key}")]["ansible.builtin.lineinfile"]
        assert edit["regexp"] == f"^{key}="
        assert edit["create"] is False
    assert tasks[password]["no_log"] is True


def test_a_username_is_only_backfilled_beside_a_password_the_slm_generates():
    """An operator's existing AUTOBOT_REDIS_PASSWORD may be the requirepass the legacy playbooks
    render; a username beside it would switch that enforcement off, so it is left alone."""
    tasks = _tasks(_SLM_TASKS)
    assert _index(tasks, "Check if AUTOBOT_REDIS_PASSWORD present") < _index(tasks, "Add AUTOBOT_REDIS_USERNAME")
    assert "_slm_redis_pw_check.rc != 0" in tasks[_index(tasks, "Add AUTOBOT_REDIS_USERNAME")]["when"]


def test_the_secrets_template_carries_both_keys_with_the_username_first():
    text = (_ROLES / "slm_manager" / "templates" / "slm-secrets.env.j2").read_text(encoding="utf-8")
    user = text.index("AUTOBOT_REDIS_USERNAME={{ slm_redis_username }}")
    password = text.index("AUTOBOT_REDIS_PASSWORD={{ slm_redis_password }}")
    assert user < password


def test_the_slm_defaults_generate_and_send_as_default():
    defaults = yaml.safe_load((_ROLES / "slm_manager" / "defaults" / "main.yml").read_text(encoding="utf-8"))
    assert defaults["slm_redis_password"] == ""
    assert defaults["slm_redis_username"] == "default"


# --- the shared read (owner decision: on the SLM host) -------------------------------


def test_the_shared_read_runs_once_on_the_slm_host():
    tasks = _tasks(f"_shared/tasks/{_READ_TASK}")
    *reads, expose = tasks
    for task in reads:
        assert task["delegate_to"] == "localhost", task["name"]
        assert task["run_once"] is True, task["name"]
        assert task["become"] is False, task["name"]
    probe = next(t for t in reads if "AUTOBOT_REDIS_PASSWORD" in t["name"])
    assert probe["no_log"] is True
    assert set(expose["ansible.builtin.set_fact"]) == {"_redis_password_read", "_redis_username_read"}


# --- consumers (#16627 AC2) ----------------------------------------------------------

_CONSUMERS = [
    ("roles/backend/tasks/main.yml", "backend_redis_password", "backend_redis_username", "backend.env.j2"),
    ("roles/backend/tasks/env_only.yml", "backend_redis_password", "backend_redis_username", "backend.env.j2"),
    ("roles/redis/tasks/main.yml", "redis_client_password", "redis_username", "Wait for Redis to be ready"),
    ("roles/ai-stack/tasks/main.yml", "ai_redis_password", "ai_redis_username", "ai-stack.env.j2"),
]


def _first_use(tasks: list, marker: str) -> int:
    """Index of the first top-level task whose data mentions *marker* (a block counts)."""
    for i, task in enumerate(tasks):
        if marker in str(task):
            return i
    raise AssertionError(f"no task uses {marker!r}")


@pytest.mark.parametrize(("rel", "password_var", "username_var", "use"), _CONSUMERS)
def test_each_consumer_reads_then_adopts_before_it_uses_the_credential(rel, password_var, username_var, use):
    tasks = _tasks(rel)
    read = next(i for i, t in enumerate(tasks) if str(t.get("ansible.builtin.include_tasks", "")).endswith(_READ_TASK))
    adopt = next(
        i for i, t in enumerate(tasks) if password_var in (t.get("ansible.builtin.set_fact") or {}) and i > read
    )
    assert read < adopt < _first_use(tasks, use)

    facts = tasks[adopt]["ansible.builtin.set_fact"]
    assert facts[password_var] == "{{ _redis_password_read }}"
    assert "_redis_username_read" in facts[username_var], "the username is set together with the password"
    when = " ".join(tasks[adopt]["when"])
    assert "_redis_password_read" in when and "length > 0" in when
    assert f"({password_var} | default('') | trim) | length == 0" in when, "never replace a set password"
    assert tasks[adopt]["no_log"] is True


@pytest.mark.parametrize("rel", sorted({c[0] for c in _CONSUMERS}))
def test_no_consumer_generates_a_redis_password(rel):
    assert "lookup('password'" not in _text(rel)


def test_the_role_clients_send_the_client_credential_and_the_server_is_untouched():
    exporter = (_ROLES / "redis" / "templates" / "redis_exporter.service.j2").read_text(encoding="utf-8")
    assert 'REDIS_PASSWORD={{ redis_client_password }}"' in exporter
    assert "{{ redis_password }}" not in exporter
    ping = _tasks("roles/redis/tasks/main.yml")[_index(_tasks("roles/redis/tasks/main.yml"), "Wait for Redis")]
    assert "-a {{ redis_client_password }}" in ping["command"]
    defaults = yaml.safe_load((_ROLES / "redis" / "defaults" / "main.yml").read_text(encoding="utf-8"))
    assert defaults["redis_client_password"] == "{{ redis_password }}"
    server = (_ROLES / "redis" / "templates" / "redis-stack.conf.j2").read_text(encoding="utf-8")
    # #17434/#17551 re-keyed this from a literal to the property it guards; the
    # guarantee is NOT weakened. The template now normalises the credential once
    # into `_redis_auth`, so `protected-mode` and `requirepass` cannot disagree,
    # and emits `requirepass {{ _redis_auth }}`. Pinning the old spelling
    # `requirepass {{ redis_password }}` would pin the BUGGY shape: under it an
    # empty password rendered a bare `requirepass `, which is #17434's defect.
    # What #16627 guarantees is that the SERVER credential derives from
    # `redis_password` and never from `redis_client_password` -- asserted as a
    # chain, so a future change routing it through the client credential fails.
    # A Jinja comment cannot reach the rendered config, so the "never the client
    # credential" check is made against the DIRECTIVES, not the file's prose --
    # otherwise a comment explaining the redis_password/redis_client_password
    # split trips a guard about what the server actually sends.
    directives = re.sub(r"\{#.*?#\}", "", server, flags=re.S)
    auth = re.search(r"\{%\s*set\s+_redis_auth\s*=\s*(.+?)%\}", directives)
    assert auth, "the server template no longer normalises its credential into _redis_auth"
    assert "redis_password" in auth.group(1), "the server credential must derive from redis_password"
    assert "redis_client_password" not in auth.group(1)
    assert "requirepass {{ _redis_auth }}" in directives
    assert "redis_client_password" not in directives


def test_the_ai_stack_env_renders_a_username_whenever_it_renders_the_password():
    """#16678: the username always travels with the password -- `default` unless one is configured."""
    text = (_ROLES / "ai-stack" / "templates" / "ai-stack.env.j2").read_text(encoding="utf-8")
    block = re.search(r"\{% if ai_redis_password \| length > 0 %\}.*?\{% endif %\}", text, re.S)
    assert block, "the Redis credential block moved"
    both = _render(block.group(0), ai_redis_password=_PW, ai_redis_username="svc")
    assert f"REDIS_PASSWORD={_PW}" in both and "REDIS_USERNAME=svc" in both
    alone = _render(block.group(0), ai_redis_password=_PW, ai_redis_username="")
    assert f"REDIS_PASSWORD={_PW}" in alone and "REDIS_USERNAME=default" in alone
    assert _render(block.group(0), ai_redis_password="", ai_redis_username="default").strip() == ""


# --- the legacy playbooks: requirepass never from the client credential -------------

_PLAYBOOK_REQUIREPASS = [
    ("playbooks/deploy-hybrid-docker.yml", "REDIS_ARGS="),
    ("playbooks/deploy-native-services.yml", "requirepass {{"),
]


def _requirepass_line(rel: str, marker: str) -> str:
    return next(line for line in _text(rel).splitlines() if marker in line and "{% if" in line)


@pytest.mark.parametrize(("rel", "marker"), _PLAYBOOK_REQUIREPASS)
def test_the_slm_client_credential_never_turns_enforcement_on(rel, marker):
    line = _requirepass_line(rel, marker)
    slm_env = {"AUTOBOT_REDIS_PASSWORD": _PW, "AUTOBOT_REDIS_USERNAME": "default"}
    assert "requirepass" not in _render(line, env=slm_env)


@pytest.mark.parametrize(("rel", "marker"), _PLAYBOOK_REQUIREPASS)
def test_the_legacy_env_and_an_explicit_password_still_set_requirepass(rel, marker):
    line = _requirepass_line(rel, marker)
    assert f"requirepass {_LEGACY_PW}" in _render(line, env={"AUTOBOT_REDIS_PASSWORD": _LEGACY_PW})
    assert f"requirepass {_PINNED_PW}" in _render(line, env={}, autobot_redis_password=_PINNED_PW)
    # An explicit server password is enforced even where the SLM env carries a username.
    slm_env = {"AUTOBOT_REDIS_PASSWORD": _PW, "AUTOBOT_REDIS_USERNAME": "default"}
    assert f"requirepass {_PINNED_PW}" in _render(line, env=slm_env, autobot_redis_password=_PINNED_PW)


@pytest.mark.parametrize("rel", ["playbooks/deploy-hybrid-docker.yml", "playbooks/deploy-native-services.yml"])
def test_every_rendered_redis_password_travels_with_a_username(rel):
    lines = _text(rel).splitlines()
    rendered = [i for i, line in enumerate(lines) if re.search(r"\bREDIS_PASSWORD=", line)]
    assert rendered, "the playbook no longer renders REDIS_PASSWORD -- update this guard"
    for i in rendered:
        assert "REDIS_USERNAME=" in lines[i + 1], f"{rel}:{i + 1} sends a password without a username"
