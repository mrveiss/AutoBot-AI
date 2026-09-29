# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Three historical ingestion paths still call the redactor (#13708 review, #16985).

**This guard is not the coverage argument, and its list is not the set of ingestion
entry points.** Read `_AUTHORITATIVE_GUARDS` below before drawing any conclusion
about what is protected.

Credential redaction for knowledge writes is enforced at a single chokepoint --
`sanitize_fact_content` in `autobot-backend/knowledge/ingest_sanitize.py`, which calls
`redact_content` -- and the guards that prove it are discovery-based: they walk every
transitive connector subclass and every durable-store write rather than naming paths.
A connector added tomorrow is covered without anyone editing a list.

What remains here is narrower and deliberately so: the three specific paths that
#13708's review found unguarded and #16895 fixed. Verifying they *still* call the
redactor directly is a second layer under the chokepoint, not a statement about
completeness.

## Why this docstring exists

The three-entry list is correct and was never wrong. But under the chokepoint design
it became **misleading by understatement**: a reader who found this file first would
conclude coverage was three entry points when the real coverage is every write path
(#16985's remaining criterion). That is the mirror image of the usual defect -- a
guard whose name claims more than its mechanism enforces. Here the mechanism enforces
less than the system actually guarantees, and the cost is the same: a reader acts on
the wrong number.

So the list keeps its job and loses its implied scope. `_HISTORICAL_ENTRY_POINTS` says
what it is; `_ENTRY_POINTS` read like the answer to "which are the entry points".

## Why the pointer is asserted rather than written

`test_the_authoritative_guards_still_exist` fails if any guard named above is gone.
Without it this docstring is a cross-reference that rots silently the moment those
files are renamed -- and a stale comment describing a mechanism is worse than none,
because it is read in preference to the code. That failure cost three sessions a wrong
diagnosis on 2026-09-27 (`chromadb_client.py`'s "os.getenv-based" comment above a line
that read the SSOT default).

## Why this is still not tree-scanning

"extracts external content and returns it for indexing" is not a discoverable
syntactic pattern the way a route decorator or an import is, so `repo_tests._reach`'s
machinery does not fit -- see PR #16939's review, where a guard that DID need a reach
floor shipped without one. The discovery that *is* possible happens in the
authoritative guards, keyed on connector subclassing and store writes. Duplicating it
here would put one rule in two places, which is the defect this file is being edited
to stop describing.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import textwrap
from pathlib import Path

import pytest

#: The three paths #13708's review found unguarded and #16895 fixed. NOT the set of
#: ingestion entry points -- see the module docstring. Named for what it is so the
#: next reader cannot mistake its length for a coverage number.
_HISTORICAL_ENTRY_POINTS = [
    ("knowledge.connectors.gdrive", "GoogleDriveConnector.fetch_content"),
    ("knowledge.connectors.onedrive", "OneDriveConnector.fetch_content"),
    ("api.knowledge", "upload_file_to_knowledge"),
]

#: The guards that actually establish coverage, and the test in each that does the
#: establishing. Mapped rather than listed, because the previous version asserted
#: only that the FILES existed -- and a file can survive the deletion of the test
#: that made it authoritative. `is_file()` is satisfied by an empty file.
#:
#: The connector row is the one that mattered (#17732 review). This list named
#: `connector_redaction_functional_test.py`, which has twelve tests and NO
#: `__subclasses__()` walk -- it enumerates. The docstring above claims the guards
#: "walk every transitive connector subclass", and the file that does that is
#: `test_every_discovered_connector_class_routes_through_the_chokepoint`, which was
#: absent. So the
#: strongest claim in the docstring was backed by the one file that does not
#: support it, while the file that does went unmentioned -- the coverage argument
#: pointing at the wrong evidence, which is the exact defect #16985 is about.
_AUTHORITATIVE_GUARDS = {
    "repo_tests/store_fact_chokepoint_guard_test.py": (
        "test_no_writer_reaches_the_store_around_the_chokepoint",
        "test_a_new_direct_writer_is_detected",
    ),
    "repo_tests/kb_content_redaction_chokepoint_guard_test.py": (
        "test_every_content_sink_call_site_is_redacted_or_explicitly_exempt",
        "test_negative_control_an_unredacted_write_path_is_caught",
    ),
    # The discovery guard: it walks `base.__subclasses__()`, so a connector added
    # tomorrow is covered without anyone editing a list. This is what makes the
    # docstring's "every transitive connector subclass" true.
    "repo_tests/connector_redaction_guard_test.py": (
        "test_every_discovered_connector_class_routes_through_the_chokepoint",
        "test_negative_control_an_overriding_connector_is_caught",
    ),
    # Retained as the behavioural layer under the discovery guard -- it exercises
    # real connectors rather than proving the set is complete. Listed with its own
    # test so a reader is not left inferring which role it plays.
    "autobot-backend/knowledge/connectors/connector_redaction_functional_test.py": (),
}

#: The chokepoint those guards protect.
_CHOKEPOINT = "autobot-backend/knowledge/ingest_sanitize.py"
#: The function inside it that must do the redacting. Named, not inferred, so the
#: check below cannot be satisfied by a redact_content call elsewhere in the file.
_CHOKEPOINT_FUNCTION = "sanitize_fact_content"


def _collectible_test_names(module: ast.Module) -> set[str]:
    """Test names pytest can actually collect: module-level functions, plus the
    methods of a module-level class.

    Deliberately NOT ``ast.walk`` (review, #17732). A ``def`` nested inside
    another function is unreachable to collection, so a required test could be
    deleted, its name survive inside some closure, and this guard stay green
    while pytest ran nothing -- the failure this test exists to prevent, in the
    test itself.

    Class methods are included rather than excluded: pytest collects
    ``TestX::test_y``, so restricting to the module body alone would reject a
    legitimately class-based guard later. All six names required today are
    module-level functions, so this is about the next one, not the current set.
    """
    names: set[str] = set()
    for node in module.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.ClassDef):
            names.update(
                child.name for child in node.body if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            )
    return names


