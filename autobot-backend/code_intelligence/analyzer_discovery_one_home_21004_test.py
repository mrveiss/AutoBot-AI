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

from autobot_shared.testfile_names import is_test_filename

_PKG = Path(__file__).resolve().parent
_CANONICAL = "python_files.py"
_WALKS = {"rglob", "walk"}
_COPY_NAMES = {"EXCLUDE_DIRS", "DEFAULT_EXCLUDE_DIRS", "_SKIP_DIRS", "_COCHANGE_SKIP_DIRS"}
_PATH_CTORS = {"Path", "PurePath", "PurePosixPath"}
_PATH_ARG = re.compile(r"(?i)(path|file|rel)")
# A name that reads as an exclusion/ignore list. Bound to a literal collection of
# strings it is a local copy of the exclusion rule (#21004 AC1/AC2).
_IGNORE_LIST_NAME = re.compile(r"^_?(default_)?(exclude|excludes|ignore|skip)[a-z_]*$", re.IGNORECASE)
# Pattern lists that are policy globs consumed by ``matches_exclusion`` (no directory
# names, no predicate of their own). Each entry needs a reason; a stale entry fails.
_ALLOWED_POLICY_LISTS = {
    ("shared/analysis_base.py", "DEFAULT_EXCLUDE_PATTERNS"): "BaseCodeAnalyzer family's own file-glob policy",
    ("multi_language_scanner.py", "default_excludes"): "project log tree; dir names come from SKIP_DIRS",
    ("llm_pattern_analyzer.py", "exclude_patterns"): "caller default, applied through matches_exclusion",
    ("base_analyzer.py", "default_excludes"): "minified-bundle globs, applied through matches_exclusion",
    ("anti_pattern_detection/types.py", "DEFAULT_IGNORE_PATTERNS"): "ANALYSIS_EXCLUDE_DIRS plus bytecode globs",
    # An INCLUDE match (which pre-commit checks apply to a file), not an exclusion.
    ("precommit_analyzer.py", "<module>"): "fnmatch import: check applicability, not file exclusion",
    # Deferred to the open PR that owns this file (#21162): regex exclude list, still to be converted.
    ("testing_pattern_analyzer.py", "exclude_patterns"): "regex list; converts with #21162",
    ("testing_pattern_analyzer.py", "_should_exclude"): "regex exclusion; converts with #21162",
    ("testing_pattern_analyzer.py", "is_test_file"): "test_file_patterns classification; converts with #21162",
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
        if p.name != _CANONICAL and not is_test_filename(p.name) and "tests" not in p.relative_to(root).parts
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
    """A list/tuple/set literal holding a string constant, also behind ``x or [...]``."""
    if isinstance(value, ast.BoolOp):
        return any(_is_string_collection(v) for v in value.values)
    if not isinstance(value, (ast.List, ast.Tuple, ast.Set)):
        return False
    return any(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in value.elts)


def _ignore_list_copies(node: ast.AST) -> List[str]:
    """Names (plain or attribute) bound to a literal exclusion list: a local copy of the rule."""
    if not _is_string_collection(getattr(node, "value", None)):
        return []
    return [name for name in _assigned_names(node) if _IGNORE_LIST_NAME.match(name)]


def _compiled_regex_names(tree: ast.AST) -> Set[str]:
    """Names bound to ``re.compile(...)``: their ``.match`` is a regex, not a file-name predicate."""
    names: Set[str] = set()
    for node in ast.walk(tree):
        value = getattr(node, "value", None)
        if isinstance(value, ast.Call) and getattr(value.func, "attr", "") == "compile":
            names.update(_assigned_names(node))
    return names


def _match_receiver(node: ast.Call) -> str | None:
    """The receiver name of ``<recv>.match(<path-like>)`` (``""`` when anonymous), else ``None``.

    Keyed on the argument OR the receiver being path-like (``p.match(file_path)``,
    ``file_path.match(p)``, ``Path(x).match(g)``) whatever the other side is called;
    ``rx.match(line)`` is not.
    """
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr == "match" and node.args):
        return None
    arg, owner = node.args[0], func.value
    names = [
        (n.id if isinstance(n, ast.Name) else n.attr if isinstance(n, ast.Attribute) else "") for n in (arg, owner)
    ]
    is_ctor = isinstance(owner, ast.Call) and getattr(owner.func, "id", "") in _PATH_CTORS
    if not (is_ctor or any(_PATH_ARG.search(n) for n in names)):
        return None
    return names[1]


