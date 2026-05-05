# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for autobot_shared.missing_dep.MissingDep (#6807).

Closes the test gap from #6794: the dunder short-circuit and
__getitem__ pass-through were added to support Optional[stub] /
List[stub] at module-load time, but PR #6800 verified the behavior
only with a one-shot script. These tests pin the contract so a future
refactor that breaks any of the three paths (subscript / call /
attribute) fails CI loudly.
"""

from typing import List, Optional

import pytest

from autobot_shared.missing_dep import MissingDep


def _stub() -> MissingDep:
    return MissingDep("Foo", ImportError("original cause"))


def test_subscript_does_not_raise() -> None:
    """Optional[stub] / List[stub] must evaluate at module load (#6794)."""
    stub = _stub()
    # Both must succeed without raising — that's the entire point of
    # the __getitem__ override.
    assert Optional[stub] is not None
    assert List[stub] is not None


def test_subscript_returns_self() -> None:
    """Subscript yields a MissingDep again so chained subscripts compose."""
    stub = _stub()
    assert stub[int] is stub
    assert stub[str, bytes] is stub


def test_call_raises_importerror() -> None:
    """Calling a missing dep must raise ImportError (not TypeError)."""
    stub = _stub()
    with pytest.raises(ImportError, match="Foo is not available"):
        stub()


def test_call_with_args_raises_importerror() -> None:
    """Args/kwargs do not change the failure mode."""
    stub = _stub()
    with pytest.raises(ImportError, match="Foo is not available"):
        stub(1, 2, key="value")


def test_non_dunder_attr_raises_importerror() -> None:
    """Real attribute access must raise ImportError."""
    stub = _stub()
    with pytest.raises(ImportError, match="Foo is not available"):
        stub.some_method  # noqa: B018  # intentional attribute access


def test_dunder_attr_raises_attributeerror_not_importerror() -> None:
    """typing.* probes dunders via hasattr — they must signal absence
    via AttributeError, not crash with ImportError.

    This is what the dunder short-circuit in __getattr__ exists for.
    """
    stub = _stub()
    # hasattr swallows AttributeError → False; if __getattr__ raised
    # ImportError it would propagate and crash module load.
    assert hasattr(stub, "__typing_subst__") is False
    assert hasattr(stub, "__mro_entries__") is False


def test_falsy() -> None:
    """`if not stub` must be True so optional-dep guards work (#6297)."""
    stub = _stub()
    assert not stub
    assert bool(stub) is False


def test_eq_none() -> None:
    """`stub == None` must be True so `is None` style guards transition
    cleanly (#6297). Note: `stub is None` is intentionally still False —
    only equality is overridden, identity is not.
    """
    stub = _stub()
    assert stub == None  # noqa: E711  # intentional comparison
    assert stub is not None


def test_eq_other_missingdep_instance() -> None:
    """Two MissingDep instances compare equal regardless of name —
    callers treat them as a single sentinel value.
    """
    a = MissingDep("A", ImportError("a"))
    b = MissingDep("B", ImportError("b"))
    assert a == b


def test_repr_contains_name() -> None:
    """repr() exposes the original module name so test failures are
    debuggable.
    """
    assert repr(_stub()) == "MissingDep('Foo')"


def test_hashable() -> None:
    """MissingDep must remain hashable (used as dict keys / in sets in
    some optional-import sites).
    """
    s = {_stub(), _stub()}
    assert len(s) == 2  # identity-based hashing is preserved
