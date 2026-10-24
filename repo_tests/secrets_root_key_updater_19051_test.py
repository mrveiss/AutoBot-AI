# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#19051: the builtin updater must back-fill the root key, and an empty key must stop the deploy.

The #14758 back-fill lived only in the slm_manager role, which update-all-nodes.yml Play 1
never runs. A host kept current by the builtin updater alone never got a key, the backend
rendered `AUTOBOT_SECRETS_ROOT_KEY=`, and every System vault call returned 503.
"""

import re

from repo_tests._paths import repo_root

ANSIBLE = repo_root() / "autobot-slm-backend" / "ansible"
UPDATER = ANSIBLE / "playbooks" / "update-all-nodes.yml"
ROLE_MAIN = ANSIBLE / "roles" / "slm_manager" / "tasks" / "main.yml"
BACKFILL = ANSIBLE / "roles" / "slm_manager" / "tasks" / "secrets_root_key.yml"
BACKEND_TASKS = ANSIBLE / "roles" / "backend" / "tasks" / "main.yml"
_INCLUDE = re.compile(r"name: slm_manager\s+tasks_from: secrets_root_key\.yml")


def _read(path):
    assert path.is_file(), f"{path} is missing — this guard would otherwise pass vacuously"
    return path.read_text(encoding="utf-8")


def test_play_1_runs_the_back_fill_before_the_backend_play() -> None:
    text = _read(UPDATER)
    play1, play2 = text.find('- name: "Play 1 '), text.find('- name: "Play 2 ')
    assert 0 <= play1 < play2, "update-all-nodes.yml no longer has Play 1 before Play 2 — re-point this guard"
    match = _INCLUDE.search(text)
    assert match, "Play 1 must include slm_manager tasks_from: secrets_root_key.yml (#19051)"
    assert play1 < match.start() < play2, "the back-fill must run in Play 1, before the backend env renders"


def test_the_role_and_the_updater_share_one_back_fill() -> None:
    assert "include_tasks: secrets_root_key.yml" in _read(ROLE_MAIN)
    # The files a second copy would land in: the role's own flow, the updater, the backend role.
    # A named list, not a tree glob, so this guard declares no uncovered read (#15900).
    marker = re.compile(r"^\s*regexp: .*AUTOBOT_SECRETS_ROOT_KEY=", re.MULTILINE)
    copies = [p.name for p in (ROLE_MAIN, UPDATER, BACKEND_TASKS, BACKFILL) if marker.search(_read(p))]
    assert copies == [BACKFILL.name], f"the back-fill must exist exactly once, in {BACKFILL.name}; found {copies}"


def test_the_back_fill_only_adds() -> None:
    text = _read(BACKFILL)
    add = text[text.index("Add AUTOBOT_SECRETS_ROOT_KEY") :]
    assert "_slm_root_key_check.rc != 0" in add, "the key must be written only when the grep found none"
    assert "create: false" in add


def test_an_empty_key_from_the_slm_file_fails_the_backend_deploy() -> None:
    text = _read(BACKEND_TASKS)
    align = text.index("Align autobot_secrets_root_key with slm-secrets.env")
    guard = text.index("Fail when the SLM secrets file yields no root key")
    render = text.index("src: backend.env.j2")
    assert align < guard < render, "the empty-key failure must sit after the read-back and before the env renders"
    block = text[guard : text.index("\n- name:", guard)]
    assert "ansible.builtin.fail" in block
    assert "_slm_secrets_stat.stat.exists" in block, "it must fire only where the SLM file is the key's source"
    assert "_backend_slm_root_key | length == 0" in block, "judge the FILE's key; an inventory key must not mask it"


# --- #19294 review F1/F2/F3/F5: never generate over an existing key -------------------------

_GEN = "GENERATED-KEY"


def _tasks():
    yaml = __import__("yaml")
    return yaml.safe_load(_read(BACKFILL))


def _task(name_part):
    found = [t for t in _tasks() if name_part in t["name"]]
    assert len(found) == 1, f"expected one task named like {name_part!r}, found {len(found)}"
    return found[0]


def _render(expr, **context):
    """Render one of the back-fill's own Jinja expressions; count generator calls."""
    import jinja2

    calls = []
    env = jinja2.Environment()  # nosec B701  # rendering repo-owned expressions with test data only
    env.filters["regex_replace"] = lambda v, pattern, repl: re.sub(pattern, repl, v)
    env.globals["lookup"] = lambda *a, **k: calls.append(a) or _GEN
    return env.from_string(expr).render(**context).strip(), len(calls)


def _seed(operator="", backend_env=""):
    expr = _task("Add AUTOBOT_SECRETS_ROOT_KEY")["vars"]["_root_key_seed"]
    ctx = {"_backend_env_root_key": {"stdout": backend_env}}
    if operator is not None:
        ctx["autobot_secrets_root_key"] = operator
    return _render(expr, **ctx)


