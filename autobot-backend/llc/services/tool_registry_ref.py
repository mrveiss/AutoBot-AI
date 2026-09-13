# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Resolving a tool name against the registry (#14357, extracted for #14852).

Tools have no database table — they register in-process by name via
``autobot_shared.tool_sdk.registry``. So the authority for "is this a real
tool" is the registry, not a foreign key, and validation has to be done in
code by whoever writes a tool name down.

Two callers now write one: ``RoleToolService`` attaches a tool to a role, and
``CompanyToolService`` records a company's URL and logo for one. They must
agree on what counts as a real tool, or an overlay could be written for a name
that can never be attached — a row nothing would ever read. Hence one function
rather than a copy in each.

The failure modes stay separated, as they were when this lived in
``role_tool``. If the registry has not been populated (import ordering, a
stripped-down process) then *every* name looks unknown, and reporting that as
"unknown tool" sends someone hunting for a typo when nothing has registered
yet. An empty registry raises :class:`ToolRegistryUnavailable`; an absent name
raises ``ValueError``. "It isn't there" and "I can't tell" are different
answers and must not collapse into one.
"""

from __future__ import annotations

from dataclasses import dataclass


class ToolRegistryUnavailable(RuntimeError):
    """The tool registry holds no tools, so no name can be validated.

    Distinct from "unknown tool" on purpose: this is an environment problem,
    not a caller mistake, and conflating them turns a startup-ordering bug into
    a wild goose chase for a misspelling.
    """


@dataclass(frozen=True)
class RegisteredTool:
    """The registry's view of one tool, flattened for the catalogue.

    A copy rather than the live ``ToolMetadata``, so a reader cannot mutate the
    registry's own object, and so the catalogue depends on three fields instead
    of the whole SDK dataclass.

    ``tags`` is the grouping. #14852 asked for a ``group`` column; the registry
    already carries this and documents it as "organisational tags for filtering
    / grouping", so a column would have been a second answer to the same
    question.
    """

    name: str
    description: str
    tags: tuple[str, ...]


def _list_tool_metas() -> list:
    """The registry's raw metadata objects.

    Raises :class:`ToolRegistryUnavailable` when the registry is empty, so a
    caller reports an environment problem rather than rendering an empty
    catalogue that reads as "this company uses no tools".
    """
    # Imported lazily, by the fully-qualified ``autobot_shared.tool_sdk`` path
    # (#14373). Both matter:
    #
    # * Lazily, because a module-level import runs while the feature routers
    #   load, and an ImportError there takes the whole LLC router down, not
    #   just this service. Every other consumer imports it the same way
    #   (``tools/tool_registry.py``, ``api/image_generation.py``).
    # * Fully-qualified, not the bare top-level ``tool_sdk`` path, because
    #   ``get_tool_registry()`` returns a module-level singleton stored on
    #   ``autobot_shared/tool_sdk/registry.py``. Reaching that file under a
    #   second module identity (the bare name) would load a *second* copy of it
    #   with its own, independently empty, registry — every tool would look
    #   unregistered while the real registry was fine. The bare ``tool_sdk``
    #   path is exactly what caused the original ``ModuleNotFoundError`` here
    #   (#14373) and is not a supported alias.
    from autobot_shared.tool_sdk.registry import get_tool_registry  # noqa: PLC0415

    metas = list(get_tool_registry().list_tools())
    if not metas:
        raise ToolRegistryUnavailable(
            "the tool registry is empty, so no tool name can be validated; "
            "this is an environment problem, not an unknown tool"
        )
    return metas


def registered_tool_names() -> set[str]:
    """Every name the registry currently knows.

    Reads ``name`` and nothing else on purpose. Validating an attachment must
    not depend on the rest of ``ToolMetadata`` — that coupling would make a
    name check fail for a tool whose description happened to be absent.
    """
    return {meta.name for meta in _list_tool_metas()}


def registered_tools() -> dict[str, RegisteredTool]:
    """Every tool the registry knows, keyed by name, with its metadata.

    The richer read, used by the catalogue. ``require_registered_tool`` uses
    :func:`registered_tool_names` instead, so a name check stays cheap.
    """
    return {
        meta.name: RegisteredTool(
            name=meta.name,
            description=meta.description,
            tags=tuple(meta.tags or ()),
        )
        for meta in _list_tool_metas()
    }


def require_registered_tool(tool_name: str) -> str:
    """The tool must be registered. Returns the cleaned name."""
    cleaned = (tool_name or "").strip()
    if not cleaned:
        raise ValueError("a tool name is required")

    if cleaned not in registered_tool_names():
        raise ValueError(f"unknown tool {cleaned!r}")
    return cleaned
