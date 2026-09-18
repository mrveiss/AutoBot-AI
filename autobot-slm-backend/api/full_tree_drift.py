# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Full-tree drift endpoint (#16310): every file, every component, one run.

Owner requirement, 11 Sep 2026: "We need to have drift check for all the
files." ``GET /code-sync/drift`` (Issue #2834) compares one component at a
time and only a fixed extension allowlist; this is additive, not a
replacement -- the existing endpoint and its response shape are untouched, so
the SLM frontend's ``fetchDrift()`` (``useCodeSync.ts``) keeps working exactly
as before. See ``services/full_tree_drift.py`` for the verdict model.

Registers its route onto the SAME ``APIRouter`` ``api.code_sync`` already
builds and ``main.py`` already mounts (imported at the bottom of that module,
after ``router`` exists) rather than adding a second ``app.include_router()``
call -- ``main.py`` is at its own grandfathered line-count ceiling (#16310).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from pydantic import BaseModel

from api.code_sync import router
from services.auth import get_current_user
from services.full_tree_drift import ComponentDrift, compute_all_components_drift


class FileVerdictModel(BaseModel):
    """One deployed-relative path and the verdict it earned."""

    path: str
    verdict: str
    detail: str | None = None


class ComponentDriftModel(BaseModel):
    """One component's full-tree drift result."""

    component: str
    compared: int
    drifted: list[FileVerdictModel]
    exclusions: dict[str, int]
    error: str | None = None
    skipped: bool = False


class FullTreeDriftReport(BaseModel):
    """Every component, every file, one verdict each (#16310)."""

    components: list[ComponentDriftModel]
    total_compared: int
    total_drift: int
    exclusions: dict[str, int]
    checked_at: str
    errors: list[str]


def _to_model(result: ComponentDrift) -> ComponentDriftModel:
    return ComponentDriftModel(
        component=result.component,
        compared=result.compared,
        drifted=[FileVerdictModel(path=v.path, verdict=v.verdict, detail=v.detail) for v in result.drifted],
        exclusions=result.exclusions,
        error=result.error,
        skipped=result.skipped,
    )


def _merge_exclusions(components: list[ComponentDriftModel]) -> dict[str, int]:
    aggregate: dict[str, int] = {}
    for component in components:
        for name, count in component.exclusions.items():
            aggregate[name] = aggregate.get(name, 0) + count
    return aggregate


@router.get("/drift/full", response_model=FullTreeDriftReport)
async def get_full_tree_drift(
    _: Annotated[dict, Depends(get_current_user)],
) -> FullTreeDriftReport:
    """Every file under every deployed component, checked in one run (#16310).

    An empty or unreadable component tree is reported through ``errors``, not
    silently folded into a clean result -- a run that could not look must
    never read the same as a run that looked and found nothing.
    """
    results, checked_at = await compute_all_components_drift()
    components = [_to_model(result) for result in results]
    return FullTreeDriftReport(
        components=components,
        total_compared=sum(component.compared for component in components),
        total_drift=sum(len(component.drifted) for component in components),
        exclusions=_merge_exclusions(components),
        checked_at=checked_at,
        errors=[f"{component.component}: {component.error}" for component in components if component.error],
    )
