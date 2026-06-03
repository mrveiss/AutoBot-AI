# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""CLI commands for the per-agent knowledge wiki (GH#9021).

Usage:
    python -m autobot_backend.cli.agent_wiki list   <agent_id> [--namespace NS]
    python -m autobot_backend.cli.agent_wiki create <agent_id> --ns NS --key K --title T --body B
    python -m autobot_backend.cli.agent_wiki delete <agent_id> --id ENTRY_ID
    python -m autobot_backend.cli.agent_wiki context <agent_id>

Requires AUTOBOT_LLC_COMPANY_ID env var (or --company-id flag).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid


def _get_company_id(args: argparse.Namespace) -> uuid.UUID:
    raw = getattr(args, "company_id", None) or os.environ.get("AUTOBOT_LLC_COMPANY_ID")
    if not raw:
        print("ERROR: provide --company-id or set AUTOBOT_LLC_COMPANY_ID", file=sys.stderr)
        sys.exit(1)
    return uuid.UUID(raw)


async def _list(args: argparse.Namespace) -> None:
    from autobot_backend.llc.services.agent_wiki_service import AgentWikiService

    from user_management.database import get_async_session_factory

    company_id = _get_company_id(args)
    factory = get_async_session_factory()
    async with factory() as session:
        svc = AgentWikiService()
        entries = await svc.list_entries(session, args.agent_id, company_id, getattr(args, "namespace", None))
    if not entries:
        print("(no wiki entries)")
        return
    for e in entries:
        print(f"[{e.namespace}/{e.key}] {e.title}  (id={e.id})")
        if getattr(args, "verbose", False):
            print(f"  {e.body[:120]}")


async def _create(args: argparse.Namespace) -> None:
    from autobot_backend.llc.services.agent_wiki_service import AgentWikiService

    from user_management.database import get_async_session_factory

    company_id = _get_company_id(args)
    factory = get_async_session_factory()
    async with factory() as session:
        svc = AgentWikiService()
        entry = await svc.create_entry(
            session,
            agent_id=args.agent_id,
            company_id=company_id,
            namespace=args.ns,
            key=args.key,
            title=args.title,
            body=args.body,
        )
        await session.commit()
    print(f"Created: {entry.id}  [{entry.namespace}/{entry.key}] {entry.title}")


async def _delete(args: argparse.Namespace) -> None:
    from autobot_backend.llc.services.agent_wiki_service import AgentWikiService

    from user_management.database import get_async_session_factory

    company_id = _get_company_id(args)
    factory = get_async_session_factory()
    async with factory() as session:
        svc = AgentWikiService()
        entry = await svc.get_entry(session, uuid.UUID(args.id), args.agent_id, company_id)
        if entry is None:
            print("ERROR: entry not found", file=sys.stderr)
            sys.exit(1)
        await svc.delete_entry(session, entry)
        await session.commit()
    print(f"Deleted: {args.id}")


async def _context(args: argparse.Namespace) -> None:
    from autobot_backend.llc.services.agent_wiki_service import AgentWikiService

    from user_management.database import get_async_session_factory

    company_id = _get_company_id(args)
    factory = get_async_session_factory()
    async with factory() as session:
        svc = AgentWikiService()
        md = await svc.get_wiki_context(session, args.agent_id, company_id)
    print(md if md else "(empty wiki)")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="AutoBot agent wiki CLI")
    parser.add_argument("--company-id", dest="company_id", default=None)
    sub = parser.add_subparsers(dest="cmd")

    p_list = sub.add_parser("list", help="List wiki entries for an agent")
    p_list.add_argument("agent_id")
    p_list.add_argument("--namespace", default=None)
    p_list.add_argument("-v", "--verbose", action="store_true")

    p_create = sub.add_parser("create", help="Create a wiki entry")
    p_create.add_argument("agent_id")
    p_create.add_argument("--ns", default="general")
    p_create.add_argument("--key", required=True)
    p_create.add_argument("--title", required=True)
    p_create.add_argument("--body", default="")

    p_del = sub.add_parser("delete", help="Delete a wiki entry by UUID")
    p_del.add_argument("agent_id")
    p_del.add_argument("--id", required=True)

    p_ctx = sub.add_parser("context", help="Print assembled wiki Markdown for an agent")
    p_ctx.add_argument("agent_id")

    args = parser.parse_args(argv)
    if args.cmd is None:
        parser.print_help()
        sys.exit(0)

    dispatch = {"list": _list, "create": _create, "delete": _delete, "context": _context}
    asyncio.run(dispatch[args.cmd](args))


if __name__ == "__main__":
    main()
