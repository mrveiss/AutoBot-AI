"""One reading of a ci.yml gate's `if:` (#20825).

A required-context gate is `always()` except on an unrelated-label event, where it is skipped so the earlier
verdict stands. Tests that only need "this gate always runs" share this predicate instead of each spelling it.
"""

from __future__ import annotations

import re

_STATUS_FUNCTION = re.compile(r"\b(?:always|failure|cancelled)\(\)")
_READS_NEEDS_RESULT = re.compile(r"needs(?:\.[\w-]+|\[[^\]]+\])\.result\s*==")


def gate_always_runs(condition: object) -> bool:
    """True for `always()` and for `always() && !(<unrelated-label no-op event>)`, with or without `${{ }}`."""
    text = " ".join(str(condition or "").replace("${{", " ").replace("}}", " ").split())
    return text == "always()" or (text.startswith("always() && !(") and "label.name != 'land-next'" in text)


_LABEL = "contains(github.event.pull_request.labels.*.name, 'land-next')"


def runs_without_land_next(condition: object) -> bool:
    """True when the condition lets work run for a pull request without `land-next` (or for another label's event).

    The `land-next` test is read as a boolean `has_label`; the rest is evaluated by the in-repo evaluator for the
    events a parked pull request produces. An expression the evaluator cannot read (a negation, another call)
    is not judged here: the textual rules in the caller still apply.
    """
    from repo_tests._github_expressions import evaluate

    text = " ".join(str(condition or "").replace("${{", " ").replace("}}", " ").split()).replace(_LABEL, "has_label")
    for has_label, action, label in ((False, "opened", ""), (False, "synchronize", ""), (True, "labeled", "unrelated")):
        event = {"action": action, "label": {"name": label}}
        context = {"has_label": has_label, "github": {"event_name": "pull_request", "event": event}}
        try:
            if evaluate(text, context):
                return True
        except ValueError:
            return False
    return False


def runs_when_needs_skipped(condition: object) -> bool:
    """True when a status function runs the job although every job it needs was skipped (no `needs.X.result ==` test)."""
    text = str(condition or "")
    return bool(_STATUS_FUNCTION.search(text)) and not _READS_NEEDS_RESULT.search(text)
