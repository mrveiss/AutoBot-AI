# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One implementation of "import a template's work items" (#20472).

``PortabilityService.execute_import`` (snapshots, template exports) and
``TemplateService.import_template`` (library and built-in templates) both call
:func:`import_work_items`, so every item goes through ``WorkItemService.create`` and
its hierarchy rules, parents are remapped from source ids to new ids, and an item that
cannot be created is reported with a reason code rather than dropped.
"""

import uuid
from typing import Any, Awaitable, Callable, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from llc.models.sprint import LLCProject
from llc.services.work_item_hierarchy import HierarchyViolation

# Reason codes in ``skipped_work_items``; the UI maps each to a translated message.
REASON_NO_PROJECT = "no_project"
REASON_PROJECT_NOT_IMPORTED = "project_not_imported"
REASON_PARENT_MISSING = "parent_missing"
REASON_PARENT_NOT_IMPORTED = "parent_not_imported"
REASON_PARENT_CYCLE = "parent_cycle"
REASON_HIERARCHY = "hierarchy_violation"

DEFAULT_PROJECT_NAME = "Imported Project"
DEFAULT_TYPE = "epic"
DEFAULT_PROJECT_STATUS = "backlog"  # the column default; "planning" is not a project status

_REASON_TEXT = {
    REASON_NO_PROJECT: "the template has no project for it",
    REASON_PROJECT_NOT_IMPORTED: "the project it names was not imported",
    REASON_PARENT_MISSING: "its parent is not in the import",
    REASON_PARENT_NOT_IMPORTED: "its parent could not be imported",
    REASON_PARENT_CYCLE: "its parent chain loops back on itself",
    REASON_HIERARCHY: "it breaks the work item hierarchy rules",
}

# (item, company_id, project_id, parent_id) -> new work item id
ItemCreator = Callable[[Dict[str, Any], uuid.UUID, Optional[str], Optional[str]], Awaitable[Any]]
ProjectCreator = Callable[[Dict[str, Any], uuid.UUID], Awaitable[Any]]


def template_name(template: Dict[str, Any]) -> str:
    """The name a template goes by: its metadata name, else its company name."""
    meta = template.get("metadata") or {}
    return meta.get("name") or (template.get("company") or {}).get("name") or DEFAULT_PROJECT_NAME


def select_items(template: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The items to import. A template *export* carries seeds, so only ``is_seed`` ones; any other source all."""
    items = [*template.get("seed_work_items", []), *template.get("work_items", [])]
    if template.get("export_kind") == "template":
        return [i for i in items if i.get("is_seed")]
    return items


def _skip(report: Dict[str, Any], item: Dict[str, Any], reason: str, detail: str = "") -> None:
    title = item.get("title", "")
    entry = {"title": title, "source_id": str(item["id"]) if item.get("id") else None, "reason": reason}
    report["skipped_items"].append(entry)
    report["skipped_titles"].append(title)
    report["warnings"].append(f"Work item {title!r} skipped: {_REASON_TEXT[reason]}{detail}")


def _project_for(item: Dict[str, Any], project_ids: Dict[str, str]) -> tuple:
    """(project id, reason): the project it names, else the first one; never an unrelated one."""
    named = item.get("project_id")
    if named:
        found = project_ids.get(str(named))
        return found, (None if found else REASON_PROJECT_NOT_IMPORTED)
    fallback = next(iter(project_ids.values()), None)
    return fallback, (None if fallback else REASON_NO_PROJECT)


def _parent_state(item: Dict[str, Any], source_ids: set, landed: Dict[str, str], failed: set) -> str:
    """'root', 'ready', 'wait', or the reason the item can never be created."""
    parent = item.get("parent_id")
    if not parent:
        return "root"
    parent = str(parent)
    if parent in landed:
        return "ready"
    if parent not in source_ids:
        return REASON_PARENT_MISSING
    return REASON_PARENT_NOT_IMPORTED if parent in failed else "wait"


async def _create_one(item, company_id, project_ids, parent_new, landed, report, create_item) -> bool:
    project_id, reason = _project_for(item, project_ids)
    if reason:
        _skip(report, item, reason)
        return False
    try:
        new_id = await create_item(item, company_id, project_id, parent_new)
    except HierarchyViolation as exc:
        _skip(report, item, REASON_HIERARCHY, f" ({exc})")
        return False
    report["created"].append(str(new_id))
    if item.get("id"):
        landed[str(item["id"])] = str(new_id)
    return True


