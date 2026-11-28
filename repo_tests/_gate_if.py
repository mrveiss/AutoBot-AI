"""One reading of a ci.yml gate's `if:` (#20825).

A required-context gate is `always()` except on an unrelated-label event, where it is skipped so the earlier
verdict stands. Tests that only need "this gate always runs" share this predicate instead of each spelling it.
"""

from __future__ import annotations


def gate_always_runs(condition: object) -> bool:
    """True for `always()` and for `always() && !(<unrelated-label no-op event>)`, with or without `${{ }}`."""
    text = " ".join(str(condition or "").replace("${{", " ").replace("}}", " ").split())
    return text == "always()" or (text.startswith("always() && !(") and "label.name != 'land-next'" in text)
