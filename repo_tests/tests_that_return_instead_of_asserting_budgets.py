# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Budget ledger for ``tests_that_return_instead_of_asserting_test.py`` (#15590).

Split out of the guard itself, mirroring ``python_file_size_known_large.py``
(#14547): that file exists because the size hook's own logic had to stay
under the cap it enforces, and this one exists for the same reason applied to
a different guard.

The guard's convention is a paragraph per budget change explaining why the
delta is a legitimate shrink rather than a re-measurement. Those paragraphs
are load-bearing, not decoration to trim — #15195's entry warns that a
re-baseline without an enumerated delta is exactly the loophole the
convention exists to close. Left inline, the convention eventually consumes
the guard's own MAX_LINES: a five-line rationale for #15255 took the file
from 600 to 605 and failed ``python_file_size_ratchet_test``, and had to be
compressed onto the value line to land. That inline compression was the
workaround; this split, and writing the next rationale as the paragraph it
deserves, is the fix.

``_KNOWN_OFFENDERS`` and ``_SWALLOWED_ASSERTIONS`` below are the two ceilings
the guard enforces, each keyed by top-level tree and paired with the
population floor that proves the sweep is still reaching the tree it claims —
a walk that has silently stopped matching would otherwise report its own
collapse to zero as progress. Both are down-only, with no sanctioned route to
raise either: see ``test_the_known_offender_budgets_only_ever_shrink`` and
``test_no_test_smothers_its_own_assertions_under_a_swallowing_handler`` in the
guard itself for the ratchet mechanics, the exact failure conditions and the
messages. Nothing in this module decides pass or fail on its own.
"""

from __future__ import annotations

# Measured on this branch, per top-level tree:
#   tree: (return statements that must not be exceeded,
#          test functions that must STILL be found in that tree)
#
# The second number is not decoration. Without it, a walk that breaks and
# returns nothing looks identical to a tree somebody finished draining, and the
# ratchet would record the collapse as a triumph and lock it in. A tree may
# only be declared drained while its own population is still demonstrably
# there. Delete an entry once its budget genuinely reaches zero.
_KNOWN_OFFENDERS = {
    # Lowered in the same commit that changed the definition, as the guard's own
    # ratchet requires: 136 -> 78 and 134 -> 126.
    #
    # Be precise about WHY these moved, because the obvious reading is wrong.
    # The drop is NOT the nine driver-consumed functions that commit fixed —
    # none of those are in `autobot-backend`, yet that tree fell 58. The whole
    # movement is a side effect of the exemption in `offending_returns`: a test
    # that asserts AND returns is no longer counted, because it can fail and its
    # return value is a separate driver contract (#14920). That tree-wide change
    # un-flags 39 pre-existing functions in `autobot-backend` and 4 in
    # `autobot-infrastructure` that neither commit touched.
    #
    # Those 43 were checked rather than assumed: every one carries real
    # assertions (1-24 apiece) alongside its return, so none is a vacuous assert
    # masking a test that cannot fail.
    #
    # The drop is not a sweep collapse — the population floors below are
    # untouched and still pass, which is what tells the two apart.
    # 78 -> 75 with #14941 (test_celery_worker_status stopped returning a verdict
    # pytest discards) and #14927 (three classes converted to collect, which moves
    # their methods into this file's population as well).
    #
    # 126 -> 121 with #14518: the inline-python and driver scripts under
    # `shared/scripts` (test_phase5_cleanup, verify_backend_config,
    # verify_ssh_manager, test_redis_comparison) now assert instead of handing a
    # verdict back to a caller that discards it. Measured, not estimated — the
    # sweep reports 121 and the population floor below is unmoved, which is what
    # separates a real drain from a sweep that stopped matching.
    #
    # 75 -> 73 with #14989: api/simple_terminal_e2e_test.py's own new
    # early-return offender was converted to an assert in the same commit that
    # added it, and merging Dev_new_gui landed one further pre-existing fix
    # elsewhere in the tree.
    #
    # Both reductions survive together: the ratchet only turns down, so where
    # two branches each lowered a budget the merge keeps the lower of the two,
    # never the more permissive one.
    #
    # 73 -> 71 with #14979: cache/cache_consolidation_p4_test.py's ten functions
    # each wrapped their asserts in `except Exception: return False`, so the bare
    # except swallowed AssertionError and not one of the ten could fail. All ten
    # returns are gone and the assertions now propagate.
    #
    # Only 2 of the 10 move this number, and the reason is worth recording:
    # `_offending_returns` skips any test containing an `assert` or `raise`,
    # because "returning instead of asserting" is the defect and a test that does
    # both can still fail. Nine of the ten HAD asserts -- inert ones, neutralised
    # by the bare except, but present -- so this sweep passed over them. Only
    # `test_migrated_files_import`, whose body was `pass` plus prints with no
    # assert at all, was ever counted (2 returns, lines 281 and 288).
    #
    # So this guard is blind to an assert that cannot fire. That gap is #15195.
    #
    # 71 -> 86 and 121 -> 127 with #15195: A DELIBERATE RE-MEASUREMENT, NOT A
    # RATCHET VIOLATION, AND THE ONLY ONE THIS FILE SANCTIONS.
    #
    # The ceilings above are down-only against a FIXED definition of the defect.
    # #15195 changed the definition: an assertion neutralised by a handler that
    # catches AssertionError no longer buys the assert/raise exemption, because
    # such a test cannot fail — which is the whole subject of this sweep. The
    # population did not grow; the detector stopped missing part of it. Nothing
    # was written, nothing regressed, and no offending line is new.
    #
    # The distinction that keeps this from being a loophole: a re-baseline is
    # legitimate only when the sweep is made STRICTER and the delta is
    # enumerated. Both hold here. The 21 newly-counted returns are 8 functions
    # in 3 files, every one of them pre-existing:
    #
    #   autobot-backend/config/config_consolidation_p2_test.py        11 returns
    #     (test_config_consolidation — ten `try: assert…/except Exception:
    #      return False` sections in one function)
    #   autobot-backend/tests/integration/
    #     test_causal_framework_integration.py                         4 returns
    #     (four *_full_pipeline methods that catch AssertionError into a
    #      scenario report and return it)
    #   autobot-infrastructure/shared/scripts/test_configuration.py    6 returns
    #     (three driver functions consumed by the module's own main())
    #
    # No previously-counted site stopped being counted (the base set is a strict
    # subset of the new one, verified site-by-site), and no tree outside this
    # dict gained an offender — the hard zero below is unmoved. Those 8 are
    # reported, not converted, under #15189: two of the three files are large
    # live-service drivers where unwrapping the swallow is its own piece of
    # work, and half-converting a population is how a ratchet gets stuck.
    #
    # A number here may be raised again ONLY on the same terms: the detector got
    # stricter, and the delta is enumerated in this comment. Fixing tests still
    # requires no permission at all.
    # 127 -> 121 with #15189: the three swallowing driver functions in
    # shared/scripts/test_configuration.py lost their `except Exception:
    # return False` wrappers, so their assertions propagate — exempt by the
    # rule above, since a test with a LIVE assertion is no longer counted.
    # 86 -> 75 with #15189 (continued): config_consolidation_p2_test.py's ten
    # swallowing sections are now ten real tests; all 11 counted returns gone.
    "autobot-backend": (75, 18000),
    # 121 -> 118 with #15255: three more swallowing drivers in
    # shared/scripts/test_configuration.py lost their `except Exception:
    # return False` wrappers, so their assertions propagate and stop being
    # counted -- the same exemption the #15189 entry above describes. A shrink,
    # not a re-measurement: the definition of the defect did not move, the
    # population did. It landed as a one-line note because the detector file was
    # sitting exactly on the 600-line cap and the paragraph would not fit; that
    # is the defect #15590 splits this module out to fix, so the note is restored
    # to its proper form here.
    "autobot-infrastructure": (118, 250),
    "autobot-npu-worker": (7, 150),
}

# Test functions holding at least one assertion that cannot fire, per top-level
# tree, paired with the same population floor as above (#15195).
#
# The sibling defect, and the one that made the detector blind: an `assert` under a
# handler catching Exception/BaseException/AssertionError. The ceiling above
# only sees it when the function ALSO returns a value; this one sees it whether
# or not it returns, which is what closes the general case. Nine functions
# today, and every tree not named here is pinned at zero by derivation.
#
# Down-only, on the same terms as every other ceiling in this file: there is no
# sanctioned route to raise one. Wrapping a test's own assertions in
# `except Exception` is never the right thing to write — if the test is meant to
# tolerate an error, catch the specific exception it tolerates; if it is meant
# to report one, `pytest.fail(...)` or `raise` in the handler, both of which
# this guard already recognises as reporting rather than swallowing.
#
# 9 -> 5 with #15189 (`autobot-infrastructure` deleted rather than left at zero): three
# driver functions in shared/scripts/test_configuration.py and
# `test_secrets_service_config_migration` in config_migration_integration_test.py were
# unwrapped. The five remaining, named in #15189, needed #15166-style restructuring: one
# in config_consolidation_p2_test.py, four aggregator methods in
# test_causal_framework_integration.py.
# 5 -> 4 (continued): config_consolidation_p2_test.py is now ten real tests, zero inert
# asserts, surfacing two drifts fixed in the same change: `_get_default_config()` never
# existed on `ConfigManager` (real fn: `config.defaults.get_default_config()`), and
# multimodal asserted the pre-#13207 `voice.confidence_threshold` of 0.8, not current
# 0.7 — the remaining four are the unchanged aggregator methods.
_SWALLOWED_ASSERTIONS = {
    "autobot-backend": (4, 18000),
}