async def _create_pass(pending, source_ids, ctx) -> List[Dict[str, Any]]:
    """One topological sweep: create every item whose parent has landed; return those still waiting."""
    landed, failed, report = ctx["landed"], ctx["failed"], ctx["report"]
    waiting = []
    for item in pending:
        state = _parent_state(item, source_ids, landed, failed)
        if state == "wait":
            waiting.append(item)
        elif state in ("root", "ready"):
            parent_new = landed[str(item["parent_id"])] if state == "ready" else None
            ok = await _create_one(
                item, ctx["company_id"], ctx["project_ids"], parent_new, landed, report, ctx["create"]
            )
            if not ok and item.get("id"):
                failed.add(str(item["id"]))
        else:
            _skip(report, item, state)
            if item.get("id"):
                failed.add(str(item["id"]))
    return waiting


async def import_work_items(
    items: List[Dict[str, Any]],
    company_id: uuid.UUID,
    project_ids: Dict[str, str],
    create_item: ItemCreator,
) -> Dict[str, Any]:
    """Create ``items`` parents-first so each parent exists when its child is validated.

    Returns ``{"created": [ids], "skipped_items": [{title, source_id, reason}], "skipped_titles", "warnings"}``.
    """
    report = {"created": [], "skipped_items": [], "skipped_titles": [], "warnings": []}
    source_ids = {str(i["id"]) for i in items if i.get("id")}
    ctx = {
        "landed": {},
        "failed": set(),
        "report": report,
        "company_id": company_id,
        "project_ids": project_ids,
        "create": create_item,
    }
    pending = list(items)
    while pending:
        remaining = await _create_pass(pending, source_ids, ctx)
        if len(remaining) == len(pending):
            for item in remaining:
                _skip(report, item, REASON_PARENT_CYCLE)
            break
        pending = remaining
    return report


def merge_report(
    report: Dict[str, Any], created: Dict[str, Any], skipped: Dict[str, Any], warnings: List[str]
) -> List[Dict[str, Any]]:
    """Fold an :func:`import_work_items` report into the import result; return the structured skips."""
    created["work_items"].extend(report["created"])
    skipped["work_items"].extend(report["skipped_titles"])
    warnings.extend(report["warnings"])
    return report["skipped_items"]


async def create_project(session: AsyncSession, project: Dict[str, Any], company_id: uuid.UUID) -> uuid.UUID:
    """Insert one project for the import."""
    new_id = uuid.uuid4()
    session.add(
        LLCProject(
            id=new_id,
            company_id=company_id,
            name=project.get("name", DEFAULT_PROJECT_NAME),
            description=project.get("description"),
            status=project.get("status", DEFAULT_PROJECT_STATUS),
        )
    )
    await session.flush()
    return new_id


async def create_work_item(
    session: AsyncSession,
    item: Dict[str, Any],
    company_id: uuid.UUID,
    project_id: Optional[str],
    parent_id: Optional[str] = None,
) -> uuid.UUID:
    """Create a work item through ``WorkItemService``, so the hierarchy rules apply.

    No agent is woken: an import records existing work, it does not hand anyone a new assignment.
    """
    from llc.models.enums import WorkItemPriority, WorkItemType  # noqa: PLC0415
    from llc.services.accessors import get_work_item_service  # noqa: PLC0415

    created = await get_work_item_service().create(
        session,
        company_id=str(company_id),
        type=WorkItemType(item.get("type") or DEFAULT_TYPE),
        title=item.get("title", ""),
        description=item.get("description"),
        priority=WorkItemPriority(item.get("priority", "medium")),
        labels=item.get("labels", []),
        project_id=project_id,
        parent_id=parent_id,
        wake_agents=False,
    )
    return created.id


async def import_projects(
    session: AsyncSession, template: Dict[str, Any], company_id: uuid.UUID, created: Dict[str, Any]
) -> Dict[str, str]:
    """Import the template's projects; map source id -> new id.

    A template with work items but no projects gets one project named after it, so every item has a home.
    """
    projects = list(template.get("projects", []))
    if not projects and select_items(template):
        projects = [{"id": None, "name": template_name(template)}]
    project_ids: Dict[str, str] = {}
    for project in projects:
        new_id = await create_project(session, project, company_id)
        created["projects"].append(str(new_id))
        project_ids[str(project.get("id"))] = str(new_id)
    return project_ids


async def import_template_work(
    session: AsyncSession,
    template: Dict[str, Any],
    company_id: uuid.UUID,
    created: Dict[str, Any],
    skipped: Dict[str, Any],
    warnings: List[str],
    create_item: Optional[ItemCreator] = None,
) -> List[Dict[str, Any]]:
    """The public seam both imports call: projects, then work items parents-first.

    Returns the structured skip list (title, source_id, reason code); ``created``, ``skipped`` and
    ``warnings`` are filled in place.
    """
    project_ids = await import_projects(session, template, company_id, created)

    async def _default(item, cid, project_id, parent_id):  # noqa: ANN001, ANN202
        return await create_work_item(session, item, cid, project_id, parent_id)

    report = await import_work_items(select_items(template), company_id, project_ids, create_item or _default)
    return merge_report(report, created, skipped, warnings)
