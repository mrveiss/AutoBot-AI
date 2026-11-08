# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#21004: every code-intelligence analyzer discovers files and excludes dirs in one place."""

import ast
import importlib.util
import re
from pathlib import Path
from typing import List, Set

import pytest

_PKG = Path(__file__).resolve().parent
_CANONICAL = "python_files.py"
_WALKS = {"rglob", "walk"}
_COPY_NAMES = {"EXCLUDE_DIRS", "DEFAULT_EXCLUDE_DIRS", "_SKIP_DIRS", "_COCHANGE_SKIP_DIRS"}
# A name that reads as an exclusion/ignore list. Bound to a literal collection of
# strings it is a local copy of the exclusion rule (#21004 AC1/AC2).
_IGNORE_LIST_NAME = re.compile(r"^_?(default_)?(exclude|excludes|ignore|skip)[a-z_]*$", re.IGNORECASE)
_PATH_RECEIVER = re.compile(r"^(path|filepath|file_path|rel_path|rel|\w+_path)$")
_PATH_CTORS = {"Path", "PurePath", "PurePosixPath"}
# Pattern lists that are policy globs consumed by ``matches_exclusion`` (no directory
# names, no predicate of their own). Each entry needs a reason; a stale entry fails.
_ALLOWED_POLICY_LISTS = {
    ("shared/analysis_base.py", "DEFAULT_EXCLUDE_PATTERNS"): "BaseCodeAnalyzer family's own file-glob policy",
    ("multi_language_scanner.py", "default_excludes"): "project log tree; dir names come from SKIP_DIRS",
    ("llm_pattern_analyzer.py", "exclude_patterns"): "caller default, applied through matches_exclusion",
    ("base_analyzer.py", "default_excludes"): "minified-bundle globs, applied through matches_exclusion",
    ("anti_pattern_detection/types.py", "DEFAULT_IGNORE_PATTERNS"): "ANALYSIS_EXCLUDE_DIRS plus bytecode globs",
    # An INCLUDE match (which pre-commit checks apply to a file), not an exclusion.
    ("precommit_analyzer.py", "fnmatch"): "check applicability, not file exclusion",
}


def _load_real_module():
    """Load python_files.py by path (conftest stubs code_intelligence submodules)."""
    spec = importlib.util.spec_from_file_location("_real_21004_python_files", _PKG / _CANONICAL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _production_files(root: Path) -> List[Path]:
    """Non-test ``.py`` files below *root*, excluding the canonical module."""
    return sorted(
        p
        for p in root.rglob("*.py")  # noqa: bare-walk (the guard's own scan)
        if p.name != _CANONICAL and not p.name.endswith("_test.py") and "tests" not in p.relative_to(root).parts
    )


_OS_WALKERS = {"walk", "fwalk", "scandir"}


def _str_arg_has_recursive_glob(call: ast.Call) -> bool:
    first = call.args[0] if call.args else None
    return isinstance(first, ast.Constant) and isinstance(first.value, str) and "**" in first.value


def _is_false(value: ast.expr) -> bool:
    return isinstance(value, ast.Constant) and not value.value


def _os_walker_names(tree: ast.AST) -> Set[str]:
    """Local names bound by ``from os import walk/fwalk/scandir [as x]``."""
    return {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "os"
        for alias in node.names
        if alias.name in _OS_WALKERS
    }


def _call_violation(node: ast.Call, os_names: Set[str]) -> str:
    """Name of the discovery rule *node* breaks, or ``""``."""
    func = node.func
    if isinstance(func, ast.Name):
        return "bare walk()" if func.id in os_names else ""
    if not isinstance(func, ast.Attribute):
        return ""
    owner = func.value.id if isinstance(func.value, ast.Name) else ""
    if func.attr == "rglob":
        return "bare rglob()"
    if owner == "os" and func.attr in _OS_WALKERS:
        return f"bare os.{func.attr}()"
    if func.attr == "glob" and _str_arg_has_recursive_glob(node):
        return "recursive glob(**)"
    if owner == "glob" and func.attr in {"glob", "iglob"}:
        recursive = any(k.arg == "recursive" and not _is_false(k.value) for k in node.keywords)
        return "glob.glob(recursive=)" if recursive else ""
    return ""


def _import_violation(node: ast.AST) -> str:
    if isinstance(node, ast.ImportFrom) and node.module == "os":
        if any(alias.name in _OS_WALKERS for alias in node.names):
            return "from os import walker"
    return ""


def _is_string_collection(value: ast.expr | None) -> bool:
    """A list/tuple/set literal holding at least one string constant."""
    if not isinstance(value, (ast.List, ast.Tuple, ast.Set)):
        return False
    return any(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in value.elts)


def _ignore_list_copies(node: ast.AST) -> List[str]:
    """Names bound to a literal exclusion list (a local copy of the rule)."""
    value = getattr(node, "value", None)
    if not _is_string_collection(value):
        return []
    return [name for name in _assigned_names(node) if _IGNORE_LIST_NAME.match(name)]


def _is_filename_predicate(node: ast.AST) -> str:
    """The rule broken by a local file-name match (``fnmatch``, ``<path>.match(``)."""
    if isinstance(node, ast.ImportFrom) and node.module == "fnmatch":
        return "local fnmatch"
    if isinstance(node, ast.Import) and any(a.name == "fnmatch" for a in node.names):
        return "local fnmatch"
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "match"):
        return ""
    owner = node.func.value
    is_ctor = isinstance(owner, ast.Call) and getattr(owner.func, "id", "") in _PATH_CTORS
    if is_ctor or (isinstance(owner, ast.Name) and _PATH_RECEIVER.match(owner.id)):
        return "local path.match() predicate"
    return ""


