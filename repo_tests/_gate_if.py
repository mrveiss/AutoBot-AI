"""One reading of a ci.yml gate's `if:` (#20825).

A required-context gate is exactly `always()`: ci.yml has no `pull_request` trigger any more, so no event
exists on which a gate would be skipped. Tests that only need "this gate always runs" share this predicate
instead of each spelling it.
"""

from __future__ import annotations


def gate_always_runs(condition: object) -> bool:
    """True for `always()`, with or without the `${{ }}` wrapper."""
    return " ".join(str(condition or "").replace("${{", " ").replace("}}", " ").split()) == "always()"