def test_an_operator_supplied_key_is_written_and_nothing_is_generated() -> None:
    assert _seed(operator="OPERATOR-KEY") == ("OPERATOR-KEY", 0)


def test_a_backend_env_only_key_is_written_and_nothing_is_generated() -> None:
    assert _seed(operator=None, backend_env='"ENV-KEY"\n') == ("ENV-KEY", 0)


def test_a_key_is_generated_only_when_none_exists_anywhere() -> None:
    assert _seed(operator="", backend_env="") == (_GEN, 1)


def test_two_different_existing_keys_are_a_conflict_and_equal_ones_are_not() -> None:
    task = _task("Compare the operator and backend-env root keys")
    expr, variables = task["ansible.builtin.set_fact"]["_root_keys_conflict"], task["vars"]

    def conflict(operator, backend_env):
        ctx = {"autobot_secrets_root_key": operator, "_backend_env_root_key": {"stdout": backend_env}}
        resolved = {k: _render(v, **ctx)[0] for k, v in variables.items()}
        return _render(expr, **ctx, **resolved)[0]

    assert conflict("A", "B") == "True"
    assert conflict("A", "'A'") == "False"
    assert conflict("A", "") == "False" and conflict("", "B") == "False"
    assert "no_log" not in _task("Refuse two different existing root keys"), "the refusal must stay readable"


def test_an_export_line_counts_as_present_and_is_replaced_not_duplicated() -> None:
    grep = _task("Check if AUTOBOT_SECRETS_ROOT_KEY present")["ansible.builtin.shell"]["cmd"]
    ere = re.search(r'grep -Eq "(.+)"\s', grep).group(1).replace('\\"', '"')
    ere = ere.replace("[[:space:]]", r"\s").replace("[:space:]", r"\s")  # POSIX class -> Python, bare or bracketed
    regexp = _task("Add AUTOBOT_SECRETS_ROOT_KEY")["ansible.builtin.lineinfile"]["regexp"]
    for line in (
        "AUTOBOT_SECRETS_ROOT_KEY=k",
        "export AUTOBOT_SECRETS_ROOT_KEY=k",
        "  export  AUTOBOT_SECRETS_ROOT_KEY=k",
    ):
        assert re.match(ere, line), f"the presence check must see {line!r}"
        assert re.match(regexp, line), f"lineinfile must replace {line!r}, not add a second line"
    for empty in ("AUTOBOT_SECRETS_ROOT_KEY=", 'AUTOBOT_SECRETS_ROOT_KEY=""', "export AUTOBOT_SECRETS_ROOT_KEY=''"):
        assert not re.match(ere, empty), f"{empty!r} is no key: the back-fill must replace it"
    for unrelated in ("export OTHER_SECRET=k", "MY_AUTOBOT_SECRETS_ROOT_KEY=k", "# AUTOBOT_SECRETS_ROOT_KEY=k"):
        assert not re.match(ere, unrelated), f"the presence check must not count {unrelated!r}"
        assert not re.match(regexp, unrelated), f"lineinfile must not replace {unrelated!r}"


def test_the_backend_reads_every_key_line_the_back_fill_counts_as_present() -> None:
    # CodeRabbit on #19364: an `export`-prefixed or quoted key skipped the back-fill but read back empty.
    text = _read(BACKEND_TASKS)
    block = text[text.index("Read AUTOBOT_SECRETS_ROOT_KEY from slm-secrets.env") :]
    pcre = re.search(r"grep -oP '(.+?)'", block).group(1).replace(r"\K", "(?P<key>") + ")"
    lines = ("AUTOBOT_SECRETS_ROOT_KEY=k", "export AUTOBOT_SECRETS_ROOT_KEY=k", "  export  AUTOBOT_SECRETS_ROOT_KEY=k")
    for line in lines:
        assert (m := re.match(pcre, line)) and m.group("key") == "k", f"the backend must read the key in {line!r}"
    unquote = text[text.index("Unquote the root key read from slm-secrets.env") :]
    assert "regex_replace(" in unquote.split("\n- name:")[0], "a quoted key must be unquoted before use"


def test_every_key_handling_task_is_no_log_and_reads_run_in_check_mode() -> None:
    for part in ("Check if", "Read an existing root key", "Compare the operator", "Add AUTOBOT_SECRETS_ROOT_KEY"):
        assert _task(part).get("no_log") is True, f"{part!r} handles the key and must be no_log"
    for part in ("Check if", "Read an existing root key"):
        assert _task(part).get("check_mode") is False, f"{part!r} must run in check mode so rc is defined"
