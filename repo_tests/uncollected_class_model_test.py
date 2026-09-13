# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Self-tests for ``uncollected_class_model`` — the model, not the repository.

Every branch of the collection model is driven here on synthetic subjects, and
the whole model is compared against a real ``pytest --collect-only`` run. That
comparison is the load-bearing one: #14927 reported 120 uncollected methods from
an AST model of ``python_classes`` alone, and collecting the files put the real
figure at 90, with 30 false positives and 41 real offenders the model could not
see. An error of that shape is only catchable by asking pytest.

The cross-module cases are written as real files on disk because the resolution
under test is path-based. Driven through the source-string entry point alone
they would all answer "unknown", which is exactly what a resolver that had
stopped resolving would answer too.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from repo_tests.uncollected_class_model import (
    _parse_module,
    _parsed,
    _REPO_ROOT,
    _unresolvable_bases,
    uncollected_test_methods,
)

def _driver_package(tmp_path: Path) -> Path:
    """A real package holding one class with a constructor and one without.

    Real files, because the resolution these tests drive is path-based: the
    source-string entry point on its own cannot see another module and would
    fall back to "unknown" for every case below, which is the answer that makes
    a broken resolver look like a working one.
    """
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "driver.py").write_text(
        "class Driver:\n    def __init__(self):\n        self.session = 1\n", encoding="utf-8"
    )
    (package / "clean.py").write_text("class Clean:\n    pass\n", encoding="utf-8")
    return package


def _swept(package: Path, name: str, source: str) -> list[tuple[str, str, int]]:
    """Write ``source`` into ``package`` as a module and report its offenders."""
    module = package / name
    module.write_text(source, encoding="utf-8")
    return uncollected_test_methods(source, module)


def test_a_base_in_a_neighbouring_module_carries_its_init_across(tmp_path: Path) -> None:
    """A relative import is followed too, and an inherited __init__ still blocks."""
    package = _driver_package(tmp_path)
    assert _swept(
        package,
        "blocked_test.py",
        "from .driver import Driver\n\n\nclass TestThing(Driver):\n"
        "    def test_one(self):\n        assert True\n",
    ) == [("TestThing", "test_one", 5)], (
        "an __init__ imported from a neighbouring module still blocks collection"
    )
    assert not _swept(
        package,
        "fine_test.py",
        "from .clean import Clean\n\n\nclass TestThing(Clean):\n"
        "    def test_one(self):\n        assert True\n",
    ), (
        "a resolved base with no constructor must not be reported — over-reporting "
        "gets a guard switched off as surely as under-reporting hides work"
    )


def test_an_aliased_cross_module_base_resolves_to_its_real_definition(tmp_path: Path) -> None:
    """``from mod import Foo as Bar`` — the target module is keyed by Foo (#15007).

    Resolving a base by the name it is written with looked ``Bar`` up in a dict
    that only ever held ``Foo``, found nothing, and called the base unresolvable.
    Safe, because unresolvable is read as ``__init__``-present and the methods
    are reported rather than spared — but wrong, and the wrongness surfaces as a
    class with a perfectly readable base named in the "cannot resolve this"
    report. There were zero live instances when this was written, which is the
    whole reason it needs a fixture: nothing in the tree would notice it return.
    """
    package = _driver_package(tmp_path)
    assert _swept(
        package,
        "aliased_blocked_test.py",
        "from .driver import Driver as Engine\n\n\nclass TestThing(Engine):\n"
        "    def test_one(self):\n        assert True\n",
    ) == [("TestThing", "test_one", 5)], (
        "the alias hides Driver's constructor, it does not remove it"
    )
    assert not _swept(
        package,
        "aliased_fine_test.py",
        "from .clean import Clean as Fresh\n\n\nclass TestThing(Fresh):\n"
        "    def test_one(self):\n        assert True\n",
    ), "an aliased base with no constructor resolves, so nothing may be reported"

    fine = package / "aliased_fine_test.py"
    classes = {n.name: n for n in _parsed(fine).body if isinstance(n, ast.ClassDef)}
    assert not _unresolvable_bases(classes["TestThing"], classes, fine), (
        "Fresh resolves to Clean, so it must not be named as a base nothing can "
        "reach — the spurious report is the defect, not the count it feeds"
    )


