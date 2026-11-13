# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20772: every restart the updater or a role handler makes clears a start-limit park first.

A unit parked in ``failed`` by its start limit refuses a restart, so a bare ``systemd:
state=restarted`` fails the update on that node. The restarts go through the one shared task
file, which runs ``systemctl reset-failed`` and then restarts. These tests fail when a restart
task or handler anywhere under ``ansible/`` restarts a unit through the ``systemd``/``service`` module
directly, unless the site is on ``_DIRECT_RESTARTS`` with its reason.
"""

import functools
from pathlib import Path

import pytest
import yaml
from repo_tests._ansible_restart_unit import is_direct_restart, shared_include
from repo_tests._paths import repo_root

from tools.lint._scan_helpers import tracked_paths

_ANSIBLE_REL = "autobot-slm-backend/ansible"
_ANSIBLE = Path(__file__).resolve().parents[1] / "ansible"
_PLAYBOOK = _ANSIBLE / "playbooks" / "update-all-nodes.yml"
_SHARED = _ANSIBLE / "_shared" / "tasks" / "restart_unit.yml"
_ROLE_KEYS = ("ansible.builtin.include_role", "include_role", "ansible.builtin.import_role", "import_role")


class _Loader(yaml.SafeLoader):
    """SafeLoader that reads Ansible's custom tags (``!unsafe``, ``!vault``) as plain data."""


_Loader.add_multi_constructor("!", lambda loader, suffix, node: None)


def _load(path: Path) -> list:
    """Every document of the file, flattened: a list document contributes its items, any other its value.

    Handles multi-document files (``---`` x N), dict-shaped vars files and empty documents. A file
    that does not parse fails the test with its name; it is never skipped.
    """
    try:
        docs = list(yaml.load_all(path.read_text(encoding="utf-8"), Loader=_Loader))  # noqa: S506 - SafeLoader subclass
    except yaml.YAMLError as exc:
        raise AssertionError(f"{path.name} does not parse as YAML: {exc}") from exc
    flat: list = []
    for doc in docs:
        if isinstance(doc, list):
            flat.extend(doc)
        elif doc is not None:
            flat.append(doc)
    return flat