def _is_filename_predicate(node: ast.AST, regexes: Set[str]) -> str:
    """The rule broken by a local file-name match (``fnmatch``, ``<anything>.match(x)``)."""
    if isinstance(node, ast.ImportFrom) and node.module == "fnmatch":
        return "local fnmatch"
    if isinstance(node, ast.Import) and any(a.name == "fnmatch" for a in node.names):
        return "local fnmatch"
    receiver = _match_receiver(node) if isinstance(node, ast.Call) else None
    if receiver is None or receiver == "re" or receiver in regexes:
        return ""
    return "local .match() predicate"


def _enclosing_symbols(tree: ast.AST) -> dict:
    """``id(node) -> name`` of the function that contains it (``<module>`` at top level)."""
    owners: dict = {}

    def visit(node: ast.AST, owner: str) -> None:
        for child in ast.iter_child_nodes(node):
            inner = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else owner
            owners[id(child)] = inner
            visit(child, inner)

    visit(tree, "<module>")
    return owners


def _predicate_violations(node: ast.AST, rel: str, symbol: str, regexes: Set[str], allowed: dict) -> List[str]:
    rule = _is_filename_predicate(node, regexes)
    found = [f"{rel}:{node.lineno} {rule} [{symbol}]"] if rule and (rel, symbol) not in allowed else []
    for name in _ignore_list_copies(node):
        if (rel, name) not in allowed:
            found.append(f"{rel}:{node.lineno} local ignore list {name} [{name}]")
    return found


def find_violations(root: Path, allowed: dict | None = None) -> List[str]:
    """``file:line what`` for each bare walk call or analyzer-local exclusion-set copy."""
    allowed = _ALLOWED_POLICY_LISTS if allowed is None else allowed
    found: List[str] = []
    for path in _production_files(root):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        os_names = _os_walker_names(tree)
        owners, regexes = _enclosing_symbols(tree), _compiled_regex_names(tree)
        for node in ast.walk(tree):
            rule = _call_violation(node, os_names) if isinstance(node, ast.Call) else _import_violation(node)
            if rule:
                found.append(f"{path.relative_to(root)}:{node.lineno} {rule}")
            for name in _assigned_names(node):
                if name in _COPY_NAMES:
                    found.append(f"{path.relative_to(root)}:{node.lineno} local {name}")
            if hasattr(node, "lineno"):
                found.extend(
                    _predicate_violations(
                        node, path.relative_to(root).as_posix(), owners.get(id(node), "<module>"), regexes, allowed
                    )
                )
    return found


def _target_name(target: ast.expr) -> str:
    return target.id if isinstance(target, ast.Name) else target.attr if isinstance(target, ast.Attribute) else ""


def _assigned_names(node: ast.AST) -> List[str]:
    """Names bound by an assignment, including ``self.<attr>`` targets."""
    if isinstance(node, ast.Assign):
        return [n for n in (_target_name(t) for t in node.targets) if n]
    if isinstance(node, ast.AnnAssign):
        return [n for n in [_target_name(node.target)] if n]
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
    "local ignore list exclude_patterns": "class A:\n    def __init__(self, exclude_patterns=None):\n        self.exclude_patterns = exclude_patterns or ['*.pyc']\n",
    "local .match() predicate": "def f(file_path, pats):\n    return any(file_path.match(p) for p in pats)\n",
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


@pytest.mark.parametrize(
    "source",
    [
        "def f(path, pats):\n    return any(p.match(path) for p in pats)\n",
        "def f(x, pats):\n    return any(path.match(x) for path in pats)\n",
        "import re\n\nclass A:\n    def f(self, file_path):\n        return self._exclude.match(file_path)\n",
    ],
)
def test_guard_flags_short_and_attribute_receivers(tmp_path: Path, source: str):
    (tmp_path / "bad.py").write_text(source, encoding="utf-8")
    assert any(".match() predicate" in f for f in find_violations(tmp_path))


def test_guard_does_not_flag_a_compiled_regex_match(tmp_path: Path):
    source = "import re\n_RX = re.compile('x')\n\ndef f(file_path):\n    return _RX.match(file_path)\n"
    (tmp_path / "ok.py").write_text(source, encoding="utf-8")
    assert find_violations(tmp_path) == []


def test_guard_flags_a_path_constructor_match(tmp_path: Path):
    (tmp_path / "bad.py").write_text(
        "from pathlib import Path\n\ndef f(x, g):\n    return Path(x).match(g)\n", encoding="utf-8"
    )
    assert any(".match() predicate" in f for f in find_violations(tmp_path))


