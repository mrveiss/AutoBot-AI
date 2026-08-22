# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``eslint-plugin-oxlint`` must never drift off its matching ``oxlint`` minor.

``eslint-plugin-oxlint`` declares a peer dependency on its *own* minor of
``oxlint`` — plugin ``1.79.0`` requires ``oxlint: ~1.79.0``. If the two pins in
``autobot-frontend/package.json`` fall on different minors, the peer is
unsatisfiable and ``npm ci`` dies with ``ERESOLVE`` inside the frontend image
build, taking the required ``smoke-test`` check down with it.

This has happened twice:

* #12792 — a grouped bump advanced the plugin while leaving ``oxlint`` behind.
* #12798 — remedied it by giving the pair their own dependabot group, so the
  two would always move together.
* #14705 — the group emitted a **single-member** PR ("Bumps the oxlint group in
  /autobot-frontend with 1 update"), advancing ``oxlint`` to ``1.79.0`` and
  leaving the plugin at ``~1.78.0``. A matching plugin release had been on the
  registry for three days. #14715 is this guard.

A dependabot group says "if these move, move them together". It does not say
"never move one without the other" — when only one member is judged to have an
actionable update, a one-member group PR is emitted and the lockstep silently
evaporates. The group name on the branch and in the PR body still says
``oxlint``, so it reads as though lockstep held.

A version cap is the wrong remedy here, for the reason ``dependabot.yml``
already gives on the group: both *should* keep advancing, just never apart.
So the invariant is checked directly instead.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

# The two packages whose minors must agree, and the manifest that pins them.
_OXLINT = "oxlint"
_PLUGIN = "eslint-plugin-oxlint"
_MANIFEST = Path(__file__).resolve().parents[1] / "autobot-frontend" / "package.json"

# `~1.79.0`, `^1.79.0`, `1.79.0`, `>=1.79.0` — capture major and minor only.
_SPEC = re.compile(r"^\D*(\d+)\.(\d+)\.")


def _minor(spec: str) -> tuple[int, int]:
    """Return ``(major, minor)`` for a pin, or fail loudly on an unparsed one.

    An unparseable spec is a failure, never a skip: a guard that quietly opts
    out of the case it cannot read is a guard that fails open.
    """
    match = _SPEC.match(spec)
    if match is None:
        pytest.fail(
            f"could not parse the version out of {spec!r}. Extend this guard "
            f"rather than letting an unreadable pin pass unchecked."
        )
    return int(match.group(1)), int(match.group(2))


def _pins() -> dict[str, str]:
    """Both pins as declared in the frontend manifest."""
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    declared: dict[str, str] = {}
    for section in ("dependencies", "devDependencies"):
        declared.update(manifest.get(section, {}))
    return declared


def test_manifest_is_where_this_guard_expects() -> None:
    """The guard is worthless if it reads nothing — assert the target exists."""
    assert _MANIFEST.is_file(), (
        f"{_MANIFEST} is missing. This guard silently covers nothing if the "
        f"frontend manifest moves; repoint it at the new location."
    )


@pytest.mark.parametrize("package", [_OXLINT, _PLUGIN])
def test_both_packages_are_pinned(package: str) -> None:
    """Neither half may vanish — an absent pin would read as agreement."""
    assert package in _pins(), (
        f"{package} is no longer pinned in {_MANIFEST.name}. If the pair was "
        f"deliberately dropped, delete this guard in the same change; leaving "
        f"it in place would report a lockstep that nothing enforces."
    )


def test_oxlint_and_its_plugin_share_a_minor() -> None:
    """The invariant: the two pins sit on the same major.minor.

    ``eslint-plugin-oxlint@X.Y.Z`` peers on ``oxlint: ~X.Y.Z``, so a mismatch
    here is an unresolvable install, not a style preference.
    """
    pins = _pins()
    oxlint_spec, plugin_spec = pins[_OXLINT], pins[_PLUGIN]
    oxlint_minor, plugin_minor = _minor(oxlint_spec), _minor(plugin_spec)

    assert oxlint_minor == plugin_minor, (
        f"{_OXLINT} is pinned {oxlint_spec} and {_PLUGIN} is pinned "
        f"{plugin_spec}. {_PLUGIN} peers on its own matching {_OXLINT} minor, "
        f"so this combination cannot resolve and `npm ci` will fail with "
        f"ERESOLVE during the frontend image build (#12792, #14705). Move both "
        f"pins to the same minor."
    )


def test_guard_rejects_the_skew_that_broke_14705() -> None:
    """Mutation check: the real #14705 skew must actually trip ``_minor``.

    Without this, a guard that always returned equal minors would pass the
    assertion above and prove nothing.
    """
    assert _minor("~1.79.0") != _minor("~1.78.0"), (
        "the version parser cannot distinguish the two pins that broke "
        "#14705, so the lockstep assertion above cannot fail and is inert"
    )
    assert _minor("~1.79.0") == _minor("~1.79.0")