def test_the_detector_follows_an_inherited_init_up_the_mro() -> None:
    """#14984, driven through the same entry point the rest of the model uses.

    pytest asks ``cls.__init__ is not object.__init__``, which walks the MRO, so
    an inherited constructor blocks collection exactly as an own one does. The
    failure direction the old own-body-only check had was under-reporting: a
    real uncollected test recorded as fine.
    """
    assert uncollected_test_methods(
        "class Driver:\n    def __init__(self):\n        self.session = 1\n\n\n"
        "class TestThing(Driver):\n    def test_one(self):\n        pass\n"
    ) == [("TestThing", "test_one", 7)], "an __init__ inherited from a plain base still blocks collection"

    assert uncollected_test_methods(
        "class Driver:\n    def __init__(self):\n        self.session = 1\n\n\n"
        "class Middle(Driver):\n    pass\n\n\n"
        "class TestThing(Middle):\n    def test_one(self):\n        pass\n"
    ) == [("TestThing", "test_one", 11)], "the walk must follow a chain of bases, not just the first link"

    assert not uncollected_test_methods(
        "class Driver:\n    pass\n\n\n"
        "class TestThing(Driver):\n    def test_one(self):\n        pass\n"
    ), "a plain base with no constructor blocks nothing"

    assert not uncollected_test_methods(
        "class TestThing(object):\n    def test_one(self):\n        pass\n"
    ), "object is what pytest compares against, so spelling it out blocks nothing"

    # An import this model cannot follow is never read as clean -- see _init_state.
    assert uncollected_test_methods(
        "class TestThing(SomethingImported):\n    def test_one(self):\n        pass\n"
    ) == [("TestThing", "test_one", 2)], "an unresolvable base must not be assumed __init__-free"


def test_the_detector_finds_a_planted_method_and_spares_the_legitimate_ones() -> None:
    """Self-test. Every branch is exercised, not merely written down."""
    assert uncollected_test_methods("class Helper:\n    def test_a(self):\n        pass\n") == [
        ("Helper", "test_a", 2)
    ]

    # Collected, each for a different reason.
    assert not uncollected_test_methods("class TestX:\n    def test_a(self):\n        pass\n")
    assert not uncollected_test_methods(
        "import unittest\n\n\nclass Anything(unittest.TestCase):\n"
        "    def test_a(self):\n        pass\n"
    ), "unittest.TestCase is collected whatever python_classes says"
    assert not uncollected_test_methods(
        "import unittest\n\n\nclass Base(unittest.TestCase):\n    pass\n\n\n"
        "class Deeper(Base):\n    def test_a(self):\n        pass\n"
    ), "a TestCase subclass reached through another class in the module"
    assert not uncollected_test_methods(
        "class Mixin:\n    def test_a(self):\n        pass\n\n\n"
        "class TestReal(Mixin):\n    pass\n"
    ), "a base contributes its methods through any collected subclass"
    assert not uncollected_test_methods(
        "class _Stub(AbstractConnector):\n    async def test_connection(self):\n        pass\n"
    ), "a private stand-in implementing an interface that dictates the name"

    # The direction #14927 missed entirely.
    assert uncollected_test_methods(
        "class TestX:\n    def __init__(self):\n        pass\n\n"
        "    def test_a(self):\n        pass\n"
    ) == [("TestX", "test_a", 5)], "a Test* class with __init__ is NOT collected by pytest"

    # A module-level function is pytest's business, not this guard's.
    assert not uncollected_test_methods("def test_a():\n    pass\n")
    # A private stand-in with no base class is just a class named with an underscore.
    assert uncollected_test_methods("class _Loose:\n    def test_a(self):\n        pass\n")