@pytest.mark.parametrize(
    "source", ["import re\n\ndef f(line, rx):\n    return rx.match(line)\n", "SKIP_REASONS = []\n"]
)
def test_guard_does_not_flag_regex_match_or_an_empty_list(tmp_path: Path, source: str):
    (tmp_path / "ok.py").write_text(source, encoding="utf-8")
    assert find_violations(tmp_path) == []


def test_allowed_policy_lists_are_all_still_present():
    """A stale entry would silently exempt a future copy of the same symbol: each must still be a real hit."""
    hits = find_violations(_PKG, allowed={})
    for rel, symbol in _ALLOWED_POLICY_LISTS:
        assert any(h.startswith(f"{rel}:") and h.endswith(f"[{symbol}]") for h in hits), (rel, symbol)


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

    module = _load_real_module()
    assert SKIP_DIRS | module.PACKAGE_AWARE_NON_CODE_NAMES | {".mypy_cache"} == module.ANALYSIS_EXCLUDE_DIRS


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


def _touch(root: Path, *rels: str) -> None:
    for rel in rels:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("", encoding="utf-8")


def test_the_real_backup_package_is_discovered():
    """autobot-backend/backup/ is a real package (imported by the lifespan): never skipped by name."""
    found = {p.relative_to(_PKG.parent).as_posix() for p in _load_real_module().discover_files(_PKG.parent / "backup")}
    assert "backup/scheduler.py" in found


@pytest.mark.parametrize("name", ["backup", "backups", "archive", "archives", "third_party"])
def test_a_package_named_like_an_archive_dir_is_kept_and_a_plain_dir_is_skipped(tmp_path: Path, name: str):
    module = _load_real_module()
    _touch(tmp_path, f"{name}/__init__.py", f"{name}/real.py", f"plain/{name}/dead.py", "plain/live.py")
    found = {p.relative_to(tmp_path).as_posix() for p in module.discover_files(tmp_path)}
    assert f"{name}/real.py" in found
    assert f"plain/{name}/dead.py" not in found  # control: a non-package dir of that name is still skipped
    assert "plain/live.py" in found


def test_mypy_cache_is_skipped_even_with_an_init_file(tmp_path: Path):
    _touch(tmp_path, ".mypy_cache/__init__.py", ".mypy_cache/x.py", "a.py")
    assert [p.name for p in _load_real_module().discover_files(tmp_path)] == ["a.py"]


def test_is_excluded_and_matches_exclusion_are_package_aware(tmp_path: Path):
    module = _load_real_module()
    _touch(tmp_path, "backup/__init__.py", "backup/s.py", "old/backup/x.py")
    assert not module.is_excluded(tmp_path / "backup" / "s.py", tmp_path, module.ANALYSIS_EXCLUDE_DIRS)
    assert module.is_excluded(tmp_path / "old" / "backup" / "x.py", tmp_path, module.ANALYSIS_EXCLUDE_DIRS)
    assert not module.matches_exclusion(tmp_path / "backup" / "s.py", (), tmp_path)
    assert module.matches_exclusion(tmp_path / "old" / "backup" / "x.py", (), tmp_path)


@pytest.mark.parametrize("ancestor", ["build", "venv", "lib", "test"])
def test_a_root_under_a_pattern_named_dir_is_not_excluded(tmp_path: Path, ancestor: str):
    module = _load_real_module()
    root = tmp_path / ancestor / "proj"
    _touch(root, "pkg/a.py")
    assert not module.matches_exclusion(root / "pkg" / "a.py", [ancestor], root)


def test_a_plain_word_matches_whole_components_only(tmp_path: Path):
    module = _load_real_module()
    for rel, word, expected in [
        ("rebuild.py", "build", False),
        ("build/x.py", "build", True),
        ("library/x.py", "lib", False),
        ("lib/x.py", "lib", True),
        ("latest.py", "test", False),
        ("test/x.py", "test", True),
        ("a/gen/x.py", "gen/x.py", True),
        ("a/gen2/x.py", "gen/x.py", False),
    ]:
        assert module.matches_exclusion(tmp_path / rel, [word], tmp_path) is expected, (rel, word)


def test_star_stays_inside_one_component_and_double_star_spans(tmp_path: Path):
    module = _load_real_module()
    for rel, pattern, expected in [
        ("a/tests/x.py", "**/tests/**", True),
        ("tests/a/b/x.py", "**/tests/**", True),
        ("a/b/tests", "tests/*", False),
        ("tests/a/x.py", "tests/*", False),  # one-level star: does not cross a second "/"
        ("tests/x.py", "tests/*", True),
        ("a/x.min.js", "**/*.min.js", True),
        ("src/pkg/gen/x.py", "src/*/x.py", False),
        ("src/gen/x.py", "src/*/x.py", True),
    ]:
        assert module.matches_exclusion(tmp_path / rel, [pattern], tmp_path) is expected, (rel, pattern)


