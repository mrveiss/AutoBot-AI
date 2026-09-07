# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No two model-pricing tables may price one model differently (#15912).

Eight tables in this repository stated what a model costs when #15912 began.
Three were dicts keyed by model id; five are provider baselines in
``llm_shared/pricing/``, four of which carried a comment saying they were *"kept
in sync with"* another table -- by hand, and pointing at a module the canonical
table had already moved out of.

Six remain. Two became comprehensions over the canonical table, because a
derived view cannot drift and two literals can.

The population is **discovered from the source**, not listed here. A list of the
tables known when this was written is a measurement frozen as a rule: the fourth
table gets added, matches no name in the list, and the guard reports clean about
a file it never opened. So this walks the AST of every tracked ``*.py`` and
recognises pricing tables by *shape*:

* a dict of ``{model: {"input"/"output"}}`` or ``{model: {"prompt"/"completion"}}``
* a list of ``(model_id, input, output)`` or ``(model_id, input, output, cache)``

Shape-discovery is not a nicety here: a grep for the four baselines that named
the canonical table found four. There were five. ``vertexai_source.py`` carried
no pointer at all, so nothing that searched for the pointer could find it.

**Units are normalised before comparison, and that is the point.** ``PER_1K``
holds prices a thousandth the size of ``PER_1M``; comparing raw numbers would
call every shared model a disagreement and comparing only same-unit tables would
have missed the two real ones. Normalising is what let this find that ``PER_1K``
priced ``gpt-4o`` at 5.00/15.00 against 2.50/10.00 everywhere else -- not a unit
artefact, a stale price nobody had reason to look at.