def _mappings(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _mappings(value)
    elif isinstance(node, list):
        for item in node:
            yield from _mappings(item)


def _updater_roles() -> list:
    found = set()
    for node in _mappings(_load(_PLAYBOOK)):
        for key in _ROLE_KEYS:
            if isinstance(node.get(key), dict):
                found.add(node[key]["name"])
        for entry in node.get("roles") or []:
            found.add(entry if isinstance(entry, str) else entry.get("role") or entry.get("name"))
    return sorted(found)


def _handler_files() -> list:
    paths = [_ANSIBLE / "roles" / role / "handlers" / "main.yml" for role in _updater_roles()]
    return [p for p in paths if p.is_file()]


def test_the_shared_task_clears_the_park_before_it_restarts() -> None:
    tasks = _load(_SHARED)
    modules = [next(iter(set(t) & {"ansible.builtin.command", "ansible.builtin.systemd"})) for t in tasks]
    assert modules == ["ansible.builtin.command", "ansible.builtin.systemd"]
    assert tasks[0]["ansible.builtin.command"]["argv"][:3] == ["systemctl", "reset-failed", "--"]
    assert tasks[1]["ansible.builtin.systemd"]["state"] == "restarted"
    assert tasks[0]["ansible.builtin.command"]["argv"][3] == tasks[1]["ansible.builtin.systemd"]["name"]


def test_the_updater_playbook_restarts_only_through_the_shared_task() -> None:
    mappings = list(_mappings(_load(_PLAYBOOK)))
    shared = [t for t in mappings if shared_include(t)]
    direct = [t.get("name") for t in mappings if is_direct_restart(t)]
    assert len(shared) >= 10, "control: the finder sees the playbook's restart tasks"
    assert not direct, f"these restarts do not clear a start-limit park: {direct}"


def test_every_updater_role_handler_restarts_only_through_the_shared_task() -> None:
    files = _handler_files()
    handlers = [h for f in files for h in _load(f) if isinstance(h, dict)]
    shared = [h for h in handlers if shared_include(h)]
    direct = [h.get("name") for h in handlers if is_direct_restart(h)]
    assert len(shared) >= 25, "control: the finder sees the role handlers' restarts"
    assert not direct, f"these handlers do not clear a start-limit park: {direct}"


_INCLUDE_TASKS_KEYS = ("ansible.builtin.include_tasks", "include_tasks")
#: Task keys ansible-core 2.17.14 accepts on an ``include_tasks``: `playbook/task_include.py`
#: `TaskInclude.VALID_INCLUDE_KEYWORDS`. Any other key (``become``, ``delegate_to``, ``failed_when``,
#: ``changed_when``, ``notify``, ``environment``, ...) raises "is not a valid attribute for a TaskInclude"
#: when the task list is loaded. ``apply`` is an argument of the include (`TaskInclude.OTHER_ARGS`), not a task key.
_VALID_INCLUDE_KEYS = frozenset(
    {"action", "args", "collections", "debugger", "ignore_errors", "loop", "loop_control", "loop_with", "name"}
    | {"no_log", "register", "run_once", "tags", "timeout", "vars", "when"}
)
#: A handler include also takes ``listen``: `playbook/handler_task_include.py` `HandlerTaskInclude`.
_VALID_HANDLER_INCLUDE_KEYS = _VALID_INCLUDE_KEYS | {"listen"}
#: ``with_<lookup>`` is rewritten to ``loop``/``loop_with`` by `playbook/task.py` `preprocess_data`
#: (`_preprocess_with_loop`), so any ``with_*`` key is the valid loop spelling.
_WITH_PREFIX = "with_"
#: Reach floor with headroom: 327 includes were measured over every YAML under ``ansible/`` on the day this was written.
_INCLUDE_TASKS_FLOOR = 250


def _is_include(task: dict) -> bool:
    return any(k in task for k in _INCLUDE_TASKS_KEYS)


def _invalid_include_keys(task: dict, in_handler: bool) -> list:
    valid = _VALID_HANDLER_INCLUDE_KEYS if in_handler else _VALID_INCLUDE_KEYS
    return sorted(
        k for k in task if k not in valid and k not in _INCLUDE_TASKS_KEYS and not str(k).startswith(_WITH_PREFIX)
    )


def _include_key_offenders(docs, in_handler: bool = False) -> list:
    """(name, invalid keys) of every ``include_tasks`` in ``docs`` that carries a key ansible-core rejects."""
    return [
        (t.get("name"), bad)
        for t, handler in _mappings_in_context(docs, in_handler)
        if _is_include(t) and (bad := _invalid_include_keys(t, handler))
    ]


def _count_includes(docs, in_handler: bool = False) -> int:
    return sum(1 for t, _ in _mappings_in_context(docs, in_handler) if _is_include(t))


def _every_yaml() -> list:
    return sorted(p for ext in ("yml", "yaml") for p in _ANSIBLE.rglob(f"*.{ext}"))


def test_every_include_tasks_carries_only_keywords_ansible_core_accepts() -> None:
    """A rejected key fails the load of the playbook or handler file, and no CI job parses these (#17917)."""
    found, total = [], 0
    for path in _every_yaml():
        docs = _load(path)
        in_handler = "handlers" in path.relative_to(_ANSIBLE).parts
        total += _count_includes(docs, in_handler)
        found += [(path.relative_to(_ANSIBLE).as_posix(), *hit) for hit in _include_key_offenders(docs, in_handler)]
    assert (
        total >= _INCLUDE_TASKS_FLOOR
    ), f"reach: the finder is not seeing the includes ({total} found, floor {_INCLUDE_TASKS_FLOOR})"
    assert found == [], f"include_tasks with keys ansible-core rejects on an include: {found}"


def _fixture_offenders(extra: str, handler: bool = False) -> list:
    task = f"- name: a\n  ansible.builtin.include_tasks: x.yml\n{extra}"
    return _include_key_offenders(yaml.safe_load(task), handler)


def test_the_include_key_check_reports_keys_outside_the_valid_set() -> None:
    assert _fixture_offenders("  delegate_to: h\n") == [("a", ["delegate_to"])]
    assert _fixture_offenders("  failed_when: false\n") == [("a", ["failed_when"])]
    assert _fixture_offenders("  become: true\n") == [("a", ["become"])]
    assert _fixture_offenders("  listen: x\n") == [("a", ["listen"])], "listen is for a handler include only"


def test_the_include_key_check_passes_valid_includes() -> None:
    assert _fixture_offenders("  listen: x\n", handler=True) == []
    assert _fixture_offenders("  with_items: [a, b]\n  vars: {x: 1}\n  tags: [t]\n  when: y\n") == []
    plain = yaml.safe_load("- name: a\n  ansible.builtin.command: id\n  become: true\n")
    assert _include_key_offenders(plain) == [] and _count_includes(plain) == 0


def test_every_shared_include_names_its_unit() -> None:
    sources = _all_yaml()
    includes = [t for src in sources for t in _mappings(_load(src)) if shared_include(t)]
    assert includes
    nameless = [t.get("name") for t in includes if not (t.get("vars") or {}).get("restart_unit_name")]
    assert not nameless, f"restart includes without restart_unit_name: {nameless}"


def _mappings_in_context(node, in_handler: bool = False):
    """Yield (mapping, in_handler); a ``handlers:`` subtree is handler context."""
    if isinstance(node, dict):
        yield node, in_handler
        for key, value in node.items():
            yield from _mappings_in_context(value, in_handler or key == "handlers")
    elif isinstance(node, list):
        for item in node:
            yield from _mappings_in_context(item, in_handler)


def _lacks_apply(task: dict, inc) -> bool:
    return not (isinstance(inc, dict) and (inc.get("apply") or {}).get("tags") == task["tags"])


def _tagged_includes_without_apply() -> list:
    """Non-handler shared includes whose own ``tags`` are not repeated in ``apply.tags``.

    A dynamic ``include_tasks`` at a play site is itself tag-filtered, and its tags do not reach the
    included tasks, so under ``--tags`` the include runs but the inner restart is filtered out unless
    ``apply: {tags: ...}`` repeats them (ansible-core 2.17 ``playbook/task.py`` ``evaluate_tags`` and
    ``plugins/strategy/linear.py`` ``filter_tagged_tasks``). Handlers are exempt: they ignore tags
    (docs "Handlers ignore tags"; the handler branch of ``linear.py`` never calls ``filter_tagged_tasks``).
    Limit: handler context is a ``handlers:`` key or a file under ``handlers/``; a handler file pulled in
    by name from elsewhere would be judged as a play site.
    """
    bad = []
    for path in _all_yaml():
        rel = path.relative_to(_ANSIBLE).as_posix()
        for task, in_handler in _mappings_in_context(_load(path), "handlers" in path.relative_to(_ANSIBLE).parts):
            inc = shared_include(task)
            if inc is None or in_handler or "tags" not in task:
                continue
            if _lacks_apply(task, inc):
                bad.append((rel, task.get("name")))
    return bad


def test_every_play_site_restart_keeps_its_tags_inside_the_include() -> None:
    assert _tagged_includes_without_apply() == []


def _lacks_apply_in(fixture: str) -> list:
    tasks = _mappings_in_context(yaml.safe_load(fixture))
    return [_lacks_apply(t, shared_include(t)) for t, _ in tasks if shared_include(t)]


def test_the_tag_check_sees_a_missing_apply() -> None:
    """Control: the finder is not blind; it reports a fixture include whose tags are not applied."""
    fixture = "- ansible.builtin.include_tasks: _shared/tasks/restart_unit.yml\n  tags: [restart]\n"
    assert _lacks_apply_in(fixture) == [True]


def test_the_tag_check_accepts_an_include_that_applies_its_tags() -> None:
    """Contrast: a fixture include whose ``apply.tags`` match its own tags is not reported, so a detector that
    rejects every include would fail here."""
    fixture = (
        "- ansible.builtin.include_tasks:\n    file: _shared/tasks/restart_unit.yml\n"
        "    apply:\n      tags: [restart]\n"
        "  tags: [restart]\n"
    )
    assert _lacks_apply_in(fixture) == [False]
    assert _lacks_apply_in(fixture.replace("      tags: [restart]", "      tags: [other]")) == [True]


def test_the_loader_reads_every_document_of_a_multi_document_file(tmp_path: Path) -> None:
    sample = tmp_path / "two.yml"
    sample.write_text(
        "---\n- name: a\n  hosts: x\n---\n- name: b\n  hosts: y\n---\n---\nkey: !vault |\n  abc\n", encoding="utf-8"
    )
    assert [d.get("name", d.get("key")) for d in _load(sample)] == ["a", "b", None]
    broken = tmp_path / "broken.yml"
    broken.write_text("- a: [unclosed\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="broken.yml"):
        _load(broken)


def test_the_self_update_socket_restart_goes_through_the_shared_task() -> None:
    """#21426: the socket restart in the manager role is the same class of restart as the handlers."""
    path = _ANSIBLE / "roles" / "slm_manager" / "tasks" / "bind_self_update_socket.yml"
    mappings = list(_mappings(_load(path)))
    assert [t.get("name") for t in mappings if is_direct_restart(t)] == []
    shared = [t for t in mappings if shared_include(t)]
    assert len(shared) == 1
    assert shared[0]["vars"]["restart_unit_name"] == "{{ slm_self_update_socket_service }}.socket"
    assert shared[0]["ansible.builtin.include_tasks"]["apply"]["tags"] == ["slm", "service", "systemd"]


_RESTART_MODULES = ("systemd", "ansible.builtin.systemd", "service", "ansible.builtin.service")
_NOT_A_UNIT_OF_OURS = (
    "distro-packaged daemon: this repo renders its configuration at most, never its unit file or a systemd "
    "drop-in, and sets no start limit on it (#20772 is AutoBot-managed units)."
)
_CONSUMES_REGISTER = "a later task reads this restart's own register; include_tasks cannot return it (#21429)."
# (file under ansible/, unit as written) -> why this restart stays a direct module call.
_DIRECT_RESTARTS = {
    (
        "fix-slm-env-ports.yml",
        "autobot-slm-backend",
    ): "async: 1 / poll: 0 fire-and-forget; an include cannot be detached (#21429).",
    (
        "playbooks/deploy-native-services.yml",
        "redis-stack-server",
    ): "the same call also sets enabled on first configuration (#21429).",
    ("playbooks/deploy-base.yml", "ssh"): _NOT_A_UNIT_OF_OURS,
    ("playbooks/deploy-base.yml", "systemd-resolved"): _NOT_A_UNIT_OF_OURS,
    ("playbooks/deploy-base.yml", "rsyslog"): _NOT_A_UNIT_OF_OURS,
    ("playbooks/deploy-base.yml", "fail2ban"): _NOT_A_UNIT_OF_OURS,
    ("playbooks/deploy-time-sync.yml", "{{ item }}"): _NOT_A_UNIT_OF_OURS + " Loops chrony/timesyncd, rsyslog, cron.",
    ("playbooks/enroll-node.yml", "ssh"): _NOT_A_UNIT_OF_OURS,
    ("playbooks/enroll-node.yml", "ufw"): _NOT_A_UNIT_OF_OURS,
    ("playbooks/setup-vm-names-and-lvm.yml", "systemd-networkd"): _NOT_A_UNIT_OF_OURS,
    ("playbooks/setup-vm-names-and-lvm.yml", "rsyslog"): _NOT_A_UNIT_OF_OURS,
    ("playbooks/toggle-enforcement.yml", "autobot-backend"): _CONSUMES_REGISTER,
    ("playbooks/update-node.yml", "{{ item }}"): _CONSUMES_REGISTER,
    (
        "playbooks/update-all-nodes.yml",
        "autobot-frontend",
    ): "`systemctl try-restart`: leaves a stopped unit alone, which the shared task (a plain restart) would start; "
    "it also reads its own register (#19661, #21429).",
    ("roles/dependency_patching/tasks/post-update.yml", "{{ current_service.service_name }}"): _CONSUMES_REGISTER,
    ("roles/dependency_patching/tasks/rollback-system.yml", "{{ current_service.service_name }}"): _CONSUMES_REGISTER,
    ("roles/dependency_patching/tasks/rollback.yml", "{{ current_service.service_name }}"): _CONSUMES_REGISTER,
    ("roles/common/handlers/main.yml", "sshd"): _NOT_A_UNIT_OF_OURS,
    ("roles/dns/handlers/main.yml", "dnsmasq"): _NOT_A_UNIT_OF_OURS,
    ("roles/dns/handlers/main.yml", "systemd-resolved"): _NOT_A_UNIT_OF_OURS,
    ("roles/docker/handlers/main.yml", "docker"): _NOT_A_UNIT_OF_OURS,
    ("roles/time_sync/handlers/main.yml", "systemd-timesyncd"): _NOT_A_UNIT_OF_OURS,
    ("roles/time_sync/handlers/main.yml", "chrony"): _NOT_A_UNIT_OF_OURS,
    ("roles/time_sync/handlers/main.yml", "rsyslog"): _NOT_A_UNIT_OF_OURS,
    ("roles/time_sync/handlers/main.yml", "cron"): _NOT_A_UNIT_OF_OURS,
    ("roles/time_sync/handlers/main.yml", "systemd-logind"): _NOT_A_UNIT_OF_OURS,
    ("roles/xrdp/handlers/main.yml", "{{ xrdp_service_name }}"): _NOT_A_UNIT_OF_OURS,
}


_COMMAND_MODULES = ("command", "ansible.builtin.command", "shell", "ansible.builtin.shell")
_COMMAND_SEPARATORS = ";&|\r\n"
_RESTART_VERBS = ("restart", "try-restart")
#: Shell characters that wrap a command word or a unit: quotes, a subshell ``(``/``$(``, a backtick.
_WRAPPERS = "\"'()$`"


def _commands(text: str) -> list:
    """*text* split at ``;``, ``&``, ``|`` and newlines that are outside a ``{{ ... }}`` template."""
    commands, depth, start, at = [], 0, 0, 0
    while at < len(text):
        if text.startswith("{{", at):
            depth, at = depth + 1, at + 2
        elif text.startswith("}}", at):
            depth, at = max(0, depth - 1), at + 2
        else:
            if depth == 0 and text[at] in _COMMAND_SEPARATORS:
                commands.append(text[start:at])
                start = at + 1
            at += 1
    return commands + [text[start:]]


def _tokens(command: str) -> list:
    """Whitespace tokens, with a ``{{ ... }}`` template kept whole as one token."""
    tokens, open_template = [], False
    for token in command.split():
        if open_template:
            tokens[-1] += " " + token
        else:
            tokens.append(token)
        if "{{" in token and "}}" not in token:
            open_template = True
        elif "}}" in token:
            open_template = False
    return tokens


def _ends_the_operands(token: str) -> bool:
    """A comment, or a redirection (``>``, ``2>``, ``<``): what follows is not a unit."""
    redirect = token.lstrip("0123456789")
    return token.startswith("#") or redirect[:1] in (">", "<")


def _unit_operands(tokens: list) -> list:
    """The unit names among the tokens after the verb: options skipped, everything after ``--`` an operand."""
    units, options_done = [], False
    for token in tokens:
        word = token.lstrip(_WRAPPERS)
        if word == "systemctl" or word.endswith("/systemctl") or _ends_the_operands(token):
            break
        if token == "--" and not options_done:
            options_done = True
        elif options_done or not token.startswith("-"):
            name = token.lstrip("\"'`").rstrip(_WRAPPERS)
            if name:
                units.append(name)
    return units


def _systemctl_restart_units(text: str) -> list:
    """Units of every ``systemctl [options] [try-]restart [options] [--] <unit>...`` in *text*, by tokens.

    A command ends at ``;``, ``&``, ``|`` or a newline. After the ``systemctl`` word come any option tokens (those
    starting with ``-``), then the verb, then EVERY unit operand up to the end of the command (``restart a b``
    restarts both). Wrapping shell characters are stripped from the start of the command word (``"systemctl``,
    ``$(systemctl``) and from the unit's ends (``x"``, ``x)``), so ``sh -c "systemctl restart x"`` reports ``x``.
    No regex with a quantified group: the work is linear in the length of the text.
    """
    units = []
    for command in _commands(text):
        tokens = _tokens(command)
        for at, token in enumerate(tokens):
            word = token.lstrip(_WRAPPERS)
            if word != "systemctl" and not word.endswith("/systemctl"):
                continue
            verb = at + 1
            while verb < len(tokens) and tokens[verb].startswith("-"):
                verb += 1
            if verb < len(tokens) and tokens[verb] in _RESTART_VERBS:
                units += _unit_operands(tokens[verb + 1 :])
    return units


def _all_yaml() -> list:
    found = [p for ext in ("yml", "yaml") for p in _ANSIBLE.rglob(f"*.{ext}")]
    return sorted(p for p in found if not {"tests", "_shared"} & set(p.relative_to(_ANSIBLE).parts))


def _command_restart_units(node: dict) -> list:
    """Every unit of a ``systemctl [try-]restart <unit>`` run through command/shell, in order; a compound
    command (``a && b``, ``a; b``) yields one per restart."""
    units = []
    for module in _COMMAND_MODULES:
        spec = node.get(module)
        text = spec.get("cmd") or spec.get("argv") if isinstance(spec, dict) else spec
        text = " ".join(map(str, text)) if isinstance(text, list) else text
        if isinstance(text, str):
            units += _systemctl_restart_units(text)
    return units


def _direct_restart_sites() -> list:
    """(file, unit as written) of each restart made without the shared task.

    Finds ``systemd``/``service`` modules with a literal ``state: restarted`` and ``systemctl [try-]restart
    <unit>`` in command/shell ``cmd``/``argv``/free-form, in ``*.yml`` and ``*.yaml`` under ``ansible/``
    except ``tests/`` and ``_shared/``. Limits: a state or command built from a variable
    (``state: "{{ x }}"``), a restart inside a script file or a template, and a restart through
    ``ansible.builtin.service_facts``-style indirection are not seen.
    """
    found = []
    for path in _all_yaml():
        rel = path.relative_to(_ANSIBLE).as_posix()
        for node in _mappings(_load(path)):
            for module in _RESTART_MODULES:
                spec = node.get(module)
                if isinstance(spec, dict) and spec.get("state") == "restarted":
                    found.append((rel, str(spec.get("name"))))
            found.extend((rel, unit) for unit in _command_restart_units(node))
    return found


def test_a_compound_command_yields_every_restart_it_makes() -> None:
    node = {"ansible.builtin.shell": "systemctl restart ssh && systemctl --no-block try-restart autobot-backend; true"}
    assert _command_restart_units(node) == ["ssh", "autobot-backend"]
    assert _command_restart_units({"ansible.builtin.command": {"argv": ["systemctl", "restart", "--", "ssh"]}}) == [
        "ssh"
    ]
    assert _command_restart_units({"ansible.builtin.command": "systemctl status ssh"}) == []


def test_the_restart_detection_is_linear_on_an_adversarial_command() -> None:
    """The old option pattern backtracked exponentially on ``systemctl`` followed by many ``-! -`` (CodeQL py/redos)."""
    assert _systemctl_restart_units("systemctl " + "-! -" * 100_000) == []
    assert _systemctl_restart_units("systemctl -q --user restart x.service") == ["x.service"]
    assert _systemctl_restart_units("systemctl reset-failed x") == []


@pytest.mark.parametrize(
    "command",
    [
        'sh -c "systemctl restart x"',
        "sh -c 'systemctl restart x'",
        "$(systemctl restart x)",
        "`systemctl restart x`",
        "(systemctl restart x)",
        'echo "systemctl restart x"',
    ],
)
def test_a_restart_wrapped_in_quotes_or_a_subshell_is_found_by_its_clean_name(command: str) -> None:
    assert _systemctl_restart_units(command) == ["x"]


@pytest.mark.parametrize(
    "command",
    ["systemctl reset-failed x", "systemctl status x", "echo restart x", "systemctl -q", 'sh -c "systemctl status x"'],
)
@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("systemctl restart ssh autobot-backend", ["ssh", "autobot-backend"]),
        ("systemctl --no-block restart a --no-block b", ["a", "b"]),
        ("systemctl restart -- a b", ["a", "b"]),
        ('sh -c "systemctl restart a b"', ["a", "b"]),
        ("systemctl restart a > /dev/null 2>&1", ["a"]),
        ("systemctl restart a # b", ["a"]),
        ("systemctl restart a\necho b", ["a"]),
        ("systemctl restart a systemctl restart b", ["a", "b"]),
        ("sudo systemctl restart {{ redis_service_name }}", ["{{ redis_service_name }}"]),
        ("systemctl restart {{ x | default('y') }} b", ["{{ x | default('y') }}", "b"]),
    ],
)
def test_every_unit_operand_of_a_restart_is_found(command: str, expected: list) -> None:
    assert _systemctl_restart_units(command) == expected