def test_a_namespace_package_named_backup_is_skipped_today(tmp_path: Path):
    """Pins the documented limit: the package check looks only at ``<dir>/__init__.py`` (PEP 420 is not seen)."""
    _touch(tmp_path, "backup/ns.py", "pkg/backup/nested.py", "pkg/__init__.py", "pkg/real.py")
    found = {p.relative_to(tmp_path).as_posix() for p in _load_real_module().discover_files(tmp_path)}
    assert found == {"pkg/__init__.py", "pkg/real.py"}  # backup/ and pkg/backup/ are skipped


def test_a_nested_package_named_backup_with_init_is_kept(tmp_path: Path):
    _touch(tmp_path, "pkg/__init__.py", "pkg/backup/__init__.py", "pkg/backup/s.py")
    found = {p.relative_to(tmp_path).as_posix() for p in _load_real_module().discover_files(tmp_path)}
    assert "pkg/backup/s.py" in found


def test_a_non_python_backup_dir_holding_source_is_kept_for_a_walk_that_selects_it(tmp_path: Path):
    module = _load_real_module()
    _touch(tmp_path, "src/backup/view.vue", "src/backup/api.ts", "src/archive/notes.txt", "src/ok.ts")
    ts_walk = {p.relative_to(tmp_path).as_posix() for p in module.discover_files(tmp_path, ("*.ts", "*.vue"))}
    assert ts_walk == {"src/backup/view.vue", "src/backup/api.ts", "src/ok.ts"}
    every = {p.relative_to(tmp_path).as_posix() for p in module.discover_files(tmp_path, ("*",))}
    assert "src/backup/view.vue" in every and "src/archive/notes.txt" not in every  # no source there: still skipped
    # Control, other direction: a Python-only walk selects none of it, so the __init__ test decides.
    assert module.discover_files(tmp_path, ("*.py",)) == []


def test_matches_exclusion_keeps_a_foreign_source_file_in_a_backup_dir(tmp_path: Path):
    module = _load_real_module()
    _touch(tmp_path, "src/backup/view.vue", "src/backup/dead.py")
    assert not module.matches_exclusion(tmp_path / "src/backup/view.vue", (), tmp_path)
    assert module.matches_exclusion(tmp_path / "src/backup/dead.py", (), tmp_path)


def test_the_walk_and_the_predicate_agree_per_file_in_a_mixed_backup_dir(tmp_path: Path):
    """``src/backup/`` holds ``view.vue`` and ``dead.py``: the walk yields exactly what ``matches_exclusion`` keeps."""
    module = _load_real_module()
    _touch(tmp_path, "src/backup/view.vue", "src/backup/dead.py", "src/ok.py")
    for patterns in (("*.py",), ("*.vue", "*.py"), ("*",)):
        walked = {p.relative_to(tmp_path).as_posix() for p in module.discover_files(tmp_path, patterns)}
        candidates = [p for p in tmp_path.rglob("*") if p.is_file() and any(p.match(g) for g in patterns)]
        kept = {p.relative_to(tmp_path).as_posix() for p in candidates if not module.matches_exclusion(p, (), tmp_path)}
        assert walked == kept, patterns
    vue_walk = {p.relative_to(tmp_path).as_posix() for p in module.discover_files(tmp_path, ("*.vue", "*.py"))}
    assert "src/backup/dead.py" not in vue_walk  # excluded by the predicate, so absent from the walk
    assert "src/backup/view.vue" in vue_walk  # foreign source the walk scans: kept


def test_base_analyzer_and_multi_language_scanner_walks_reach_a_non_python_backup_dir(tmp_path: Path):
    from code_intelligence.base_analyzer import MultiLanguageAnalyzer

    _touch(tmp_path, "src/backup/view.ts", "src/plain/view.ts")
    analyzer = MultiLanguageAnalyzer()
    files = {p.relative_to(tmp_path).as_posix() for p in analyzer._collect_files_to_analyze(tmp_path, True, None)}
    # Control: the backup/ file is treated exactly like the same file in an ordinary dir.
    assert ("src/backup/view.ts" in files) == ("src/plain/view.ts" in files)
    assert {p.name for p in _load_real_module().discover_files(tmp_path, ("*",))} == {"view.ts"}
    assert len(_load_real_module().discover_files(tmp_path, ("*",))) == 2
