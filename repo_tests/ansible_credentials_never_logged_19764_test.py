# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A task that sends or receives credentials never writes them to a log (#19764).

Ansible logs each module invocation's arguments on the target, so a ``uri`` task carrying an
``Authorization`` header, an API key or a password in its body put a live bearer token in a
node's journal (2026-10-27). Every such task sets ``no_log: true``; and no message prints the
whole response of one -- ``no_log`` hides the invocation, not a later ``fail_msg`` that dumps
``<result>.json`` (the login response holds the token).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ANS = "autobot-slm-backend/ansible"
_HTTP_MODULES = ("ansible.builtin.uri", "uri", "ansible.builtin.get_url", "get_url")
_SECRET = re.compile(r"Authorization|Bearer|X-API-Key|api[_-]?key|password|token|secret", re.IGNORECASE)
_SECRET_ARGS = ("headers", "body", "url_password", "client_key")
_MESSAGE_MODULES = (
    "ansible.builtin.debug",
    "debug",
    "ansible.builtin.fail",
    "fail",
    "ansible.builtin.assert",
    "assert",
)
_CHILD_LISTS = ("block", "rescue", "always", "tasks", "pre_tasks", "post_tasks", "handlers")


class _AnsibleLoader(yaml.SafeLoader):
    """SafeLoader that reads Ansible's custom tags (``!vault``, ``!unsafe``) as plain scalars.

    A playbook carrying an inline ``!vault`` value is valid Ansible; ``safe_load`` refuses it, and
    a guard that skipped it would count the file as covered while judging none of its tasks.
    """


_AnsibleLoader.add_multi_constructor("!", lambda loader, _suffix, node: loader.construct_scalar(node))
_TRUE = frozenset({"true", "yes", "on", "1"})


def _no_log_on(task: dict) -> bool:
    """Ansible's boolean rule: only a literal truthy value counts; ``"false"`` or a template does not."""
    value = task.get("no_log")
    return value is True or (isinstance(value, (str, int)) and str(value).strip().lower() in _TRUE)


def _tasks(node):
    if isinstance(node, list):
        for item in node:
            yield from _tasks(item)
    elif isinstance(node, dict):
        yield node
        for key in _CHILD_LISTS:
            if key in node:
                yield from _tasks(node[key])


def _http_args(task: dict) -> dict | None:
    """The module arguments of a uri/get_url task, in the module-key or the ``action:`` form."""
    direct = next((task[m] for m in _HTTP_MODULES if isinstance(task.get(m), dict)), None)
    if direct is not None:
        return direct
    action = task.get("action")
    if isinstance(action, dict) and action.get("module") in _HTTP_MODULES:
        return {**action, **(task.get("args") or {})}
    if isinstance(action, str) and action.split()[0] in _HTTP_MODULES:
        return {"inline": action, **(task.get("args") or {})}
    return None


def _carries_credentials(task: dict) -> bool:
    args = _http_args(task)
    if args is None:
        return False
    if args.get("url_password") or args.get("client_key"):
        return True  # presence alone: the value is a template the secret pattern cannot see
    return any(_SECRET.search(str(args.get(key, ""))) for key in ("headers", "body", "url", "inline"))


def _message_text(task: dict) -> str:
    return " ".join(str(task.get(m, "")) for m in _MESSAGE_MODULES)


def _debug_var(task: dict) -> str:
    args = next((task[m] for m in ("ansible.builtin.debug", "debug") if isinstance(task.get(m), dict)), {})
    return str(args.get("var", "")).strip()


def _whole_response_dumps(tasks: list[dict], secret_results: set[str]) -> list[str]:
    """Messages that print ``<secret result>.json`` / ``.content`` whole, or a credential field of it."""
    found = []
    for task in tasks:
        if _no_log_on(task):
            continue
        text, var, label = _message_text(task), _debug_var(task), task.get("name", "<unnamed>")
        for name in secret_results:
            if var in (name, f"{name}.json", f"{name}.content") or re.search(
                rf"\b{re.escape(name)}\.(json|content)\s*(\||}}|$)", text
            ):
                found.append(f"{label} prints {name} whole")
            elif re.search(rf"\b{re.escape(name)}\.json\.\w*(token|password|secret)\w*", text, re.IGNORECASE):
                found.append(f"{label} prints a credential field of {name}")
    return found


def findings_in(text: str) -> list[str]:
    """Every credential leak in one YAML document's text."""
    docs = yaml.load_all(text, Loader=_AnsibleLoader)  # noqa: S506 -- SafeLoader subclass; every document
    tasks = [t for doc in docs for t in _tasks(doc)]
    secret = [t for t in tasks if _carries_credentials(t)]
    found = [f"{t.get('name', '<unnamed>')} sends credentials without no_log" for t in secret if not _no_log_on(t)]
    results = {t["register"] for t in secret if isinstance(t.get("register"), str)}
    return found + _whole_response_dumps(tasks, results)


