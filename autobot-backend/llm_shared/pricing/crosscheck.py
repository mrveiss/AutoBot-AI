# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Cross-check LiteLLM's prices against OpenRouter's (#16229).

The catalogues name models differently ("claude-haiku-4-5" against
"anthropic/claude-haiku-4.5") and cover different populations -- thousands of
LiteLLM entries against a few hundred OpenRouter models. So the report keeps
its counts apart, because each one alone reads like a clean result:

- ``compared``: in both catalogues under one vendor family, prices compared
- ``disagreed``: compared, and different beyond the tolerance
- ``only_primary`` / ``only_secondary``: listed by one catalogue only
- ``not_comparable``: reseller routes ("bedrock/...") and variants (":free")

A model only one catalogue lists was never checked. It is NOT an agreement.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from llm_shared.pricing.sources import ModelPricing

#: Vendor spellings that differ between the catalogues for one provider.
#: Names, not prices; extend it when a low ``compared`` count shows a gap.
_VENDOR_ALIASES = {"google": "gemini", "mistralai": "mistral", "x-ai": "xai"}
_COMPARED_FIELDS = ("input_per_1m", "output_per_1m")


@dataclass
class CrossCheckReport:
    tolerance_percent: float
    compared: int = 0
    agreed: int = 0
    only_primary: int = 0
    only_secondary: int = 0
    not_comparable: int = 0
    disagreed: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def match_key(vendor: str, model_id: str) -> tuple[str, str]:
    """A catalogue-neutral key: the vendor family and a normalised model name."""
    name = model_id.split(":", 1)[0].lower().replace(".", "-")
    family = vendor.lower()
    return (_VENDOR_ALIASES.get(family, family), name)


def _index(pricings: dict[str, ModelPricing], *, secondary: bool) -> tuple[dict, int]:
    """Comparable entries by match key, and how many were not comparable."""
    index: dict[tuple[str, str], tuple[str, ModelPricing]] = {}
    skipped = 0
    for key, pricing in pricings.items():
        comparable = ":" not in key if secondary else "/" not in key
        if not comparable:
            skipped += 1
            continue
        index.setdefault(match_key(pricing.provider, pricing.model_id), (key, pricing))
    return index, skipped


def _worst_difference(a: ModelPricing, b: ModelPricing, tolerance: float) -> tuple[str, float] | None:
    """The field that differs most beyond *tolerance* percent, or None."""
    worst: tuple[str, float] | None = None
    for name in _COMPARED_FIELDS:
        x, y = getattr(a, name), getattr(b, name)
        base = max(abs(x), abs(y))
        pct = abs(x - y) / base * 100 if base else 0.0
        if pct > tolerance and (worst is None or pct > worst[1]):
            worst = (name, pct)
    return worst


def cross_check(
    primary: dict[str, ModelPricing], secondary: dict[str, ModelPricing], tolerance_percent: float
) -> tuple[CrossCheckReport, dict[str, str], list[str]]:
    """Compare the catalogues.

    Returns the report, a verdict per compared-or-single primary key ("agree",
    "disagree", "single"), and the secondary keys only the secondary lists.
    """
    p_idx, p_skipped = _index(primary, secondary=False)
    s_idx, s_skipped = _index(secondary, secondary=True)
    report = CrossCheckReport(tolerance_percent=tolerance_percent, not_comparable=p_skipped + s_skipped)
    verdicts: dict[str, str] = {}
    for mkey, (pkey, p) in p_idx.items():
        match = s_idx.get(mkey)
        if match is None:
            report.only_primary += 1
            verdicts[pkey] = "single"
            continue
        report.compared += 1
        worst = _worst_difference(p, match[1], tolerance_percent)
        if worst is None:
            report.agreed += 1
            verdicts[pkey] = "agree"
            continue
        field_name, pct = worst
        report.disagreed.append(
            {
                "model": pkey,
                "secondary": match[0],
                "field": field_name,
                "primary_value": getattr(p, field_name),
                "secondary_value": getattr(match[1], field_name),
                "percent": round(pct, 1),
            }
        )
        verdicts[pkey] = "disagree"
    secondary_only = [skey for mkey, (skey, _s) in s_idx.items() if mkey not in p_idx]
    report.only_secondary = len(secondary_only)
    return report, verdicts, secondary_only
