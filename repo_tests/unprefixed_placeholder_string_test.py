# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15589 -- a triple-quoted or plain string that emits its own placeholder syntax.

A string holding a replacement field with no ``f`` prefix is valid Python
producing valid output, just the wrong output. Nothing in the toolchain sees it:
it is a well-formed literal, so no flake8 code, no bandit check and no type
checker has anything to say. It becomes visible only when the names it strands
happen to trip F841, and only if someone reads that finding instead of
autofixing it. Two accidental hunts found fourteen instances (#14505 / PR
#15584, #15585 / PR #15588), including a monitoring dashboard rendering literal
placeholder text to operators, a script writing it into every commit message it
generated, and ChromaDB documents stored with it and read live by four
semantic-search consumers. None of them raised.

WHY THE NAIVE RULE IS USELESS HERE. "A string with a replacement field naming a
bound name" flags every FastAPI route decorator in the tree -- a handler taking
``item_id`` under a decorator whose path segment names ``item_id`` is exactly
that shape and is one of the commonest string patterns here. A detector that
fires on hundreds of routes gets narrowed until it finds nothing.

THE THREE CONDITIONS, AND WHAT EACH ONE BUYS. Measured over the whole tree
(5,400 files, ~451,000 string constants) while this was built:

* **The field must name an attribute, subscript or call** -- not a bare
  identifier. Route segments are bare identifiers, so this alone removes the
  entire decorator population, and every one of the fourteen known real
  instances survives it. On its own: 172 findings.
* **The field must parse as a Python expression** built only from names,
  attributes, subscripts, calls, constants and arithmetic. This is what
  separates a stranded interpolation from regex source (``[^{}]*(?``), from
  embedded JS and Lua bodies, and from dict literals quoted inside test
  fixtures -- none of which parse. 172 -> 61.
* **The field's root name must be bound somewhere in the module.** This is
  what separates a stranded interpolation from a template addressed to a
  *different* engine: this repository's workflow DSL writes step outputs as
  bare braces resolved later by ``variable_resolver``, and its prompt-injection
  suites deliberately hold poisoned ``format``-syntax fixtures. Neither binds
  the root name. 61 -> 46, and the fifteen it removes were hand-checked: ten
  are the two classes just named, and five are strings whose root is not
  imported at all -- a louder, different defect, tracked as #15614 because
  adding the prefix there would raise ``NameError`` rather than fix anything.

FALSE-POSITIVE RATE ON THE CURRENT TREE: 0 of 46. Every finding in
:data:`KNOWN_UNPREFIXED` was read at its site and is a real stranded
interpolation. The rate is recorded because a guard whose noise is unmeasured
gets tuned down by whoever it annoys first.

WHY A BASELINE RATHER THAN FAIL-CLOSED. 46 sites across 12 files is a backlog,
not a residue, and fixing them is a runtime change to twelve production modules
that has no business riding in the same commit as the detector that found them.
So the census is pinned exactly and may only SHRINK: a new instance fails here,
and every fix must lower its file's count in the same commit. A file whose
count reaches zero must leave the mapping entirely -- a stranded exemption is a
finding, not a pass.

WHY THIS FILE WRITES NO PLACEHOLDER LITERALLY. A guard about placeholder syntax
that contains placeholder syntax reports itself, and the only ways out are an
exemption entry -- the dormant-exemption shape ``check_no_shell_placeholder_paths``
exists to avoid -- or narrowing the rule until it stops matching. Every fixture
below therefore assembles its braces through :func:`_field`, and the shell form
through :func:`_shell_field`, so no single string constant in this module is
ever a replacement field.
"""

from __future__ import annotations

import ast
import builtins
import string
import subprocess  # nosec B404  # fixed argv, no shell, no caller input
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from autobot_shared.paths import scrubbed_git_env

REPO_ROOT = Path(__file__).resolve().parents[1]

# Floors bind to the sweep's REACH, never to its findings. A floor counting
# findings reads "clean" the moment the parser breaks, which is the same answer
# a genuinely clean tree gives with none of the evidence. 5,400 files and
# ~451,000 string constants were reached when this landed; both floors sit far
# enough below that ordinary churn never trips them and far enough above that a
# sweep which lost its reach cannot land under one and still look green.
MIN_FILES_PARSED = 4000
MIN_STRINGS_EXAMINED = 300000

# Directory names that are never repository source under a full-tree sweep.
EXCLUDED_DIR_NAMES = frozenset({".worktrees", "node_modules", "__pycache__", ".venv", "venv"})

#: Nodes a replacement field may be built from. Anything else -- a comparison,
#: a lambda, a walrus -- is not an interpolation someone forgot to prefix.
_ALLOWED_FIELD_NODES: Tuple[type, ...] = (
    ast.Expression,
    ast.Name,
    ast.Attribute,
    ast.Subscript,
    ast.Call,
    ast.Constant,
    ast.Load,
    ast.Slice,
    ast.Tuple,
    ast.List,
    ast.keyword,
    ast.BinOp,
    ast.UnaryOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.USub,
)

#: At least one of these must appear, or the field is a bare name -- the route
#: decorator shape this detector exists to walk past.
_REQUIRED_FIELD_NODES: Tuple[type, ...] = (ast.Attribute, ast.Subscript, ast.Call)

#: Prefixes that mark a quoted f-string *inside* a string -- source code held as
#: data (a generated script, a documented example). Its braces belong to the
#: inner program, not to this one.
_INNER_FSTRING_MARKERS = ('f"', "f'", 'F"', "F'", 'rf"', "rf'", 'fr"', "fr'")

_BUILTIN_NAMES = frozenset(dir(builtins))

#: The opening of a shell/JS template expansion, assembled from parts for the
#: same reason every fixture below is: written whole it would be a finding in
#: this module's own source under a sibling guard.
_SHELL_EXPANSION_PREFIX = "$" + "{"

#: The measured census: repo-relative path -> exact number of stranded
#: interpolations. May only shrink. #15613 tracks draining it.
KNOWN_UNPREFIXED: Dict[str, int] = {
    "autobot-backend/agent_tier_classifier.py": 4,
    "autobot-backend/code_analysis/auto-tools/security_verification.py": 2,
    "autobot-backend/intelligence/goal_processor.py": 5,
    "autobot-backend/intelligence/os_detector.py": 16,
    "autobot-backend/protocols/agent_communication.py": 1,
    "autobot-backend/security/prompt_injection_detector.py": 1,
    "autobot-backend/security/secure_llm_command_parser.py": 2,
    "autobot-backend/security/threat_intelligence.py": 6,
    "autobot-backend/utils/payload_optimizer.py": 5,
    "autobot-infrastructure/shared/scripts/analysis/test_data_layer_debug.py": 1,
    "autobot-infrastructure/shared/scripts/utilities/demo_workflow_system.py": 1,
    "autobot-slm-backend/monitoring/performance_optimizer.py": 2,
}


def _field(expression: str) -> str:
    """A replacement field, assembled rather than written (see the module docstring)."""
    return "{" + expression + "}"


def _shell_field(name: str) -> str:
    """A shell/JS template expansion, assembled for the same reason."""
    return "$" + _field(name)


def _replacement_fields(text: str) -> List[str]:
    """Every replacement field in *text*, or none when it is not a format string.

    ``Formatter.parse`` raises on an unbalanced brace, which is exactly what
    regex source and quoted JS bodies look like -- those are not format strings
    and have no fields to offer.
    """
    try:
        return [field for _, field, _, _ in string.Formatter().parse(text) if field is not None]
    except (ValueError, IndexError):
        return []


def _field_root(field: str) -> Optional[str]:
    """The name a replacement field is ultimately rooted at, or ``None``.

    Returns ``None`` for a field that is not an expression built purely from
    names, attributes, subscripts, calls, constants and arithmetic -- the test
    that separates a stranded interpolation from regex or foreign-language
    source, which does not parse at all.
    """
    try:
        parsed = ast.parse(field, mode="eval")
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        return None
    nodes = list(ast.walk(parsed))
    if not all(isinstance(node, _ALLOWED_FIELD_NODES) for node in nodes):
        return None
    if not any(isinstance(node, _REQUIRED_FIELD_NODES) for node in nodes):
        return None
    return _walk_to_root(parsed.body)


def _walk_to_root(node: ast.AST) -> Optional[str]:
    """Descend an attribute/subscript/call chain to the ``Name`` underneath it."""
    while True:
        if isinstance(node, ast.Attribute):
            node = node.value
        elif isinstance(node, ast.Subscript):
            node = node.value
        elif isinstance(node, ast.Call):
            node = node.func
        elif isinstance(node, ast.BinOp):
            node = node.left
        else:
            return node.id if isinstance(node, ast.Name) else None


def _bound_names(tree: ast.AST) -> Set[str]:
    """Every name the module could interpolate: imports, assignments, defs, params, builtins."""
    names: Set[str] = set(_BUILTIN_NAMES)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update((a.asname or a.name).split(".")[0] for a in node.names)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
            names.update(_parameter_names(node.args))
        elif isinstance(node, ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            names.update(node.names)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
    return names


def _parameter_names(args: ast.arguments) -> Set[str]:
    """Every parameter name on one signature, positional-only through ``**kwargs``."""
    named = list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
    collected = {arg.arg for arg in named}
    collected.update(arg.arg for arg in (args.vararg, args.kwarg) if arg is not None)
    return collected


def _inert_string_ids(tree: ast.AST) -> Set[int]:
    """Ids of strings this detector must never look at: docstrings, ``format`` targets, f-string parts."""
    inert: Set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            _add_docstring(node, inert)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ("format", "format_map"):
                inert.add(id(node.func.value))
        elif isinstance(node, ast.JoinedStr):
            inert.update(id(part) for part in ast.walk(node))
    return inert


def _add_docstring(node: ast.AST, inert: Set[int]) -> None:
    """Record the first-statement docstring of *node*, if it has one."""
    body = getattr(node, "body", None)
    if not body:
        return
    first = body[0]
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
        inert.add(id(first.value))


def stranded_interpolations(source: str) -> List[Tuple[int, str]]:
    """``(line, field)`` for every string in *source* that emits its own placeholder.

    The public entry point: it takes source text, so a fixture and a repository
    file are examined by exactly the same code path. Returns an empty list for
    source that does not parse -- callers count parsed files separately, so a
    syntax error can never masquerade as a clean file.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    return _findings_in(tree)


def _findings_in(tree: ast.AST) -> List[Tuple[int, str]]:
    """Walk one parsed module, applying the three conditions in order."""
    inert = _inert_string_ids(tree)
    names = _bound_names(tree)
    findings: List[Tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in inert or _is_foreign_template(node.value):
            continue
        for field in _replacement_fields(node.value):
            if _field_root(field) in names:
                findings.append((node.lineno, field))
    return findings


def _is_foreign_template(text: str) -> bool:
    """True for shell/JS expansions and for source code held as data."""
    return _SHELL_EXPANSION_PREFIX in text or any(marker in text for marker in _INNER_FSTRING_MARKERS)


def _tracked_python_files() -> Tuple[str, ...]:
    """Every tracked ``.py`` path, git-enumerated so a stray local file cannot join the sweep."""
    listed = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", "ls-files", "*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        env=scrubbed_git_env(),
    )
    paths = [line.replace("\\", "/") for line in listed.stdout.splitlines() if line.strip()]
    return tuple(p for p in paths if not any(part in EXCLUDED_DIR_NAMES for part in Path(p).parts))


@lru_cache(maxsize=1)
def _sweep() -> Tuple[Dict[str, int], int, int]:
    """``(findings-per-file, files parsed, string constants examined)`` over the whole tree.

    Both reach counters are returned alongside the findings so the floors can be
    asserted on what the sweep *touched*, never on what it *found*.
    """
    findings: Dict[str, int] = {}
    parsed = examined = 0
    for relative in _tracked_python_files():
        try:
            source = (REPO_ROOT / relative).read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (OSError, SyntaxError, UnicodeDecodeError, ValueError):
            continue
        parsed += 1
        examined += sum(1 for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str))
        hits = _findings_in(tree)
        if hits:
            findings[relative] = len(hits)
    return findings, parsed, examined


def _assert_reach(parsed: int, examined: int) -> None:
    """The vacuity floor. Reach, not findings -- a broken parser must fail by name."""
    assert parsed >= MIN_FILES_PARSED, (
        f"FIX THE SWEEP: only {parsed} Python files parsed, floor is {MIN_FILES_PARSED}. "
        "A clean result below this floor asserts nothing about the tree."
    )
    assert examined >= MIN_STRINGS_EXAMINED, (
        f"FIX THE SWEEP: only {examined} string constants examined, floor is {MIN_STRINGS_EXAMINED}. "
        "The walk reached files but stopped seeing their strings."
    )


def test_the_sweep_reaches_the_population_it_claims():
    """Floor first, so a collapsed sweep fails by name instead of passing vacuously green."""
    _, parsed, examined = _sweep()
    _assert_reach(parsed, examined)


def test_the_census_is_pinned_and_may_only_shrink():
    """No new stranded interpolation, and no exemption left standing after its fix."""
    findings, parsed, examined = _sweep()
    _assert_reach(parsed, examined)

    grown = {path: n for path, n in findings.items() if n > KNOWN_UNPREFIXED.get(path, 0)}
    assert not grown, (
        "New string(s) emit their own placeholder syntax instead of interpolating it. "
        f"Add the missing f prefix; do not extend the census: {grown}"
    )

    stranded = {path: n for path, n in KNOWN_UNPREFIXED.items() if findings.get(path, 0) < n}
    assert not stranded, (
        "The census over-states the tree -- these were fixed without lowering their entry. "
        f"Lower or remove each in the same commit as its fix (#15613): {stranded}"
    )


# --------------------------------------------------------------------------
# Contrast cases. Every condition gets a pair: one fixture that MUST trip it
# and one that must not. A detector that fires on everything, or on nothing, is
# worse than none, and only a pair can tell those apart from a passing test.
#
# Each fixture builds its braces with `_field` / `_shell_field` so this module's
# own source never contains a replacement field -- see the module docstring.
# --------------------------------------------------------------------------

#: The real site PR #15588 fixed, with its prefix taken back off:
#: ``autobot-backend/api/codebase_analytics/config_duplication_detector.py:510``.
_STRIPPED_PREFIX = 'def report(result):\n    logger.info("Found ' + _field("result['duplicates_found']") + ' values")\n'

#: The same site as it actually stands on the branch.
_KEPT_PREFIX = 'def report(result):\n    logger.info(f"Found ' + _field("result['duplicates_found']") + ' values")\n'


def test_a_stripped_f_prefix_is_caught_at_its_line():
    """The mutation #15589 asks for: take the prefix off a fixed site and it fires, by line and field."""
    assert stranded_interpolations(_STRIPPED_PREFIX) == [(2, "result['duplicates_found']")]


def test_the_same_site_with_its_prefix_is_silent():
    """The other half of the pair -- without it, the test above proves only that something fires."""
    assert stranded_interpolations(_KEPT_PREFIX) == []


def test_a_route_decorator_placeholder_is_not_a_finding():
    """A bare identifier is a path segment, not a stranded interpolation."""
    route = '@router.get("/items/' + _field("item_id") + '")\nasync def read(item_id: str):\n    return item_id\n'
    assert stranded_interpolations(route) == []


def test_an_attribute_field_in_the_same_position_is_a_finding():
    """Contrast to the route case: the position is identical, only the field's shape differs."""
    strung = 'def render(item):\n    return "/items/' + _field("item.id") + '"\n'
    assert stranded_interpolations(strung) == [(2, "item.id")]


def test_regex_source_is_not_a_finding():
    """Escaped braces are a pattern, not a format string -- and they do not parse as an expression."""
    pattern = 'import re\n\n\ndef find(text):\n    return re.findall(r"' + "\\\\{[^{}]*\\\\}" + '", text)\n'
    assert stranded_interpolations(pattern) == []


def test_a_docstring_is_not_a_finding():
    """Prose describing an interpolation is not one."""
    prose = 'def render(cfg):\n    """Emit ' + _field("cfg.name") + ' for the caller."""\n    return cfg\n'
    assert stranded_interpolations(prose) == []


def test_a_string_flowing_into_format_is_not_a_finding():
    """``.format`` is the other way to interpolate, not a missing prefix."""
    formatted = 'def render(cfg):\n    return "Name: ' + _field("cfg.name") + '".format(cfg=cfg)\n'
    assert stranded_interpolations(formatted) == []


def test_a_shell_or_js_template_is_not_a_finding():
    """A dollar-brace expansion belongs to a shell or a JS template literal."""
    shell = 'def script(env):\n    return "echo ' + _shell_field("env.HOME") + '"\n'
    assert stranded_interpolations(shell) == []


def test_a_template_addressed_to_another_engine_is_not_a_finding():
    """The workflow DSL names step outputs that are never Python bindings."""
    dsl = 'STEP = {"inputs": {"kb": "' + _field("kb_search.outputs") + '"}}\n'
    assert stranded_interpolations(dsl) == []


def test_the_same_field_with_its_root_bound_is_a_finding():
    """Contrast to the DSL case: identical text, and the only difference is that the root now exists."""
    bound = 'def build(kb_search):\n    return "' + _field("kb_search.outputs") + '"\n'
    assert stranded_interpolations(bound) == [(2, "kb_search.outputs")]


def test_source_code_held_as_data_is_not_a_finding():
    """A generated program's braces belong to the inner program, not to this one."""
    generated = 'SCRIPT = """\nimport sys\nprint(f"v ' + _field("sys.version") + '")\n"""\n'
    assert stranded_interpolations(generated) == []


def test_the_guard_never_reports_its_own_source():
    """A guard about placeholder syntax that trips on itself gets an exemption or gets narrowed."""
    own = Path(__file__).resolve().read_text(encoding="utf-8")
    assert stranded_interpolations(own) == []
