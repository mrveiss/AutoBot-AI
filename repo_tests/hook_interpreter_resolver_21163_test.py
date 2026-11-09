# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every git hook gets its Python from the one resolver, never a bare ``python3`` (#21163).

A hook that runs ``python3`` / ``python`` / ``pytest`` gets whichever interpreter is
first on PATH -- 3.10 on Ubuntu 22.04 -- while ``autobot_shared`` refuses to import
below the ``.python-version`` floor. #21163 (pre-commit ``no-direct-redis``) and
#16510 / #17945 / #18029 (pre-push pytest gate) are witnesses of that one defect.
``scripts/lib/hook-python.sh`` is the one resolver;
this guard fails on any hook wrapper or hook script that bypasses it.

Scope: ``tools/git-hooks/*``, ``scripts/hooks/*``, the extensionless hook wrappers under
``autobot-infrastructure/shared/scripts/hooks/``, ``scripts/lint-conventions.sh`` (a
``language: system`` hook), and every ``language: script|system`` entry in
``.pre-commit-config.yaml``. ``language: python`` hooks get ``default_language_version``.
"""

from __future__ import annotations

import re
import subprocess  # nosec B404  # fixed argv, no shell
from pathlib import Path

import pytest
import yaml
from repo_tests._paths import repo_root

from autobot_shared.isolated_git import isolated_git_env
from tools.lint._scan_helpers import tracked_paths

_ROOT = repo_root()
_HOOKS_DIR = "autobot-infrastructure/shared/scripts/hooks"
_RESOLVER = "scripts/lib/hook-python.sh"
_EXTRA = ("scripts/lint-conventions.sh",)  # a `language: system` hook outside any hooks directory
_NOT_A_HOOK = {"README.md", "fast_guard_tests.txt"}

# A bare interpreter word at command position: not part of a path, option, variable or filename.
_BARE = re.compile(r"(?<![\w./$\"'{}=-])(?:python3?(?:\.\d+)?|pytest)(?![\w.\-/])")
_QUOTED = re.compile(r"""(?:"(?:\\.|\$\([^)]*\)|[^"\\])*"|'[^']*')""")


# The program text of `bash -c '...'` / `sh -lc "..."`: it executes, so it is judged like a line of its own.
_SHELL_C = re.compile(r"""\b(?:ba|da|z)?sh\s+(?:-\w+\s+)*-\w*c\s+(?:'([^']*)'|"((?:\\.|[^"\\])*)")""")


def _code(line: str) -> str:
    """The line with comments and literal quoted text removed (message strings are not invocations).

    The body of a ``bash -c`` / ``sh -c`` string stays in: it is a program, not a message.
    """
    if line.strip().startswith("#"):
        return ""
    inner = " ".join(_code(m.group(1) or m.group(2) or "") for m in _SHELL_C.finditer(line))
    return _code_of_line(line) + " " + inner


def _code_of_line(line: str) -> str:
    # command substitutions inside double quotes execute, so their bodies stay (minus their own quotes)
    unsingled = re.sub(r"'[^']*'", " ", line)  # single quotes never execute
    subs = " ".join(_QUOTED.sub(" ", body) for body in re.findall(r"\$\(([^)]*)\)", unsingled))
    return re.sub(r"(^|\s)#.*", "", _QUOTED.sub(" ", line)) + " " + subs


def bare_invocations(text: str) -> list[tuple[int, str]]:
    """(line number, line) for every line that runs python3 / python / pytest by bare name."""
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        code = _code(line)
        for match in _BARE.finditer(code):
            if code[: match.start()].rstrip().endswith(("-m", "--require")):
                continue  # `<interpreter> -m pytest`, `--require pytest`: the interpreter is what is judged
            found.append((number, line.strip()))
            break
    return found


def _tracked(*pathspecs: str) -> list[str]:
    return tracked_paths(_ROOT, *pathspecs)


def _shebang(path: str) -> bytes | None:
    """The first line of a tracked regular file when it is a shebang, else None."""
    p = _ROOT / path
    if not p.is_file() or p.is_symlink():
        return None
    with p.open("rb") as handle:
        first = handle.readline(512)
    return first if first.startswith(b"#!") else None


def _is_text_script(path: str) -> bool:
    """A shell script by its shebang line alone: ``#!`` and no ``python`` on that line."""
    first = _shebang(path)
    return first is not None and b"python" not in first


def _hook_dirs() -> set[str]:
    """Git-hook directories, derived from the tracked tree (a ``hooks`` / ``git-hooks`` path component)."""
    dirs = set()
    for path in _tracked():
        parent = Path(path).parent
        if parent.parts and not parent.parts[0].startswith("."):  # dot-dirs hold agent hooks, not git hooks
            for name in ("hooks", "git-hooks"):
                if name in parent.parts:
                    dirs.add(str(Path(*parent.parts[: parent.parts.index(name) + 1])))
    return dirs


def _sourced_libs(scripts: set[str], tracked: list[str]) -> set[str]:
    """Tracked ``lib/*.sh`` files a hook script names: a library a hook sources runs in the hook."""
    wanted = {
        name
        for path in scripts
        for name in re.findall(r"[\w.-]+\.sh", (_ROOT / path).read_text(encoding="utf-8", errors="replace"))
    }
    return {p for p in tracked if "/lib/" in p and Path(p).name in wanted}


def hook_scripts() -> list[str]:
    """Every tracked shell hook wrapper / script this guard judges; only the resolver file is exempt.

    Reach is derived, not listed: files under a hooks directory, the non-Python files the pre-commit
    config points ``language: script|system`` entries at, ``_EXTRA``, and the libraries those source.
    """
    tracked = _tracked()
    dirs = _hook_dirs()
    entries = {e.split()[0] for _hid, e in config_entries() if e.split()}
    base = {p for p in tracked if any(p.startswith(f"{d}/") for d in dirs)}
    base |= {p for p in tracked if p in entries and "/" in p} | set(_EXTRA)
    base = {p for p in base if _is_shell_hook_file(p)}
    return sorted(p for p in base | _sourced_libs(base, tracked) if p != _RESOLVER and not p.endswith("_test.sh"))


def _is_shell_hook_file(path: str) -> bool:
    return (
        Path(path).name not in _NOT_A_HOOK
        and not path.endswith(("_test.py", ".py", ".ere", ".awk", ".md"))
        and (_is_text_script(path) or path.endswith(".sh"))
    )


def config_entries() -> list[tuple[str, str]]:
    """(hook id, entry) for every ``language: script|system`` hook in the pre-commit config."""
    config = yaml.safe_load((_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    return [
        (h["id"], h.get("entry", ""))
        for repo in config["repos"]
        for h in repo["hooks"]
        if h.get("language") in ("script", "system")
    ]


# --- controls: the detector must fail on a planted bare invocation and pass on a clean one ------


@pytest.mark.parametrize(
    "line",
    [
        "python3 -m tools.lint.check_x $files",
        'PYTHONPATH="$R" python3 -m tools.lint.check_x',
        "timeout 5 python3.10 script.py",
        "out=$(python3 script.py)",
        "pytest -q repo_tests",
        "FOO=1 python -c 'print(1)'",
        'if python3 -c "import sys"; then',
        'echo "$files" | python3 checker.py',
        "bash -c 'python3 -m tools.lint.check_x'",
        'sh -c "cd x && pytest -q"',
        "bash -lc 'FOO=1 python script.py'",
    ],
)
def test_control_a_planted_bare_interpreter_is_flagged(line: str) -> None:
    assert bare_invocations(line + "\n"), line


@pytest.mark.parametrize(
    "line",
    [
        '"$python_cmd" -m tools.lint.check_x $files',
        'PYTHONPATH="$R" "$PYTEST_PYTHON" -m pytest -q',
        'python_cmd="$(resolve_repo_python)" || exit 1',
        "# python3 -m foo is only a comment",
        'echo "needs python3.14 or newer"',
        'log "  validate with python3 scripts/validate_pr_body.py"',
        '"$py" scripts/x.py --pytest-flag',
        "exec bash tests/python_floor_test.sh",
        "bash -c 'echo hello'",
        """bash -c 'echo "needs python3.14 or newer"'""",
        'sh -c "\\"$py\\" -m pytest -q"',
    ],
)
def test_control_resolver_use_comments_and_messages_are_not_flagged(line: str) -> None:
    assert not bare_invocations(line + "\n"), line


# --- the guard over the tree -------------------------------------------------------------------


def test_the_walk_reaches_the_known_sites() -> None:
    """Reach, asserted by name rather than by a count: an empty walk would report 'no offenders'."""
    scripts = set(hook_scripts())
    for known in (
        "tools/git-hooks/pre-push",
        f"{_HOOKS_DIR}/pre-commit-no-direct-redis",
        f"{_HOOKS_DIR}/pre-commit-function-length",
        f"{_HOOKS_DIR}/pre-commit-no-print-console",
        f"{_HOOKS_DIR}/post-merge-doc-sync",
        "scripts/lint-conventions.sh",
    ):
        assert known in scripts, known
    assert any(hid == "no-direct-redis" for hid, _ in config_entries())


def test_no_hook_script_runs_a_bare_interpreter() -> None:
    offenders = [
        f"{path}:{number}: {line}"
        for path in hook_scripts()
        for number, line in bare_invocations((_ROOT / path).read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        "hook scripts must get Python from resolve_repo_python (scripts/lib/hook-python.sh), not a bare "
        "python3/python/pytest (#21163):\n" + "\n".join(offenders)
    )


def test_no_pre_commit_config_entry_runs_a_bare_interpreter() -> None:
    offenders = [f"{hid}: {entry}" for hid, entry in config_entries() if bare_invocations(entry + "\n")]
    assert not offenders, "\n".join(offenders)


@pytest.mark.parametrize(
    "path",
    [
        "tools/git-hooks/pre-push",
        f"{_HOOKS_DIR}/pre-commit-no-direct-redis",
        f"{_HOOKS_DIR}/pre-commit-function-length",
        f"{_HOOKS_DIR}/pre-commit-no-print-console",
        f"{_HOOKS_DIR}/post-merge-doc-sync",
        "scripts/lint-conventions.sh",
    ],
)
def test_every_python_running_hook_goes_through_the_resolver(path: str) -> None:
    text = (_ROOT / path).read_text(encoding="utf-8")
    assert "resolve_repo_python" in text and "hook-python.sh" in text, path


def test_the_resolver_refuses_an_older_python_and_names_the_version(tmp_path: Path) -> None:
    """With no qualifying interpreter on PATH it fails, naming the version -- no silent fallback."""
    (tmp_path / ".python-version").write_text("9.99\n", encoding="utf-8")
    done = subprocess.run(  # nosec B603 B607
        ["bash", "-c", f'. "{_ROOT / _RESOLVER}"; resolve_repo_python --root "$1"', "x", str(tmp_path)],
        capture_output=True,
        text=True,
        env={**isolated_git_env(), "VIRTUAL_ENV": ""},
    )
    assert done.returncode == 1 and done.stdout == ""
    assert "9.99" in done.stderr and ".python-version" in done.stderr


def test_the_resolver_reads_the_floor_from_python_version(tmp_path: Path) -> None:
    floor = (_ROOT / ".python-version").read_text(encoding="utf-8").strip()
    (tmp_path / ".python-version").write_text(floor + "\n", encoding="utf-8")
    done = subprocess.run(  # nosec B603 B607
        ["bash", "-c", f'. "{_ROOT / _RESOLVER}"; resolve_repo_python --root "$1"', "x", str(tmp_path)],
        capture_output=True,
        text=True,
        env=isolated_git_env(),
    )
    if done.returncode == 0:
        major, minor = floor.split(".")[:2]
        probe = subprocess.run(  # nosec B603
            [done.stdout, "-c", f"import sys; print(sys.version_info[:2] >= ({major}, {minor}))"],
            capture_output=True,
            text=True,
        )
        assert probe.stdout.strip() == "True"
    else:
        assert floor in done.stderr