def test_a_command_that_restarts_nothing_names_no_unit(command: str) -> None:
    assert _systemctl_restart_units(command) == []


def test_no_restart_anywhere_under_ansible_skips_the_shared_task_unless_justified() -> None:
    sites = _direct_restart_sites()
    unlisted = [s for s in sites if s not in _DIRECT_RESTARTS]
    assert not unlisted, f"direct restarts that clear no start-limit park and are not on the allow-list: {unlisted}"


# Population at pin: 325 YAML files, 7823 mappings. A floor well under both (growth is ordinary) fails the
# sweep when it stops reaching a directory, which a count of findings cannot: the allow-listed sites alone keep
# that count up while a new directory's direct restarts escape inspection.
_FILES_FLOOR, _MAPPINGS_FLOOR = 250, 6000
_SWEEP_EXCLUDED_DIRS = {"tests", "_shared"}


@functools.lru_cache(maxsize=1)
def _mappings_visited() -> int:
    return sum(1 for path in _all_yaml() for _ in _mappings(_load(path)))


def test_the_sweep_parses_every_tracked_ansible_yaml_it_does_not_exclude() -> None:
    """Reach is measured on what the sweep PARSED, independently enumerated from git, not on what it found."""
    root = repo_root()
    tracked = {r for r in tracked_paths(root, _ANSIBLE_REL) if r.endswith((".yml", ".yaml"))}
    kept = {r for r in tracked if not _SWEEP_EXCLUDED_DIRS & set(Path(r).relative_to(_ANSIBLE_REL).parts)}
    examined = {p.relative_to(root).as_posix() for p in _all_yaml()}
    assert not kept - examined, f"tracked ansible YAML the restart sweep never parses: {sorted(kept - examined)}"
    assert len(examined) >= _FILES_FLOOR, f"the sweep parsed {len(examined)} files; expected at least {_FILES_FLOOR}"
    assert _mappings_visited() >= _MAPPINGS_FLOOR, f"the sweep visited {_mappings_visited()} mappings"