def _calls_redact_content(source: str, *, function_name: str | None = None) -> bool:
    """True if *source* contains an actual call to redact_content(...).

    Checked against the function's own source, not the module's imports, so an
    entry point that imports the redactor but never calls it still fails.
    Parsed with ast rather than a substring search (review): a comment or a
    docstring mentioning "redact_content(" in passing must not satisfy this.

    ``function_name`` narrows the search to that module-level function (review,
    #17732). Without it, *source* being a whole module means any
    ``redact_content`` call anywhere in the file satisfies the check -- so
    moving the call out of the chokepoint into an unrelated helper would leave
    this guard green. The docstring above already claimed function scoping; the
    whole-module call site is where that claim was not in effect. A named
    function that is absent returns False rather than falling back to the
    module, so a rename fails loudly instead of widening the scope.
    """
    tree = ast.parse(textwrap.dedent(source))
    scope: ast.AST = tree
    if function_name is not None:
        named = next(
            (
                node
                for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name
            ),
            None,
        )
        if named is None:
            return False
        scope = named
    return any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "redact_content"
        for node in ast.walk(scope)
    )


def _resolve(module_path: str, qualname: str):
    obj = importlib.import_module(module_path)
    for part in qualname.split("."):
        obj = getattr(obj, part)
    return obj


@pytest.mark.parametrize(
    "module_path,qualname",
    _HISTORICAL_ENTRY_POINTS,
    ids=[f"{m}.{q}" for m, q in _HISTORICAL_ENTRY_POINTS],
)
def test_historical_entry_point_still_redacts_credentials(module_path: str, qualname: str) -> None:
    func = _resolve(module_path, qualname)
    source = inspect.getsource(func)
    assert _calls_redact_content(source), (
        f"{module_path}.{qualname} extracts external content but its source has no "
        "redact_content(...) call -- a credential in this content would reach the "
        "indexer/embedder unmasked (#13708)."
    )


