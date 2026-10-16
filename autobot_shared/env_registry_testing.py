# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Testing-only AUTOBOT_* environment variable registrations.

Split out of ``env_registry.py`` to keep that file under its grandfathered
file-size ceiling (#14236) while making room to register a new "terminal"
component variable there (#14961) — ``env_registry.py`` was already at its
ceiling with no slack for either addition. This is the one "testing"-component
entry that lived at the tail of that file; relocated verbatim rather than
merged into ``env_registry_terminal.py`` so neither sibling file mixes
unrelated components (see ``env_registry_ai.py``'s docstring for the same
reasoning).

Registration contract (import side effect, ordering): see ``env_registry`` (#16415).

Closes GH#7081.
"""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_LIVE_PROBE_TIMEOUT_SECONDS",
        type=float,
        default=1.0,
        description=(
            "Seconds a test's live-service precondition probe waits for a TCP connect "
            "before reporting the service as absent and skipping "
            "(autobot_shared/live_service_probe.py, #14930). Short by default: a "
            "refused loopback connect returns immediately, and this runs once per "
            "endpoint per process. Raise it when probing a fleet host across a link "
            "slow enough that a live service could be mistaken for a missing one."
        ),
        component="testing",
        range=(0.1, 60.0),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_PREPUSH_ALLOW_UNRUNNABLE",
        type=bool,
        default=False,
        description=(
            "Set to 1 to let `git push` proceed when the pre-push pytest gate COULD NOT RUN on the "
            "local interpreter -- llc/scheduler/base.py refuses to import below Python 3.11, which "
            "takes whole pytest groups down at collect time on a sub-floor machine (the platform "
            "floor and CI are 3.14). Distinct from AUTOBOT_PREPUSH_ALLOW_TIMEOUT, which covers a "
            "check that started and ran out of time. Neither is a substitute for --no-verify: both "
            "switch off exactly the one check that could not produce a verdict and leave every "
            "other hook blocking (#16230)."
        ),
        component="tooling",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_PREPUSH_ALLOW_TIMEOUT",
        type=bool,
        default=False,
        description=(
            "Set to 1 to let `git push` proceed when a pre-push check DID NOT RUN because it timed "
            "out. Predates the registry requirement and was never registered, which is how the "
            "same omission reached AUTOBOT_PREPUSH_ALLOW_UNRUNNABLE above -- registered here "
            "alongside it rather than left as the next reviewer's finding (#7081, #16230)."
        ),
        component="testing",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_PREPUSH_TYPE_CHECK_TIMEOUT",
        type=int,
        default=450,
        description=(
            "Seconds the pre-push gate allows vue-tsc per frontend project. vue-tsc checks the "
            "whole project whatever the changeset (111 s idle, ~294 s under load measured), so "
            "the budget is project-sized, not changeset-scaled. A non-integer or zero value falls "
            "back to 450 with a warning; capped at the hook's MAX_BUDGET (#18578)."
        ),
        component="testing",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_PREPUSH_PYTEST_WORKERS",
        type=int,
        default=4,
        description=(
            "Number of pytest-xdist workers the pre-push gate runs the selected tests with "
            "(`-n N --dist loadscope`). 0 runs serially. A non-integer or negative value falls "
            "back to 4 with a warning. Capped (never `-n auto`) because the dev box runs many "
            "parallel sessions at load 20-30; the budget uses the per-file cost of the mode "
            "actually chosen (#17451)."
        ),
        component="testing",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_UPSERT_COMMENT_TIMEOUT",
        type=float,
        default=30.0,
        description=(
            "Seconds each GitHub API call made by the shared sticky-PR-comment action waits before "
            "giving up (.github/actions/upsert-pr-comment/upsert_pr_comment.py, #12984). A value "
            "that is not a finite number above zero is rejected with a warning and the default is "
            "used, since 0, NaN and a negative would mean no timer or an expired one."
        ),
        component="tooling",
    )
)
