# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Frontend source files nothing imports (#21583).

The frontend half of the unconnected-code gate. ``ErrorHandler.js``, ``apiErrorHandler.ts`` and
``ApiClientMonitor.js`` sat in ``autobot-frontend/src/utils`` for months, loaded by nothing, each still
carrying logic; no record listed them because the backend detectors only judge Python.

WHAT A CONNECTION IS
--------------------
A candidate (a ``.ts``/``.tsx``/``.js``/``.jsx``/``.mjs``/``.vue`` file under a frontend ``src`` tree) is
connected when another production file, outside comments:

* names it in a quoted path -- ``import x from '@/utils/foo'``, ``import('./foo.js')``, ``require('../foo')``,
  ``export * from './foo'``, a router ``component: () => import(...)`` -- matched on the LAST path segment with
  its extension dropped (``index`` resolves to its directory name; a relative ``./index``/``../index`` is first
  resolved against the importer); or
* matches an ``import.meta.glob(...)`` pattern some OTHER production file uses. The pattern is resolved against the
  importer (``./``, ``../``, ``@/`` and ``/src/``), ``*``, ``**``, ``?`` and ``{a,b}`` are honoured, and a
  ``!negated`` pattern is ignored (it can only over-connect).

An ``.html`` file is read with its ``<!-- -->`` comments removed; its ``<script src>`` elements count.

NOT A CANDIDATE
---------------
``main.ts``/``main.js``/``App.vue`` (the entry points), ``*.d.ts``, ``*.stories.*`` (Storybook loads them by
directory scan), ``*.testHelper.*`` (test support), test files (``is_test_filename``), and
anything under a ``tests``/``test``/``__tests__``/``fixtures``/``testing`` directory.

WHAT THIS CANNOT SEE (known limits, reported as gaps)
-----------------------------------------------------
* Stem matching can mark a file connected falsely: ``a/useFoo.ts`` is "imported" by anything that quotes any
  path ending in ``useFoo``, including a same-named sibling in another directory. The error is toward
  under-reporting, the safe direction for a guard that must not false-fail.
