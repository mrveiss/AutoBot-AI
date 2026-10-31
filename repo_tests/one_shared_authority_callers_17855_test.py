# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Callers use the shared authority instead of carrying a copy (#17855).

Each row below was a local re-implementation of something `autobot_shared` already owned,
and in each the copy lacked a fix the shared one had received (blank-env handling, the strict
`GIT_*` strip, a cross-process lock, the full SSRF range set, interface enumeration, the CJK
token count, "never write defaults to disk"). The detector reads call names from the syntax
tree, so a docstring that names the old function is not a use of it.

The `with Lock():` class is checked tree-wide because it is a defect rather than a shape: a
lock constructed inside the `with` item is a new object on every entry and excludes nothing.
"""

from __future__ import annotations

import ast
import functools
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_LOCK_NAMES = frozenset({"Lock", "RLock"})
_ENV_READS = frozenset({"os.environ.get", "os.getenv", "environ.get", "getenv"})
_PARSE_CASTS = frozenset({"int", "float"})


def _dotted(node: ast.AST) -> str:
    """`a.b.c` for a Name/Attribute chain, else the empty string."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        head = _dotted(node.value)
        return f"{head}.{node.attr}" if head else node.attr
    return ""


def _call_names(tree: ast.AST) -> set[str]:
    """Every dotted callee name under `tree`, plus its final segment."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _dotted(node.func)
            if name:
                names.update({name, name.rsplit(".", 1)[-1]})
    return names


def _locks_built_in_with(source: str) -> list[int]:
    """Line numbers of `with threading.Lock():` -- a lock constructed per entry."""
    hits = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                call = item.context_expr
                if isinstance(call, ast.Call) and _dotted(call.func).rsplit(".", 1)[-1] in _LOCK_NAMES:
                    hits.append(node.lineno)
    return hits


def _local_env_parsers(source: str) -> list[str]:
    """Functions that read the environment AND parse it themselves (int/float/flag set)."""
    found = []
    for fn in ast.walk(ast.parse(source)):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        calls = _call_names(fn)
        if calls & _ENV_READS and calls & _PARSE_CASTS:
            found.append(fn.name)
    return found


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("a per-call lock", "def f():\n    with threading.Lock():\n        pass\n", [2]),
        ("a bare Lock", "def f():\n    with Lock():\n        pass\n", [2]),
        ("a held lock", "def f(self):\n    with self._lock:\n        pass\n", []),
        ("a module lock", "with _LOCK:\n    pass\n", []),
    ],
)
def test_the_lock_matcher_tells_a_per_call_lock_from_a_held_one(label: str, source: str, expected: list[int]) -> None:
    assert _locks_built_in_with(source) == expected, label


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("a local int parser", "def p(n, d):\n    return int(os.environ.get(n, d))\n", ["p"]),
        ("a local float parser", "def p(n, d):\n    return float(os.getenv(n))\n", ["p"]),
        ("a plain read", "def p(n):\n    return os.environ.get(n)\n", []),
        ("a shared-helper call", "def p(n, d):\n    return env_int(n, d)\n", []),
        ("a docstring naming it", 'def p():\n    "int(os.environ.get(x))"\n    return 1\n', []),
    ],
)
def test_the_env_parser_matcher_tells_a_copy_from_a_use(label: str, source: str, expected: list[str]) -> None:
    assert _local_env_parsers(source) == expected, label


def _is_source_python(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return rel.endswith(".py") and not (name.endswith("_test.py") or name.startswith("test_") or "/tests/" in rel)


def _source_population(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, "autobot-backend", "autobot-slm-backend", "autobot_shared")
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_source_python(rel)]


REACH = declare(
    "shared-authority-callers-scan",
    discover=_source_population,
    floor=3233,  # re-pinned mid-window: population 3383, window [3083, 3383]
    what="non-test python source",
    roots=("autobot-backend", "autobot-slm-backend", "autobot_shared"),
    growth=300,
)


def _read(rel: str) -> str:
    return (repo_root() / rel).read_text(encoding="utf-8")


@functools.lru_cache(maxsize=1)
def _per_call_locks() -> tuple[tuple[str, ...], int]:
    found: list[str] = []
    parsed = 0
    for rel in REACH.examined(repo_root()):
        source = _read(rel)
        if "Lock" not in source:
            continue
        parsed += 1
        if _locks_built_in_with(source):
            found.append(rel)
    return tuple(found), parsed


def test_the_lock_scan_is_not_vacuous() -> None:
    _, parsed = _per_call_locks()
    assert parsed >= 20, f"parsed {parsed} files mentioning a Lock"


def test_no_lock_is_constructed_inside_a_with_item() -> None:
    found, _ = _per_call_locks()
    assert not found, (
        f"#17855: {list(found)} build a Lock inside `with`; it is a new object each time and excludes "
        "nothing. Hold one lock on the instance or module, or use a cross-process one "
        "(utils.secrets_store_migration._canonical_store_lock)."
    )


#: (file, function or None for the whole file, calls it must make, calls it must not make)
_CONSUMERS: tuple[tuple[str, str | None, frozenset[str], frozenset[str]], ...] = (
    ("autobot-backend/memory/essential_story.py", None, frozenset({"env_flag", "env_float"}), frozenset(_ENV_READS)),
    ("autobot-backend/agent_loop/tool_output_spill.py", None, frozenset({"env_int", "env_flag"}), frozenset()),
    ("autobot-backend/knowledge/facts.py", None, frozenset({"env_int", "env_float"}), frozenset()),
    ("autobot-slm-backend/services/git_subprocess.py", "run_git_capture", frozenset({"start_git"}), frozenset({"create_subprocess_exec"})),
    ("autobot-slm-backend/services/git_tracker.py", None, frozenset({"run_git_capture"}), frozenset({"create_subprocess_exec", "scrubbed_git_env"})),
    ("autobot-backend/security/enterprise/compliance_manager.py", "_get_encryption_key", frozenset({"ensure_and_read_shared_key"}), frozenset({"generate_key"})),
    ("autobot-backend/api/push.py", "_check_ssrf", frozenset({"is_public_url_async"}), frozenset({"ip_address", "getaddrinfo"})),
    ("autobot-slm-backend/api/nodes_execution.py", None, frozenset(), frozenset({"gethostbyname", "gethostname"})),
    ("autobot-backend/knowledge/pipeline/extractors/semantic_chunker.py", "_estimate_tokens", frozenset({"estimate"}), frozenset({"split"})),
    ("autobot-backend/llm_shared/optimization/prompt_compressor.py", "_count_tokens", frozenset({"estimate_fast"}), frozenset()),
    ("autobot-backend/security/domain_security.py", "_load_config", frozenset({"load_config_file"}), frozenset({"safe_load"})),
    ("autobot-backend/context_window_manager.py", "_load_config", frozenset({"load_config_file"}), frozenset({"safe_load"})),
    ("autobot-backend/voice_interface.py", "_load_config", frozenset({"load_config_file"}), frozenset({"safe_load"})),
    ("autobot-backend/security/command_validator.py", "_load_config", frozenset({"load_config_file"}), frozenset({"load"})),
    # row 8: key=value / JSON config reader now delegates, with the format parser from the shared module
    ("autobot-backend/utils/common.py", "load_config", frozenset({"load_config_file"}), frozenset({"open", "yaml.safe_load"})),
)  # fmt: skip


def _scope(source: str, function: str | None) -> ast.AST | None:
    tree = ast.parse(source)
    if function is None:
        return tree
    return next(
        (n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == function),
        None,
    )


def _violations(source: str, function: str | None, must: frozenset[str], must_not: frozenset[str]) -> list[str]:
    scope = _scope(source, function)
    if scope is None:
        return [f"function {function} is missing"]
    calls = _call_names(scope)
    return [f"does not call {n}" for n in sorted(must - calls)] + [f"still calls {n}" for n in sorted(must_not & calls)]


def test_the_consumer_check_names_what_is_wrong() -> None:
    good = "def f():\n    return env_int('A', 1)\n"
    bad = "def f():\n    return int(os.environ.get('A'))\n"
    assert _violations(good, "f", frozenset({"env_int"}), frozenset({"int"})) == []
    assert _violations(bad, "f", frozenset({"env_int"}), frozenset({"int"})) == [
        "does not call env_int",
        "still calls int",
    ]
    assert _violations(good, "gone", frozenset(), frozenset()) == ["function gone is missing"]


@pytest.mark.parametrize(("rel", "function", "must", "must_not"), _CONSUMERS, ids=[c[0] for c in _CONSUMERS])
def test_each_caller_uses_the_shared_authority(rel: str, function: str | None, must, must_not) -> None:
    bad = _violations(_read(rel), function, must, must_not)
    assert not bad, f"#17855: {rel}: {bad}"


@pytest.mark.parametrize(
    "rel",
    [c[0] for c in _CONSUMERS if c[0].endswith(("essential_story.py", "tool_output_spill.py", "facts.py"))],
)
def test_no_env_parser_is_redefined_beside_env_utils(rel: str) -> None:
    assert _local_env_parsers(_read(rel)) == [], f"#17855: {rel} parses env vars itself; use autobot_shared.env_utils"


# row 10: error_handler.retry was removed after its useful part (the on_retry hook) moved into
# the shared RetryPolicy; it retried ValueError/TypeError, which the shared policy never does.
def _defined_functions(source: str) -> set[str]:
    return {n.name for n in ast.walk(ast.parse(source)) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _class_fields(source: str, cls: str) -> set[str]:
    node = next(n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.ClassDef) and n.name == cls)
    return {n.target.id for n in node.body if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)}


def test_the_definition_matchers_distinguish_present_from_absent() -> None:
    assert _defined_functions("def retry(): pass\nclass A:\n    def m(self): pass") == {"retry", "m"}
    assert _defined_functions("x = 'def retry'") == set()
    assert _class_fields("class P:\n    on_retry: int = 1\n", "P") == {"on_retry"}
    assert _class_fields("class P:\n    x = 1\n", "P") == set()


def test_error_handler_no_longer_carries_its_own_retry_decorator() -> None:
    funcs = _defined_functions(_read("autobot-backend/error_handler.py"))
    assert (
        not {"retry", "_create_sync_retry_wrapper", "_create_async_retry_wrapper"} & funcs
    ), "#17855 row 10: retry lives once, in autobot_shared.retry_mechanism"


def test_the_shared_retry_policy_owns_the_on_retry_hook() -> None:
    assert "on_retry" in _class_fields(_read("autobot_shared/retry_mechanism.py"), "RetryPolicy")


def _env_flag_modes(source: str) -> dict[str, str]:
    """`{flag name: on_invalid keyword or "default"}` for every `env_flag("NAME", ...)` call."""
    modes: dict[str, str] = {}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and _dotted(node.func).endswith("env_flag") and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                kw = next((k.value for k in node.keywords if k.arg == "on_invalid"), None)
                modes[first.value] = kw.value if isinstance(kw, ast.Constant) else "default"
    return modes


def test_the_flag_mode_matcher_reads_the_keyword() -> None:
    assert _env_flag_modes('x = env_flag("A", True, on_invalid="false")\ny = env_flag("B")') == {
        "A": "false",
        "B": "default",
    }


def test_the_auto_approve_flag_reads_a_typo_as_false() -> None:
    """Default True but its SAFE value is False: a typo must not widen what is auto-approved."""
    modes = _env_flag_modes(_read("autobot-backend/chat_workflow/compose_tool_handler.py"))
    assert modes.get("AUTOBOT_CODEEXEC_AUTOAPPROVE_READONLY") == "false"