def test_the_allow_list_has_no_stale_entry() -> None:
    assert sorted(set(_DIRECT_RESTARTS) - set(_direct_restart_sites())) == []


# Every restart that tolerates failure, as (file, unit as written). Eight had `failed_when: false`
# on origin/main before the shared task (browser x2, frontend, slm_manager handlers; NPU, browser, AI Stack
# x2 in update-all-nodes.yml); four carried `ignore_errors: true` / `failed_when: false` in the TLS and
# certificate playbooks, and the logrotate-timer handler had `failed_when: false`; all keep that behaviour.
_TOLERANT = [
    ("roles/browser/handlers/main.yml", "autobot-vnc"),
    ("roles/browser/handlers/main.yml", "autobot-playwright"),
    ("roles/frontend/handlers/main.yml", "autobot-frontend"),
    ("roles/slm_manager/handlers/main.yml", "{{ slm_backend_service }}"),
    ("playbooks/update-all-nodes.yml", "autobot-npu-worker"),
    ("playbooks/update-all-nodes.yml", "autobot-playwright"),
    ("playbooks/update-all-nodes.yml", "autobot-ai-stack"),
    ("playbooks/update-all-nodes.yml", "autobot-chromadb"),
    ("enable-tls.yml", "autobot-backend"),
    ("enable-tls.yml", "{{ redis_service_name | default('redis-stack-server') }}"),
    ("playbooks/rotate-certs.yml", "{{ _service }}"),
    ("playbooks/rotate-certs.yml", "{{ _service }}"),
    ("roles/common/handlers/main.yml", "logrotate.timer"),
]


def test_exactly_the_sites_that_tolerated_failure_still_tolerate_it() -> None:
    found = []
    for path in _all_yaml():
        for node in _mappings(_load(path)):
            vars_ = node.get("vars") if shared_include(node) else None
            if isinstance(vars_, dict) and vars_.get("restart_unit_tolerate_failure") is True:
                found.append((path.relative_to(_ANSIBLE).as_posix(), vars_["restart_unit_name"]))
    assert sorted(found) == sorted(_TOLERANT)