def _predicate_violations(node: ast.AST, rel: str) -> List[str]:
    rule = _is_filename_predicate(node)
    found = [f"{rel}:{node.lineno} {rule}"] if rule and (rel, rule.split()[-1]) not in _ALLOWED_POLICY_LISTS else []
    for name in _ignore_list_copies(node):
        if (rel, name) not in _ALLOWED_POLICY_LISTS:
            found.append(f"{rel}:{node.lineno} local ignore list {name}")
    return found


def find_violations(root: Path) -> List[str]:
    """``file:line what`` for each bare walk call or analyzer-local exclusion-set copy."""
    found: List[str] = []
    for path in _production_files(root):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        os_names = _os_walker_names(tree)
        for node in ast.walk(tree):
            rule = _call_violation(node, os_names) if isinstance(node, ast.Call) else _import_violation(node)
            if rule:
                found.append(f"{path.relative_to(root)}:{node.lineno} {rule}")
            for name in _assigned_names(node):
                if name in _COPY_NAMES:
                    found.append(f"{path.relative_to(root)}:{node.lineno} local {name}")
            if hasattr(node, "lineno"):
                found.extend(_predicate_violations(node, path.relative_to(root).as_posix()))
    return found


def _assigned_names(node: ast.AST) -> List[str]:
    if isinstance(node, ast.Assign):
        return [t.id for t in node.targets if isinstance(t, ast.Name)]
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return [node.target.id]
    return []


def test_no_bare_walk_or_exclusion_copy_in_code_intelligence():
    assert find_violations(_PKG) == []


_PLANTED = {
    "bare rglob()": "def f(p):\n    return list(p.rglob('*.py'))\n",
    "bare os.walk()": "import os\n\ndef f(p):\n    return os.walk(p)\n",
    "bare os.scandir()": "import os\n\ndef f(p):\n    return os.scandir(p)\n",
    "from os import walker": "from os import walk\n",
    "bare walk()": "from os import walk\n\ndef f(p):\n    return walk(p)\n",
    "recursive glob(**)": "def f(p):\n    return p.glob('**/*.py')\n",
    "glob.glob(recursive=)": "import glob\n\ndef f(p):\n    return glob.glob(p, recursive=True)\n",
    "local EXCLUDE_DIRS": "EXCLUDE_DIRS = {'x'}\n",
    "local ignore list": "IGNORE_PATTERNS = ['*.min.js']\n",
    "local fnmatch": "import fnmatch\n",
    "local path.match() predicate": "def f(file_path, pats):\n    return any(file_path.match(p) for p in pats)\n",
}


@pytest.mark.parametrize("rule", sorted(_PLANTED))
def test_guard_flags_each_planted_violation(tmp_path: Path, rule: str):
    """Control: a clean run proves nothing unless the guard sees every planted violation."""
    (tmp_path / "planted.py").write_text(_PLANTED[rule], encoding="utf-8")
    assert any(rule in f for f in find_violations(tmp_path))


@pytest.mark.parametrize(
    "source",
    [
        "from ast import walk\n\ndef f(t):\n    return walk(t)\n",
        "import glob\n\ndef f(p):\n    return glob.glob(p, recursive=False)\n",
        "import glob\n\ndef f(p):\n    return glob.iglob(p)\n",
    ],
)
def test_guard_does_not_flag_look_alikes(tmp_path: Path, source: str):
    (tmp_path / "ok.py").write_text(source, encoding="utf-8")
    assert find_violations(tmp_path) == []


def test_guard_flags_a_path_constructor_match(tmp_path: Path):
    (tmp_path / "bad.py").write_text(
        "from pathlib import Path\n\ndef f(x, g):\n    return Path(x).match(g)\n", encoding="utf-8"
    )
    assert any("path.match()" in f for f in find_violations(tmp_path))


@pytest.mark.parametrize(
    "source", ["import re\n\ndef f(line, rx):\n    return rx.match(line)\n", "SKIP_REASONS = []\n"]
)
def test_guard_does_not_flag_regex_match_or_an_empty_list(tmp_path: Path, source: str):
    (tmp_path / "ok.py").write_text(source, encoding="utf-8")
    assert find_violations(tmp_path) == []