_EVERY_SHAPE = '''
import unittest


class TestPlain:
    def test_collected_plain(self):
        assert True


class TestWithInit:
    def __init__(self):
        self.x = 1

    def test_blocked_by_init(self):
        assert True


class NotNamedTest:
    def test_blocked_by_name(self):
        assert True


class LowerCaseCase(unittest.TestCase):
    def test_collected_unittest(self):
        assert True


class Mixin:
    def test_collected_through_subclass(self):
        assert True


class TestFromMixin(Mixin):
    pass


class PlainBaseWithInit:
    def __init__(self):
        self.x = 1


class TestInheritsInit(PlainBaseWithInit):
    def test_blocked_by_inherited_init(self):
        assert True


class MiddleLink(PlainBaseWithInit):
    pass


class TestInheritsInitTwoLinksUp(MiddleLink):
    def test_blocked_two_links_up(self):
        assert True
'''


def test_the_model_agrees_with_pytest_on_every_shape(tmp_path: Path) -> None:
    """Run the real collector and compare. A model nothing checks is a guess.

    #14927 reported 120 methods from an AST model of ``python_classes`` alone.
    Collecting the files put the real figure at 90, with 30 false positives and
    41 real offenders the model could not see. That error is only catchable by
    asking pytest, so this asks pytest — on a module carrying one of every shape,
    in its own directory with its own config, so neither the repo's conftest nor
    its testpaths can influence the answer.
    """
    module = tmp_path / "shapes_test.py"
    module.write_text(textwrap.dedent(_EVERY_SHAPE), encoding="utf-8")
    config = tmp_path / "pytest.ini"
    config.write_text(
        "[pytest]\npython_files = test_*.py *_test.py\n"
        "python_classes = Test*\npython_functions = test_*\n",
        encoding="utf-8",
    )

    result = subprocess.run(  # nosec B603
        [
            sys.executable, "-m", "pytest", str(module),
            "--collect-only", "-q", "--no-header",
            "-c", str(config), "-p", "no:cacheprovider",
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=False,
    )
    # Presence, not absence of failure: an empty stdout would otherwise agree
    # with a model that found nothing either.
    node_ids = {
        line.split("::")[-1].strip()
        for line in result.stdout.splitlines()
        if "::" in line and line.startswith("shapes_test.py")
    }
    assert node_ids, (
        "pytest collected nothing from the shape module, so this comparison proves "
        f"nothing.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

    source = module.read_text(encoding="utf-8")
    every_method = {
        child.name
        for node in _parse_module(module).body
        if isinstance(node, ast.ClassDef)
        for child in node.body
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
        and child.name.startswith("test_")
    }
    predicted_uncollected = {method for _, method, _ in uncollected_test_methods(source)}
    predicted_collected = every_method - predicted_uncollected

    assert predicted_collected == node_ids, (
        "this file's model of pytest's collection disagrees with pytest.\n"
        f"  pytest collected : {sorted(node_ids)}\n"
        f"  model predicted  : {sorted(predicted_collected)}\n"
        "The model is what every count in this file rests on — fix it here, do not "
        "adjust the budgets to match a wrong model (#14927)."
    )


def test_an_unparseable_swept_file_fails_loudly_instead_of_reading_as_clean() -> None:
    """The sweep is a denylist from the repo root, so it meets stray files.

    One must never be skipped: a file the walk could not read is not a file the
    walk cleared, and dropping it silently is the under-reporting this guard
    exists to catch. It has to fail, name the file and say what to do about it.

    The probe is written under a ``_SKIP``ped directory so no concurrently
    running sweep can pick it up while it exists.
    """
    scratch = _REPO_ROOT / "__pycache__"
    scratch.mkdir(exist_ok=True)
    stray = scratch / "unparseable_probe_test.py"
    stray.write_text("from a-b.c import (\n", encoding="utf-8")
    try:
        with pytest.raises(AssertionError) as raised:
            _parse_module(stray)
    finally:
        stray.unlink()

    message = str(raised.value)
    assert "unparseable_probe_test.py" in message, "the failure must name the file"
    assert "_SKIP" in message, "the failure must say how to exclude a file on purpose"