def _ansible_yaml(root: Path) -> list[str]:
    try:
        return [p for p in tracked_paths(root, _ANS) if p.endswith((".yml", ".yaml"))]
    except EmptyEnumeration:
        return []


REACH_FILES = declare(
    "ansible-credentials-never-logged",
    discover=_ansible_yaml,
    # Mid-window, from REACH_FILES.window(); the arithmetic is on the PR, not here.
    floor=317,
    what="ansible yml/yaml files, scanned for credential-bearing http tasks and messages that dump their response",
    roots=(_ANS,),
    growth=50,
)


def test_no_ansible_task_logs_credentials() -> None:
    root = repo_root()
    leaks, parsed, unparsed = [], [], []
    for rel in REACH_FILES.examined(root):
        try:
            leaks += [f"{rel}: {f}" for f in findings_in((root / rel).read_text(encoding="utf-8"))]
            parsed.append(rel)
        except yaml.YAMLError as exc:
            unparsed.append(f"{rel}: {str(exc).splitlines()[0]}")
    REACH_FILES.completed(parsed)  # the floor binds to files judged, not files listed
    assert not unparsed, "ansible files the guard could not judge (#19764):\n  " + "\n  ".join(unparsed)
    assert not leaks, "credentials reach a log (#19764):\n  " + "\n  ".join(leaks)


_PLANTED = """
- name: login
  ansible.builtin.uri:
    url: "https://slm/api/auth/login"
    method: POST
    body_format: json
    body: {username: admin, password: "{{ pw }}"}
  register: login_result
- name: report
  ansible.builtin.fail:
    msg: "login failed: {{ login_result.json | default({}) }}"
"""


def test_a_planted_credential_task_without_no_log_is_flagged() -> None:
    assert findings_in(_PLANTED) == [
        "login sends credentials without no_log",
        "report prints login_result whole",
    ]


def test_no_log_and_a_single_field_message_are_accepted() -> None:
    fixed = _PLANTED.replace("  register: login_result", "  register: login_result\n  no_log: true").replace(
        "{{ login_result.json | default({}) }}", "{{ login_result.status }}"
    )
    assert findings_in(fixed) == []


def test_a_header_bearer_token_counts_as_credentials() -> None:
    task = '- name: sync\n  uri: {url: "https://x", headers: {Authorization: "Bearer {{ t }}"}}\n'
    assert findings_in(task) == ["sync sends credentials without no_log"]


def test_a_message_printing_the_token_field_is_flagged() -> None:
    leak = _PLANTED.replace("  register: login_result", "  register: login_result\n  no_log: true").replace(
        "{{ login_result.json | default({}) }}", "{{ login_result.json.access_token }}"
    )
    assert findings_in(leak) == ["report prints a credential field of login_result"]


@pytest.mark.parametrize(
    "task",
    [
        '- name: t\n  action: {module: ansible.builtin.uri, url: "https://x", headers: {Authorization: "Bearer {{ t }}"}}\n',
        '- name: t\n  action: ansible.builtin.uri\n  args: {url: "https://x", headers: {Authorization: "Bearer {{ t }}"}}\n',
        '- name: t\n  uri: {url: "https://x", url_username: u, url_password: "{{ pw }}"}\n',
        '- name: t\n  uri: {url: "https://x/api?access_token={{ t }}"}\n',
        '- name: t\n  uri: {url: "https://x", headers: {Authorization: "Bearer {{ t }}"}}\n  no_log: "false"\n',
    ],
    ids=["action-mapping", "action-string-args", "url-password", "token-in-url", "no-log-false-string"],
)
def test_every_ansible_spelling_of_a_credential_task_is_flagged(task: str) -> None:
    assert findings_in(task) == ["t sends credentials without no_log"]


def test_a_public_get_without_credentials_is_not_flagged() -> None:
    assert findings_in('- name: t\n  uri: {url: "https://x/health", method: GET}\n') == []


def test_a_debug_var_dump_of_the_response_is_flagged() -> None:
    leak = _PLANTED.replace("  register: login_result", "  register: login_result\n  no_log: true").replace(
        '  ansible.builtin.fail:\n    msg: "login failed: {{ login_result.json | default({}) }}"',
        "  ansible.builtin.debug:\n    var: login_result.json",
    )
    assert findings_in(leak) == ["report prints login_result whole"]


def test_an_inline_vault_value_is_parsed_not_skipped() -> None:
    vaulted = (
        "- name: t\n  uri:\n    url: https://x\n    url_password: !vault |\n"
        "      $ANSIBLE_VAULT;1.1;AES256\n      6162\n"
    )
    assert findings_in(vaulted) == ["t sends credentials without no_log"]


def test_every_document_of_a_multi_document_file_is_judged() -> None:
    two = '- name: ok\n  uri: {url: "https://x/health"}\n---\n- name: t\n  uri: {url: "https://x", headers: {Authorization: "Bearer {{ t }}"}}\n'
    assert findings_in(two) == ["t sends credentials without no_log"]
