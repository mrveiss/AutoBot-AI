# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for the shared collected-test model (#15195).

The guards that use this model are repo-wide sweeps: they can only tell you
that today's tree happens to be clean, never that a branch of the model is
right. So every branch gets a synthetic case here — especially the ones that
must NOT fire. A guard that over-flags a legitimate ``try``/``except`` is a
guard somebody switches off, and a switched-off guard is worse than the blind
spot #15195 removed.
"""

from __future__ import annotations

import ast
import os

from repo_tests import collected_test_model
from repo_tests.collected_test_model import (
    collectable_tests,
    own_nodes,
    propagating_guards,
    swallowed_assertions,
)


def _function(source: str) -> ast.AST:
    """The single collected test in ``source``."""
    found = collectable_tests(ast.parse(source))
    assert len(found) == 1, f"expected one collected test, found {len(found)}"
    return found[0]


def _live(source: str) -> int:
    return len(propagating_guards(_function(source)))


def _written(source: str) -> int:
    return len(own_nodes(_function(source), (ast.Assert, ast.Raise)))


SWALLOWED = (
    "def test_a():\n"
    "    try:\n"
    "        assert False\n"
    "    except Exception:\n"
    "        pass\n"
)


def test_a_handler_catching_assertions_makes_the_assert_in_its_body_inert() -> None:
    assert _written(SWALLOWED) == 1, "the assertion is written down"
    assert _live(SWALLOWED) == 0, "and it cannot reach pytest"
    assert swallowed_assertions(SWALLOWED) == [("test_a", 3)]


def test_every_spelling_that_catches_an_assertion_error_is_recognised() -> None:
    for catcher in (
        "except Exception:",
        "except BaseException:",
        "except AssertionError:",
        "except:",
        "except (ValueError, Exception):",
        "except Exception as exc:",
        "except (KeyError, AssertionError, OSError):",
    ):
        source = SWALLOWED.replace("except Exception:", catcher)
        assert _live(source) == 0, f"`{catcher}` catches AssertionError"


def test_a_handler_that_hands_the_failure_back_on_is_not_a_swallow() -> None:
    """The counter-cases. Over-flagging here is the expensive failure."""
    for handler, why in (
        ("        raise\n", "a bare re-raise"),
        ("        raise RuntimeError('x')\n", "raising something else still ends the test"),
        ("        assert False\n", "the handler re-checks"),
        ("        pytest.fail('x')\n", "pytest.fail ends the test"),
        ("        pytest.skip('x')\n", "a skipped test is not a passing test"),
        ("        self.fail('x')\n", "unittest's own outcome call"),
    ):
        source = SWALLOWED.replace("        pass\n", handler)
        # >= 1 rather than == 1: a `raise` in the handler is itself a live
        # guard node, so the re-raise cases legitimately report two.
        assert _live(source) >= 1, f"{why} — the assertion still counts"
        assert not swallowed_assertions(source), why


def test_a_handler_naming_a_non_assertion_exception_protects_nothing_away() -> None:
    for catcher in ("except ValueError:", "except (KeyError, TypeError):", "except OSError:"):
        source = SWALLOWED.replace("except Exception:", catcher)
        assert _live(source) == 1, f"`{catcher}` does not catch AssertionError"
        assert not swallowed_assertions(source)


def test_only_the_try_body_is_covered_by_that_trys_own_handlers() -> None:
    """``else``, ``finally`` and the handler bodies all propagate."""
    for clause in ("else", "finally"):
        source = (
            "def test_a():\n"
            "    try:\n"
            "        pass\n"
            "    except Exception:\n"
            "        pass\n"
            f"    {clause}:\n"
            "        assert False\n"
        )
        assert _live(source) == 1, f"an assert in `{clause}` is not caught by that try"
    handler_body = (
        "def test_a():\n"
        "    try:\n"
        "        pass\n"
        "    except Exception:\n"
        "        assert False\n"
    )
    assert _live(handler_body) == 1, "a handler does not catch what it raises itself"


def test_an_outer_swallow_survives_an_inner_handler_that_re_raises() -> None:
    nested = (
        "def test_a():\n"
        "    try:\n"
        "        try:\n"
        "            assert False\n"
        "        except ValueError:\n"
        "            raise\n"
        "    except Exception:\n"
        "        pass\n"
    )
    assert _live(nested) == 0, (
        "nothing here reaches pytest: the inner handler's `raise` is itself "
        "inside the OUTER try body, so the outer bare except eats that too"
    )
    assert swallowed_assertions(nested) == [("test_a", 4)], (
        "and the inner assert is eaten by the outer bare except, not saved by "
        "the inner handler that re-raises"
    )


def test_a_nested_definitions_swallow_belongs_to_the_nested_definition() -> None:
    helper = (
        "def test_a():\n"
        "    def helper():\n"
        "        try:\n"
        "            assert False\n"
        "        except Exception:\n"
        "            pass\n"
        "\n"
        "    assert helper() is None\n"
    )
    assert _live(helper) == 1, "the test's own assert is live"
    assert not swallowed_assertions(helper), (
        "the helper's swallow is the helper's — attributing it to the enclosing "
        "test is the naive walk this model exists to avoid"
    )


def test_a_test_with_no_try_at_all_is_untouched_by_the_rule() -> None:
    plain = "def test_a():\n    assert True\n    raise SystemExit(0)\n"
    assert _live(plain) == 2
    assert not swallowed_assertions(plain)


# ---------------------------------------------------------------------------
# Does the walk actually PRUNE a SKIP directory, or merely filter it out of
# the result afterward? (#16601)
#
# `rglob()` filtered post-hoc and `os.walk()` with `dirnames[:] = [...]`
# pruning produce the identical final file list -- that identity is exactly
# why no assertion on `test_modules()`'s RETURN VALUE can tell them apart,
# and why the shard-10 hang (rglob descending into a huge excluded directory
# regardless) shipped without any test noticing. This test instead watches
# which directories `os.walk` is fed to next: a SKIP directory holding a
# sentinel file must never be YIELDED by the walk at all, which is true only
# when `dirnames` is mutated in place before the walk continues past it.
# ---------------------------------------------------------------------------


def test_modules_prunes_skip_directories_during_the_walk_not_after(tmp_path, monkeypatch) -> None:
    skip_name = next(iter(collected_test_model.SKIP))
    skip_dir = tmp_path / skip_name
    skip_dir.mkdir()
    # A file that would be collected if this directory were ever descended
    # into -- its mere presence in the returned list, or its directory being
    # visited at all, is the tell.
    (skip_dir / "sentinel_test.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    kept_dir = tmp_path / "kept"
    kept_dir.mkdir()
    (kept_dir / "test_kept.py").write_text("def test_x():\n    pass\n", encoding="utf-8")

    visited_dirpaths: list[str] = []
    real_walk = os.walk

    def spying_walk(root, *args, **kwargs):
        for dirpath, dirnames, filenames in real_walk(root, *args, **kwargs):
            visited_dirpaths.append(dirpath)
            yield dirpath, dirnames, filenames

    monkeypatch.setattr(collected_test_model, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(collected_test_model.os, "walk", spying_walk)

    modules = collected_test_model.test_modules()

    assert str(skip_dir) not in visited_dirpaths, (
        f"os.walk descended into {skip_dir}, a directory in SKIP -- pruning "
        "must mutate `dirnames` in place BEFORE the walk continues past it, "
        "not filter the results afterward (#16601). A post-hoc filter would "
        "leave this directory out of `modules` below just the same, which is "
        "exactly the negative-control gap this test closes."
    )
    assert modules == [kept_dir / "test_kept.py"], (
        "the sentinel file under the SKIP directory must never reach the "
        "returned list either"
    )