def test_allowed_policy_lists_are_all_still_present():
    """A stale allowlist entry would silently exempt a future copy of the same name."""
    for rel, name in _ALLOWED_POLICY_LISTS:
        source = (_PKG / rel).read_text(encoding="utf-8")
        if name == "fnmatch":
            assert "fnmatch" in source, rel
            continue
        tree = ast.parse(source)
        assert any(
            name in _assigned_names(n) and _is_string_collection(getattr(n, "value", None)) for n in ast.walk(tree)
        ), (
            rel,
            name,
        )


def test_matches_exclusion_one_grammar(tmp_path: Path):
    module = _load_real_module()
    root = tmp_path / "venv" / "proj"
    cases = {
        ("a/test_x.py", (module.TEST_FILE_PATTERN,)): True,
        ("a/testing_utils.py", (module.TEST_FILE_PATTERN,)): False,
        ("a/x.pyc", ("*.pyc",)): True,
        ("a/tests/x.py", ("**/tests/**",)): True,
        ("a/x.min.js", ("**/*.min.js",)): True,
        ("a/migrations/x.py", ("/migrations/",)): True,
        ("a/x.py", ("/migrations/", "*.pyc")): False,
    }
    for (rel, patterns), expected in cases.items():
        assert module.matches_exclusion(root / rel, patterns, root) is expected, (rel, patterns)


def test_discover_files_rejects_a_path_pattern(tmp_path: Path):
    module = _load_real_module()
    for bad in ("src/*.py", "**/*.py", "a\\b.py"):
        with pytest.raises(ValueError, match="file-name glob"):
            module.discover_files(tmp_path, (bad,))


def test_guard_ignores_a_non_recursive_glob(tmp_path: Path):
    (tmp_path / "ok.py").write_text("def f(p):\n    return p.glob('*')\n", encoding="utf-8")
    assert find_violations(tmp_path) == []


@pytest.mark.parametrize("skipped_ancestor", ["venv", "node_modules", ".worktrees"])
def test_root_under_a_skipped_name_still_yields_files(tmp_path: Path, skipped_ancestor: str):
    root = tmp_path / skipped_ancestor / "project"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (root / "venv").mkdir()
    (root / "venv" / "skipped.py").write_text("y = 2\n", encoding="utf-8")
    module = _load_real_module()
    assert [p.name for p in module.discover_files(root)] == ["a.py"]
    assert [Path(p).name for p in module.collect_python_files(str(root), module.ANALYSIS_EXCLUDE_DIRS)] == ["a.py"]


def test_analysis_exclude_dirs_derives_from_skip_dirs():
    from utils.file_categorization import SKIP_DIRS

    assert SKIP_DIRS == _load_real_module().ANALYSIS_EXCLUDE_DIRS


def test_symlinked_leaf_escaping_the_root_or_into_a_skipped_dir_is_dropped(tmp_path: Path):
    module = _load_real_module()
    root = tmp_path / "project"
    (root / "pkg").mkdir(parents=True)
    (root / "venv").mkdir()
    (root / "pkg" / "real.py").write_text("x = 1\n", encoding="utf-8")
    outside = tmp_path / "outside.py"
    outside.write_text("secret = 1\n", encoding="utf-8")
    (root / "venv" / "hidden.py").write_text("y = 1\n", encoding="utf-8")
    (root / "pkg" / "escape.py").symlink_to(outside)
    (root / "pkg" / "into_skipped.py").symlink_to(root / "venv" / "hidden.py")
    (root / "pkg" / "inside.py").symlink_to(root / "pkg" / "real.py")
    assert [p.name for p in module.discover_files(root)] == ["inside.py", "real.py"]


def test_discover_files_prunes_excluded_dirs_and_matches_every_pattern(tmp_path: Path):
    module = _load_real_module()
    (tmp_path / "a").mkdir()
    (tmp_path / "node_modules" / "deep").mkdir(parents=True)
    for rel in ("a/x.ts", "a/y.vue", "a/z.py", "node_modules/deep/n.ts"):
        (tmp_path / rel).write_text("", encoding="utf-8")
    found = module.discover_files(tmp_path, ("*.ts", "*.vue"))
    assert [p.name for p in found] == ["x.ts", "y.vue"]


def test_llm_pattern_exclude_still_drops_a_top_level_test_file(tmp_path: Path):
    """F1: ``**/test*`` must exclude a ``test_*.py`` directly under the scanned directory."""
    from code_intelligence.llm_pattern_analyzer import LLMPatternAnalyzer

    (tmp_path / "test_top.py").write_text("", encoding="utf-8")
    (tmp_path / "keep.py").write_text("", encoding="utf-8")
    analyzer = LLMPatternAnalyzer(project_root=tmp_path)
    kept = analyzer._collect_files([tmp_path], ["**/test*"])
    assert [p.name for p in kept] == ["keep.py"]
