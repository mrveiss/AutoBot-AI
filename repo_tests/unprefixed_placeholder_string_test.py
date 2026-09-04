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
  the root name. 61 -> 46.

FALSE-POSITIVE RATE: 0 of 46. Every one was read at its site and repaired by
#15613, so :data:`KNOWN_UNPREFIXED` is empty and this category is now
fail-closed: a new instance fails here instead of joining a census. The rate is
recorded because a guard whose noise is unmeasured gets tuned down by whoever
it annoys first.

WHAT THE NARROWING DROPS, AND WHERE IT WENT. The first and third conditions buy
their precision by discarding a class each, and a discarded class nobody counts
is a class that grows back. Both now have their own fail-closed category here,
narrowed until the noise the parent condition removed stays removed:

* **Bare identifiers (#15617).** 1,487 in the tree -- which is why the first
  condition drops them -- but review found four real missing-``f`` bugs of that
  shape sitting inside blocks this guard already flagged. A stranded
  interpolation rarely travels alone, so :func:`companion_interpolations` keeps
  a bare field only where a qualifying finding already stands beside it: in the
  same string, or in the same enclosing function. 1,487 -> 8, every one of the
  eight real and repaired by #15613. Decorator strings are excluded by name,
  because ``decorator_list`` hangs off the function node and a route path would
  otherwise ride in on its own handler's finding. The enclosing *module* is
  deliberately not a scope: at file granularity the same rule readmits all 35
  bare fields of the twelve files this guard flagged, which is the swamping the
  first condition exists to prevent. Those 35 were read and repaired by #15613
  as well, so the class is empty today -- but the rule holds only 8 of them. A
  bare field alone in a module-level block reaches no anchor
  (``secure_llm_command_parser.py`` line 484 was one), and that is the price of
  not readmitting 1,479 route segments. Recorded here so the next reader does
  not re-litigate the exclusion.
* **Roots the module never imports (#15614).** 15 in the tree, of which ten are
  the workflow-DSL templates and poison fixtures the third condition exists to
  remove, plus a dict comprehension quoted inside a markdown code sample. Every
  one of the five real ones reached for a *standard-library module* that the
  file never imported, so :func:`unimported_module_interpolations` requires
  exactly that: 15 -> 5, with none of the ten. Adding ``f`` to those would have
  raised ``NameError`` rather than fixed anything; #15613 gave them the import
  they were reaching for instead.

WHY THIS FILE WRITES NO PLACEHOLDER LITERALLY. A guard about placeholder syntax
that contains placeholder syntax reports itself, and the only ways out are an
exemption entry -- the dormant-exemption shape ``check_no_shell_placeholder_paths``
exists to avoid -- or narrowing the rule until it stops matching. Every fixture
below therefore assembles its braces through :func:`_field`, and the shell form
through :func:`_shell_field`, so no single string constant in this module is
ever a replacement field. The same holds for ``unprefixed_placeholder_scan``,
the sibling module carrying the engine -- these two were one file until the
third category pushed it past the 600-line ceiling, and
:func:`test_neither_half_of_the_guard_ever_reports_its_own_source` asserts the
property over both halves rather than only the one holding the tests.
"""

from pathlib import Path
from typing import Dict

from repo_tests.unprefixed_placeholder_scan import (
    companion_interpolations,
    stranded_interpolations,
    sweep,
    unimported_module_interpolations,
)

#: The engine this module asserts over. Named here so the self-report test
#: below covers both halves of the split, not only the half holding the tests.
_SCAN_MODULE = Path(__file__).resolve().parent / "unprefixed_placeholder_scan.py"

# Floors bind to the sweep's REACH, never to its findings. A floor counting
# findings reads "clean" the moment the parser breaks, which is the same answer
# a genuinely clean tree gives with none of the evidence. 5,400 files and
# ~451,000 string constants were reached when this landed; both floors sit far
# enough below that ordinary churn never trips them and far enough above that a
# sweep which lost its reach cannot land under one and still look green. All
# three categories share them because all three share the one sweep.
MIN_FILES_PARSED = 4000
MIN_STRINGS_EXAMINED = 300000

#: The measured census: repo-relative path -> exact number of stranded
#: interpolations. Drained to empty by #15613, which makes the first category
#: fail-closed. The shrink-only mechanism stays -- an entry may only ever be
#: lowered or removed, and a file reaching zero must leave the mapping -- so a
#: future backlog can be pinned the same way instead of silencing the guard.
KNOWN_UNPREFIXED: Dict[str, int] = {}


def _field(expression: str) -> str:
    """A replacement field, assembled rather than written (see the module docstring)."""
    return "{" + expression + "}"


def _shell_field(name: str) -> str:
    """A shell/JS template expansion, assembled for the same reason."""
    return "$" + _field(name)


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


def _category(name: str) -> Dict[str, int]:
    """One category's findings-per-file, with the shared reach floor asserted first."""
    findings, parsed, examined = sweep()
    _assert_reach(parsed, examined)
    return findings[name]


def test_the_sweep_reaches_the_population_it_claims():
    """Floor first, so a collapsed sweep fails by name instead of passing vacuously green."""
    _, parsed, examined = sweep()
    _assert_reach(parsed, examined)


def test_the_census_is_pinned_and_may_only_shrink():
    """No new stranded interpolation, and no exemption left standing after its fix."""
    findings = _category("stranded")

    grown = {path: n for path, n in findings.items() if n > KNOWN_UNPREFIXED.get(path, 0)}
    assert not grown, (
        "New string(s) emit their own placeholder syntax instead of interpolating it. "
        f"Add the missing f prefix; do not extend the census -- #15613 drained it: {grown}"
    )

    stranded = {path: n for path, n in KNOWN_UNPREFIXED.items() if findings.get(path, 0) < n}
    assert not stranded, (
        "The census over-states the tree -- these were fixed without lowering their entry. "
        f"Lower or remove each in the same commit as its fix: {stranded}"
    )


def test_no_bare_identifier_is_stranded_beside_a_qualifying_one():
    """#15617 -- the excluded half, narrowed to where it cannot swamp the signal."""
    findings = _category("companion")
    assert not findings, (
        "A bare-identifier replacement field stands in the same string or the same function as a "
        f"stranded one. Add the missing f prefix, or pass it as a lazy-logging argument: {findings}"
    )


def test_no_field_reaches_for_a_module_the_file_never_imports():
    """#15614 -- the prefix alone raises NameError here, so the import is the fix."""
    findings = _category("unimported_module")
    assert not findings, (
        "A replacement field is rooted at a standard-library module this file never imports. "
        f"Add the import as well as the prefix -- the prefix alone raises NameError: {findings}"
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
    assert unimported_module_interpolations(dsl) == []


def test_the_same_field_with_its_root_bound_is_a_finding():
    """Contrast to the DSL case: identical text, and the only difference is that the root now exists."""
    bound = 'def build(kb_search):\n    return "' + _field("kb_search.outputs") + '"\n'
    assert stranded_interpolations(bound) == [(2, "kb_search.outputs")]


def test_source_code_held_as_data_is_not_a_finding():
    """A generated program's braces belong to the inner program, not to this one."""
    generated = 'SCRIPT = """\nimport sys\nprint(f"v ' + _field("sys.version") + '")\n"""\n'
    assert stranded_interpolations(generated) == []


#: A bare identifier with nothing stranded near it -- the 1,487-strong population #15617 measured.
_BARE_ALONE = 'def render(label):\n    return "name ' + _field("label") + '"\n'

#: The same bare field one line under a qualifying finding in the same function.
_BARE_BESIDE = (
    "def render(item, label):\n"
    '    logger.info("id ' + _field("item.id") + '")\n'
    '    logger.info("name ' + _field("label") + '")\n'
)

#: A route path segment in the decorator of a handler that does hold a real finding.
_ROUTE_BESIDE = (
    '@router.get("/items/' + _field("item_id") + '")\n'
    "def read(item_id, item):\n"
    '    logger.info("id ' + _field("item.id") + '")\n'
)


def test_a_lone_bare_identifier_is_not_a_companion_finding():
    """Without an anchor the bare half stays excluded -- otherwise every route decorator comes back."""
    assert companion_interpolations(_BARE_ALONE) == []


def test_a_bare_identifier_beside_a_stranded_one_is_a_companion_finding():
    """The other half of the pair: identical field, and only what stands beside it differs."""
    assert companion_interpolations(_BARE_BESIDE) == [(3, "label")]


def test_a_route_path_never_rides_in_on_its_own_handlers_finding():
    """``decorator_list`` hangs off the function node, so the path segment is excluded by name."""
    assert companion_interpolations(_ROUTE_BESIDE) == []
    assert stranded_interpolations(_ROUTE_BESIDE) == [(3, "item.id")]


#: The #15614 shape: a field reaching for ``json`` in a file that never imports it.
_UNIMPORTED_ROOT = 'def dump(payload):\n    logger.info("' + _field("json.dumps(payload)") + '")\n'

#: The same text in a file that does import it -- a stranded interpolation, not a NameError.
_IMPORTED_ROOT = 'import json\n\n\ndef dump(payload):\n    logger.info("' + _field("json.dumps(payload)") + '")\n'


def test_a_field_rooted_at_an_unimported_stdlib_module_is_a_finding():
    """Adding the prefix alone would raise NameError, which is why this is its own category."""
    assert unimported_module_interpolations(_UNIMPORTED_ROOT) == [(2, "json.dumps(payload)")]
    assert stranded_interpolations(_UNIMPORTED_ROOT) == []


def test_the_same_field_with_the_import_present_is_the_ordinary_kind():
    """The pair's other half: one import line moves the identical field between categories."""
    assert unimported_module_interpolations(_IMPORTED_ROOT) == []
    assert stranded_interpolations(_IMPORTED_ROOT) == [(5, "json.dumps(payload)")]


def test_neither_half_of_the_guard_ever_reports_its_own_source():
    """A guard about placeholder syntax that trips on itself gets an exemption or gets narrowed."""
    for path in (Path(__file__).resolve(), _SCAN_MODULE):
        own = path.read_text(encoding="utf-8")
        assert stranded_interpolations(own) == [], path.name
        assert companion_interpolations(own) == [], path.name
        assert unimported_module_interpolations(own) == [], path.name