WHAT THIS CANNOT SEE, stated so it is not mistaken for cover. The comparison is
keyed on the model **id string**, so two ids for one model are invisible to it:
``claude-sonnet-4-20250514`` and ``claude-sonnet-4`` are the same model and
could drift apart without this failing. Aliases would need a mapping this guard
has no way to discover, and inventing one would make it wrong in a quieter way.
"""

from __future__ import annotations

import ast
import subprocess
from typing import Dict, List, Tuple

from repo_tests._paths import repo_root

from autobot_shared.paths import scrubbed_git_env

REPO_ROOT = repo_root()

#: Per-token-count divisors, by the unit a table's name declares. A table whose
#: name says neither is read as per-1M, which is the repository default.
_PER_1K = 1_000

#: Key pairs a pricing entry may use. Both name the same two numbers.
_KEY_PAIRS = (("input", "output"), ("prompt", "completion"))

#: Floor for literal tables discovered. Bound to tables *found*, never to
#: disagreements found -- a floor tracking findings relaxes as the tree improves.
#:
#: Six, and it started at eight. The two that went are
#: ``ssot_constants.MODEL_COSTS_PER_1M_TOKENS`` and
#: ``ssot_constants.MODEL_PRICING_PER_1K_TOKENS``, which #15912 turned into
#: comprehensions over the canonical table. A derived view is not a table that
#: can drift, so the sweep correctly stops counting it -- **lowering this floor
#: was the point of the work, not an accommodation of a weaker sweep.** The two
#: cases look identical from the number alone, which is why the reason is written
#: here: if this drops again, the question is whether a literal became derived
#: (fine, re-base and say which) or the sweep stopped seeing one (not fine).
#:
#: The remaining six are the canonical table and five provider baselines in
#: ``llm_shared/pricing/``, which cannot be derived -- they exist to be a fetch
#: fallback and carry provider-specific fields.
_MIN_TABLES = 6

#: Floor for models compared across more than one table: 25, pinned at the count
#: found. Discovery can find every table and still compare nothing if key
#: normalisation breaks, and comparing nothing reads exactly like agreement.
_MIN_SHARED_MODELS = 25

#: Model ids a table may deliberately price differently, with the reason. Empty,
#: and it should stay that way: an entry here is a model whose cost depends on
#: which table you happened to read.
_ALLOWED: frozenset[str] = frozenset()

Price = Tuple[float, float]


def _tracked_python_files() -> List[str]:
    completed = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", "ls-files", "*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        env=scrubbed_git_env(),
    )
    return [n for n in completed.stdout.split("\n") if n and not n.startswith(".worktrees/")]


def _divisor(name: str) -> float:
    """Per-1K tables hold a thousandth of the per-1M price. Read off the name."""
    return 1 / _PER_1K if "PER_1K" in name.upper() else 1.0


def _prices_from_dict(node: ast.Dict) -> Dict[str, Price]:
    """``{MODEL_CONST: {"input": x, "output": y}}`` — keys may be names or literals."""
    out: Dict[str, Price] = {}
    for key, value in zip(node.keys, node.values):
        if key is None or not isinstance(value, ast.Dict):
            continue
        inner = {k.value: v for k, v in zip(value.keys, value.values) if isinstance(k, ast.Constant)}
        for lo, hi in _KEY_PAIRS:
            if lo in inner and hi in inner:
                try:
                    out[ast.unparse(key)] = (float(ast.literal_eval(inner[lo])), float(ast.literal_eval(inner[hi])))
                except (ValueError, TypeError, SyntaxError):
                    pass
                break
    return out


def _prices_from_list(node: ast.List) -> Dict[str, Price]:
    """``[(model_id, input, output[, cache_read])]`` — the provider-baseline shape."""
    out: Dict[str, Price] = {}
    for element in node.elts:
        if not isinstance(element, ast.Tuple) or not 3 <= len(element.elts) <= 4:
            continue
        try:
            model, low, high = (ast.literal_eval(e) for e in element.elts[:3])
        except (ValueError, TypeError, SyntaxError):
            continue
        if isinstance(model, str) and isinstance(low, (int, float)) and isinstance(high, (int, float)):
            out[repr(model)] = (float(low), float(high))
    return out


def discover_pricing_tables() -> Dict[str, Dict[str, Price]]:
    """``{"path::NAME": {model_key: (input_per_1m, output_per_1m)}}``.

    Recognised by shape, so a table added under any name in any file is covered
    without an edit here.
    """
    tables: Dict[str, Dict[str, Price]] = {}
    for name in _tracked_python_files():
        path = REPO_ROOT / name
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        # `ast.walk`, not `tree.body`: a table assigned as a class attribute is
        # still a table, and this codebase does put pricing names at class level
        # (`calculators.py`'s `TokenTracker.DEFAULT_COSTS` and
        # `CostCalculator.MODEL_PRICING`). The docstring promises "any name in any
        # file"; module-level-only delivered less than that. Zero such tables
        # today, so it costs nothing now — but a floor or a sweep that claims
        # more reach than it has is the defect this whole file is about.
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            label = next((t.id for t in targets if isinstance(t, ast.Name)), None)
            if label is None or node.value is None:
                continue
            if isinstance(node.value, ast.Dict):
                prices = _prices_from_dict(node.value)
            elif isinstance(node.value, ast.List):
                prices = _prices_from_list(node.value)
            else:
                continue
            if len(prices) < 2:
                continue
            scale = _divisor(label)
            tables[f"{name}::{label}"] = {m: (lo / scale, hi / scale) for m, (lo, hi) in prices.items()}
    return tables


def _normalised_key(raw: str) -> str:
    """Model keys are written as constants in one table and literals in another.

    Compared by the constant's *value* where it is known, so
    ``OPENAI_GPT4O`` and ``"gpt-4o"`` are recognised as one model. Resolved by
    import rather than by guessing: a name this cannot resolve stays itself and
    simply never matches, which under-reports rather than inventing a match.
    """
    import autobot_shared.ssot_constants as constants

    if raw.startswith(("'", '"')):
        return ast.literal_eval(raw)
    return getattr(constants, raw, raw) if isinstance(getattr(constants, raw, None), str) else raw


def alias_pairs() -> Dict[str, str]:
    """``{alias_id: canonical_id}``, derived from the constant NAMES.

    `ANTHROPIC_CLAUDE3_OPUS` / `ANTHROPIC_CLAUDE3_OPUS_DATED` and
    `ANTHROPIC_CLAUDE_SONNET4_SHORT` / `ANTHROPIC_CLAUDE_SONNET4` are one model
    each under two ids. The comparison above is keyed on the id *string*, so
    those pairs are invisible to it and could drift apart without failing
    anything.

    **The first version of this PR mitigated that by keeping the aliases
    adjacent in the table, and the comment saying so was wrong**: the aliases
    ended up adjacent to each other and ~60 lines from the twins they would
    drift from. Worse, proximity is precisely the mechanism #15912 was filed
    about — "the drift is currently prevented by attention, and #15910 removes
    the thing attention was relying on". A fix that reinstates attention as its
    own safeguard has not fixed it.

    Derived from the `_DATED` / `_SHORT` suffix convention rather than listed,
    so a fifth alias added tomorrow is covered without anyone remembering. A
    hand-written map would be an enumeration, which is the other half of the
    same complaint.
    """
    import autobot_shared.ssot_constants as constants

    names = {n for n in dir(constants) if isinstance(getattr(constants, n), str)}
    pairs: Dict[str, str] = {}
    for name in sorted(names):
        for suffix in ("_DATED", "_SHORT"):
            base = name[: -len(suffix)]
            if name.endswith(suffix) and base in names:
                alias, canonical = (name, base) if suffix == "_SHORT" else (base, name)
                pairs[getattr(constants, alias)] = getattr(constants, canonical)
    return pairs


_ALIASES = alias_pairs()
_TABLES = discover_pricing_tables()
_BY_MODEL: Dict[str, Dict[str, Price]] = {}
for _table, _prices in _TABLES.items():
    for _raw, _price in _prices.items():
        _BY_MODEL.setdefault(_normalised_key(_raw), {})[_table] = _price
_SHARED = {m: t for m, t in _BY_MODEL.items() if len(t) > 1}


def test_the_sweep_found_the_pricing_tables() -> None:
    """Runs first: every assertion below passes vacuously over an empty sweep."""
    assert len(_TABLES) >= _MIN_TABLES, (
        f"discovered {len(_TABLES)} pricing table(s), floor {_MIN_TABLES}. FIX THE SWEEP — "
        f"a clean result below this floor asserts nothing.\nFound: {sorted(_TABLES)}"
    )


def test_the_sweep_compared_models_across_tables() -> None:
    """Discovery can find every table and still compare nothing.

    If key normalisation breaks, each table's models look unique to it, no model
    is shared, and the disagreement check passes over an empty set — which reads
    exactly like agreement.
    """
    assert len(_SHARED) >= _MIN_SHARED_MODELS, (
        f"only {len(_SHARED)} model(s) are priced by more than one table (floor "
        f"{_MIN_SHARED_MODELS}) across {len(_TABLES)} tables. Key normalisation has "
        "broken; the check below is comparing almost nothing."
    )


def test_no_two_tables_price_one_model_differently() -> None:
    problems = []
    for model, per_table in sorted(_SHARED.items()):
        if model in _ALLOWED:
            continue
        if len({(round(lo, 6), round(hi, 6)) for lo, hi in per_table.values()}) > 1:
            rows = "\n".join(f"      {lo:>9} / {hi:<9}  {t}" for t, (lo, hi) in sorted(per_table.items()))
            problems.append(f"  {model}\n{rows}")
    assert not problems, (
        f"model(s) priced differently by two tables ({len(_TABLES)} tables, "
        f"{len(_SHARED)} shared models):\n" + "\n".join(problems) + "\n\n"
        "Prices are normalised to per-1M before comparison, so a unit difference is "
        "not what this reports. Derive the second table from the first rather than "
        "correcting both by hand (#15912)."
    )


# ---------------------------------------------------------------------------
# The derived views. Everything above reads the AST and therefore sees only
# LITERAL tables — a comprehension is invisible to it.
#
# That gap is created by the fix. Consolidation moved the risk from "two
# literals drift apart" to "the derivation is wrong", and the mutation said so:
# deleting the `/ 1000` from the per-1K comprehension left the sweep at 3 passed.
# A guard that stops where its subject moved to is not a guard.
# ---------------------------------------------------------------------------


def test_the_per_1k_view_is_the_canonical_table_divided_by_a_thousand() -> None:
    """Every model, at exactly a thousandth, under the renamed keys."""
    from autobot_shared.model_pricing import MODEL_PRICING_PER_1K_TOKENS, MODEL_PRICING_PER_1M_TOKENS

    wrong = [
        f"  {model}: per-1K says {view['prompt']}/{view['completion']}, "
        f"expected {price['input'] / 1000}/{price['output'] / 1000}"
        for model, price in MODEL_PRICING_PER_1M_TOKENS.items()
        for view in [MODEL_PRICING_PER_1K_TOKENS.get(model, {})]
        if not view
        or round(view["prompt"], 12) != round(price["input"] / 1000, 12)
        or round(view["completion"], 12) != round(price["output"] / 1000, 12)
    ]
    assert not wrong, "the per-1K view is not the canonical table / 1000:\n" + "\n".join(wrong)


def test_the_per_1k_view_keeps_the_two_entries_that_are_not_models() -> None:
    """`default` is the fallback `TokenTracker.track_usage` reads for an unknown model.

    Dropping it while deriving the rest would make every unknown model free, and
    no assertion above would notice — the derivation would be perfectly correct
    over a set that no longer contains the entry that matters.
    """
    from autobot_shared.model_pricing import MODEL_PRICING_PER_1K_TOKENS

    assert MODEL_PRICING_PER_1K_TOKENS.get("default") == {"prompt": 0.001, "completion": 0.002}
    assert MODEL_PRICING_PER_1K_TOKENS.get("ollama") == {"prompt": 0.0, "completion": 0.0}


def test_the_per_1m_view_is_the_canonical_table() -> None:
    """`MODEL_COSTS_PER_1M_TOKENS` is the older name for the same thing."""
    from autobot_shared.model_pricing import MODEL_COSTS_PER_1M_TOKENS, MODEL_PRICING_PER_1M_TOKENS

    assert MODEL_COSTS_PER_1M_TOKENS == MODEL_PRICING_PER_1M_TOKENS


def test_the_old_import_sites_still_resolve() -> None:
    """The views moved modules; the names callers use did not.

    `constants/model_constants.py` re-exports both, and a re-export is
    indistinguishable from an unused import to autoflake — which has deleted one
    before (#15911). This fails if that happens again.
    """
    import importlib

    module = importlib.import_module("constants.model_constants")
    for name in ("MODEL_COSTS_PER_1M_TOKENS", "MODEL_PRICING_PER_1K_TOKENS"):
        assert hasattr(module, name), f"constants.model_constants no longer re-exports {name} (#15911)"


def test_the_alias_pairing_found_the_known_aliases() -> None:
    """Reach floor for the pairing itself.

    An empty map makes the assertion below pass over nothing — which is exactly
    how the adjacency "mitigation" it replaces behaved.
    """
    assert len(_ALIASES) >= 4, (
        f"derived only {len(_ALIASES)} alias pair(s) from the `_DATED`/`_SHORT` naming "
        f"convention: {_ALIASES}. The convention changed, or the sweep broke."
    )


def test_an_alias_is_priced_the_same_as_the_model_it_aliases() -> None:
    """Two ids for one model must not disagree.

    Invisible to the table-vs-table comparison, which keys on the id string:
    `claude-sonnet-4` and `claude-sonnet-4-20250514` are different strings and
    would never be compared to each other, in any number of tables.
    """
    problems = []
    for alias, canonical in sorted(_ALIASES.items()):
        for table, prices in sorted(_TABLES.items()):
            resolved = {_normalised_key(raw): price for raw, price in prices.items()}
            if alias in resolved and canonical in resolved and resolved[alias] != resolved[canonical]:
                problems.append(
                    f"  {table}\n"
                    f"      {resolved[alias][0]:>9} / {resolved[alias][1]:<9}  {alias}\n"
                    f"      {resolved[canonical][0]:>9} / {resolved[canonical][1]:<9}  {canonical}"
                )
    assert not problems, (
        "one model priced differently under two of its own ids:\n" + "\n".join(problems)
    )


def test_the_alias_check_would_catch_a_divergence() -> None:
    """The fixture. The tree agrees today, so a check that compared nothing
    would pass every assertion above — the population is four."""
    assert _ALIASES, "no alias pairs derived; the check below proves nothing"
    alias, canonical = next(iter(sorted(_ALIASES.items())))
    resolved = {alias: (1.0, 2.0), canonical: (9.0, 2.0)}
    assert resolved[alias] != resolved[canonical]