* A file imported only by another unconnected file counts as connected; only the leaf is reported.
* A story file counts as an importer, so a component used only by its story is not reported (under-report;
  decision tracked in #21629).
* A name built at runtime (``import(`./${name}`)``) and a component used by tag name through auto-registration
  have no quoted path.
* An import inside a string that is not an import counts as one.
* CI selection: `python-paths.yml` covers `autobot-frontend/src/**` and `autobot-slm-frontend/src/**` (#17885), so a
  frontend source change runs the python suite and this gate. The pre-push hook selects the gate through the `roots=`
  declared for the frontend reach (`_reach_roots_record.py`).
"""

from __future__ import annotations

import posixpath
import re

from repo_tests._ui_literal_scan import SCRIPT_BODY
from repo_tests._unconnected_common import Tree

from autobot_shared.testfile_names import is_test_filename
from tools.lint._comment_syntax import code_lines, strip_html_comments

#: The frontend source trees whose files are candidates.
FRONTEND_ROOTS = ("autobot-frontend/src", "autobot-slm-frontend/src")
_CODE_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".vue")
_STRIP_SUFFIXES = _CODE_SUFFIXES + (".json",)
_ENTRY_NAMES = frozenset({"main.ts", "main.js", "App.vue"})
_NOT_SOURCE_DIRS = frozenset({"testing"})
_GLOB_TOKENS = {"*": "[^/]*", "?": "[^/]", "{": "(?:", "}": ")", ",": "|"}

_QUOTED_RE = re.compile(r"""["'`]([^"'`\n]{1,300})["'`]""")
_GLOB_CALL_RE = re.compile(r"import\.meta\.glob\s*(?:<[^()]*?>)?\s*\(\s*(\[[^\]]*\]|[\"'`][^\"'`]*[\"'`])")


def candidates(tree: Tree) -> list[str]:
    """Production frontend source files that could have an importer."""
    return [
        rel
        for rel in tree.select(*_CODE_SUFFIXES, under=FRONTEND_ROOTS)
        if rel.rsplit("/", 1)[-1] not in _ENTRY_NAMES
        and not rel.endswith(".d.ts")
        and ".stories." not in rel
        and ".testHelper." not in rel
        and not is_test_filename(rel)
        and not _NOT_SOURCE_DIRS.intersection(rel.split("/")[:-1])
    ]


def stem(rel_or_spec: str) -> str:
    """The last path segment, extension dropped; ``index`` resolves to the directory it sits in."""
    parts = [p for p in rel_or_spec.split("/") if p not in ("", ".", "..")]
    if not parts:
        return ""
    last = parts[-1]
    for suffix in _STRIP_SUFFIXES:
        if last.endswith(suffix):
            last = last[: -len(suffix)]
            break
    if last == "index" and len(parts) > 1:
        return parts[-2]
    return last


def code_text(rel: str, text: str) -> str:
    """*text* without comments; HTML loses only its ``<!-- -->`` comments (an entry ``<script src>`` is not one).

    A ``.vue`` file contributes its ``<script>`` blocks only: a template's prose holds apostrophes and ``//`` that a
    comment scanner would read as the start of a string or comment, swallowing the real imports below it.
    """
    if rel.endswith(".html"):
        return strip_html_comments(text)
    name = rel
    if rel.endswith(".vue"):
        text, name = "\n".join(SCRIPT_BODY.findall(text)), "script.ts"
    return "\n".join(line.text for line in code_lines(text, name=name, strip_trailing=True))


def _spec_stem(spec: str, importer: str) -> str:
    """The stem *spec* names. A relative path to an ``index`` is resolved against *importer* first, so ``./index``
    names the importer's directory, as the candidate ``<dir>/index.ts`` does."""
    name = stem(spec)
    if name == "index" and spec.startswith(("./", "../")):
        return stem(posixpath.normpath(posixpath.join(posixpath.dirname(importer), spec)))
    return name


def quoted_stems(code: str, importer: str) -> set[str]:
    """Stems of every quoted path in *code* from *importer* (a string holding a ``/`` or starting with a dot)."""
    specs = (spec for spec in _QUOTED_RE.findall(code) if "/" in spec or spec.startswith("."))
    return {_spec_stem(spec, importer) for spec in specs} - {""}


def _project_root(rel: str) -> str:
    return rel.split("/", 1)[0]


def _resolve(pattern: str, importer: str) -> str | None:
    """A glob pattern as a repo-relative glob, or ``None`` for a negation or a bare package pattern."""
    if pattern.startswith("!"):
        return None
    project = _project_root(importer)
    if pattern.startswith("@/"):
        return posixpath.normpath(f"{project}/src/{pattern[2:]}")
    if pattern.startswith("/"):
        return posixpath.normpath(f"{project}{pattern}")
    if pattern.startswith("."):
        return posixpath.normpath(posixpath.join(posixpath.dirname(importer), pattern))
    return None


def glob_patterns(importer: str, code: str) -> list[str]:
    """Repo-relative glob patterns every ``import.meta.glob(...)`` call in *code* (from *importer*) names."""
    found: list[str] = []
    for argument in _GLOB_CALL_RE.findall(code):
        for raw in re.findall(r"""["'`]([^"'`]+)["'`]""", argument):
            resolved = _resolve(raw, importer)
            if resolved:
                found.append(resolved)
    return found


def glob_regex(pattern: str) -> re.Pattern[str]:
    """The regex a ``*``/``**``/``?``/``{a,b}`` glob means; ``*`` and ``?`` never cross a ``/``."""
    out: list[str] = []
    depth, i = 0, 0
    while i < len(pattern):
        char = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
            continue
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
            continue
        depth += (char == "{") - (char == "}" and depth > 0)
        out.append(_GLOB_TOKENS.get(char, re.escape(char)) if char != "," or depth else re.escape(char))
        i += 1
    return re.compile("".join(out))


def _importer_index(tree: Tree) -> tuple[dict[str, set[str]], list[tuple[str, re.Pattern[str]]]]:
    """``({stem: importing files}, [(importer, glob regex)])`` over every production source file in the tree."""
    importers: dict[str, set[str]] = {}
    globs: list[tuple[str, re.Pattern[str]]] = []
    for rel in tree.select(*_CODE_SUFFIXES, ".html"):
        code = code_text(rel, tree.text(rel))
        for name in quoted_stems(code, rel):
            importers.setdefault(name, set()).add(rel)
        globs.extend((rel, glob_regex(p)) for p in glob_patterns(rel, code))
    return importers, globs


def unconnected(tree: Tree, cands: list[str] | None = None) -> list[str]:
    """Candidates no other production file imports or reaches with an ``import.meta.glob``, sorted."""
    cands = candidates(tree) if cands is None else cands
    importers, globs = _importer_index(tree)
    out = []
    for rel in cands:
        if importers.get(stem(rel), set()) - {rel}:
            continue
        if any(importer != rel and g.fullmatch(rel) for importer, g in globs):
            continue
        out.append(rel)
    return sorted(out)