def test_negative_control_a_function_that_skips_redaction_is_caught() -> None:
    """Proves the assertion above can fail, not just always pass.

    Without this, a guard whose detection helper is broken (e.g. checking the
    wrong string, or matching the import instead of a call) would report green
    against every real entry point without ever having demonstrated it can see
    a violation -- the exact "did not look" failure MEASUREMENT_DISCIPLINE.md
    warns about.
    """

    def _fake_entry_point_that_forgets_to_redact(content_bytes: bytes) -> str:
        text = content_bytes.decode("utf-8")
        return text

    source = inspect.getsource(_fake_entry_point_that_forgets_to_redact)
    assert not _calls_redact_content(source), "negative control itself contains a redact_content(...) call"


def test_negative_control_a_mention_in_a_comment_or_string_is_not_a_call() -> None:
    """A substring search would pass this; an ast.Call check must not (review).

    ``# TODO: call redact_content(text) here`` and a docstring naming the
    function are exactly the false-positive shape a plain ``"redact_content(" in
    source`` check cannot tell apart from a real call.
    """

    def _fake_entry_point_that_only_mentions_it(content_bytes: bytes) -> str:
        """Caller must invoke redact_content(text) before returning."""
        # TODO: call redact_content(text) here
        text = content_bytes.decode("utf-8")
        return text

    source = inspect.getsource(_fake_entry_point_that_only_mentions_it)
    assert not _calls_redact_content(source), "a comment/docstring mention of redact_content( must not count as a call"


def test_the_authoritative_guards_still_exist() -> None:
    """The docstring's cross-reference is asserted, not merely written.

    If a guard named in `_AUTHORITATIVE_GUARDS` is renamed or removed, this file's
    claim that coverage lives elsewhere becomes false and a reader is sent to nothing.
    A pointer nobody checks is how a comment outlives the mechanism it describes.
    """
    root = Path(__file__).resolve().parents[1]
    missing = [rel for rel in [*_AUTHORITATIVE_GUARDS, _CHOKEPOINT] if not (root / rel).is_file()]
    assert not missing, (
        f"this guard's docstring points at {missing}, which do not exist. Either the "
        "coverage argument moved and the docstring needs re-pointing, or the guards that "
        "establish it were removed -- in which case the three paths verified here are the "
        "only redaction coverage left, and that is a security regression, not a doc defect."
    )

    # The file existing is not the claim. `is_file()` passes on an empty file, and a
    # guard whose discovery test was deleted still satisfies it -- so the named test
    # has to be there too.
    gutted = []
    for rel, required in _AUTHORITATIVE_GUARDS.items():
        if not required:
            continue
        defined = _collectible_test_names(ast.parse((root / rel).read_text(encoding="utf-8")))
        gutted.extend(f"{rel}::{name}" for name in required if name not in defined)
    assert not gutted, (
        f"the tests that make these guards authoritative are gone: {gutted}. The files are "
        "still present, so a file-existence check would pass while the coverage argument "
        "this docstring makes had quietly stopped being true."
    )


def test_the_chokepoint_calls_the_redactor() -> None:
    """The three paths here are a second layer; this asserts the first one is real.

    Without it, every test in this file could pass while the chokepoint the docstring
    defers to had stopped redacting -- the guard would be measuring its own narrow
    layer and reporting the system as covered.
    """
    root = Path(__file__).resolve().parents[1]
    source = (root / _CHOKEPOINT).read_text(encoding="utf-8")
    assert _calls_redact_content(source, function_name=_CHOKEPOINT_FUNCTION), (
        f"{_CHOKEPOINT}::{_CHOKEPOINT_FUNCTION} is named here as the chokepoint that redacts "
        "every knowledge write, and it contains no redact_content(...) call. A call elsewhere "
        "in that module does not satisfy this: the chokepoint argument is about this function."
    )
