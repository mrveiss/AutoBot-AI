# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Data migration: the desktop server carries the `vnc` role (#22211).

The fleet serves ONE VNC desktop, on the desktop server. Fleet roles come from the SLM database,
so that server needs a `vnc` NodeRole row (and `vnc` declared on `nodes.roles`, as the assign-role
endpoint does) before provisioning applies the vnc role and removes xrdp.

The desktop server is the node that carries the xrdp desktop purpose, read from the database and
never from an address or a hostname. xrdp is not an SLM role, so the purpose is recorded by what the
xrdp role leaves behind: a registered `rdp` credential (`node_credentials.credential_type`) or a
monitored `xrdp` service row (`services.service_name`).

  * a node already holds the vnc role -> nothing to assign: the desktop server is whichever node holds
    it, and the fleet update provisions it (registering its credential);
  * exactly one such node -> it gets the role;
  * none -> nothing to do (a fresh install, or the role was assigned by hand);
  * more than one -> ambiguous, so NO node is changed and a warning names the candidates. One
    desktop is the rule; picking between two would be a guess.

Idempotent (a node that already has the row is left alone, whatever its status), never deletes or
rewrites a row. `downgrade()` removes only the row this migration created (assignment_type
`migration`) and the declaration it added.
"""

import logging
from typing import List

from migrations.utils import get_connection, table_exists

logger = logging.getLogger(__name__)

#: The role this migration assigns.
VNC_ROLE = "vnc"
#: Marks rows this migration created, so downgrade() removes only those.
MIGRATION_ASSIGNMENT_TYPE = "migration"
#: Recorded by the assign-role endpoint for a role that is assigned but not yet provisioned.
ASSIGNED_STATUS = "not_installed"
#: What the xrdp role leaves behind on the node that carried the desktop purpose.
RDP_CREDENTIAL_TYPE = "rdp"
XRDP_SERVICE_NAME = "xrdp"

_DECLARE_SQL = """
    UPDATE nodes
       SET roles = (COALESCE(roles::jsonb, '[]'::jsonb) || to_jsonb(%s::text))::json
     WHERE node_id = %s AND NOT (COALESCE(roles::jsonb, '[]'::jsonb) @> to_jsonb(%s::text))
"""
_UNDECLARE_SQL = """
    UPDATE nodes
       SET roles = (COALESCE(roles::jsonb, '[]'::jsonb) - %s)::json
     WHERE node_id = %s AND COALESCE(roles::jsonb, '[]'::jsonb) @> to_jsonb(%s::text)
"""


def _desktop_candidates(cursor) -> List[str]:
    """Nodes that carry the xrdp desktop purpose, from whichever tables exist."""
    found = set()
    if table_exists(cursor, "node_credentials"):
        cursor.execute(
            "SELECT DISTINCT node_id FROM node_credentials WHERE credential_type = %s", (RDP_CREDENTIAL_TYPE,)
        )
        found.update(row[0] for row in cursor.fetchall())
    if table_exists(cursor, "services"):
        cursor.execute("SELECT DISTINCT node_id FROM services WHERE service_name = %s", (XRDP_SERVICE_NAME,))
        found.update(row[0] for row in cursor.fetchall())
    return sorted(found)


def _existing_nodes(cursor, node_ids: List[str]) -> List[str]:
    cursor.execute("SELECT node_id FROM nodes WHERE node_id = ANY(%s)", (node_ids,))
    return sorted(row[0] for row in cursor.fetchall())


def _vnc_holders(cursor) -> List[str]:
    """Nodes that already carry the vnc role: the desktop server is whichever node holds it."""
    cursor.execute("SELECT DISTINCT node_id FROM node_roles WHERE role_name = %s", (VNC_ROLE,))
    return sorted(row[0] for row in cursor.fetchall())


def _assign(cursor, node_id: str) -> bool:
    """Insert the NodeRole row and declare the role; False when the node already has the row."""
    cursor.execute("SELECT 1 FROM node_roles WHERE node_id = %s AND role_name = %s", (node_id, VNC_ROLE))
    if cursor.fetchone():
        return False
    cursor.execute(
        "INSERT INTO node_roles (node_id, role_name, assignment_type, status) VALUES (%s, %s, %s, %s)",
        (node_id, VNC_ROLE, MIGRATION_ASSIGNMENT_TYPE, ASSIGNED_STATUS),
    )
    cursor.execute(_DECLARE_SQL, (VNC_ROLE, node_id, VNC_ROLE))
    return True


def migrate(db_url: str) -> None:
    """Assign the vnc role to the single node that carries the xrdp desktop purpose (#22211)."""
    conn = get_connection(db_url)
    try:
        cursor = conn.cursor()
        if not (table_exists(cursor, "nodes") and table_exists(cursor, "node_roles")):
            logger.info("assign_vnc_role_to_desktop_node: no nodes/node_roles table, nothing to assign")
            return
        holder = _vnc_holders(cursor)
        if holder:
            logger.info(
                "assign_vnc_role_to_desktop_node: %s already holds the %s role, nothing to assign "
                "(the fleet update provisions it)",
                holder,
                VNC_ROLE,
            )
            return
        candidates = _existing_nodes(cursor, _desktop_candidates(cursor))
        if len(candidates) != 1:
            logger.warning(
                "assign_vnc_role_to_desktop_node: %d node(s) carry the xrdp desktop purpose %s; "
                "assigning the vnc role to none (assign it in the SLM when exactly one is the desktop server)",
                len(candidates),
                candidates,
            )
            return
        if _assign(cursor, candidates[0]):
            conn.commit()
            logger.info("assign_vnc_role_to_desktop_node: assigned %s to %s", VNC_ROLE, candidates[0])
        else:
            logger.info("assign_vnc_role_to_desktop_node: %s already has the %s role", candidates[0], VNC_ROLE)
    finally:
        conn.close()


def downgrade(db_url: str) -> None:
    """Remove only the vnc rows this migration created, and the declaration it added."""
    conn = get_connection(db_url)
    try:
        cursor = conn.cursor()
        if not table_exists(cursor, "node_roles"):
            return
        cursor.execute(
            "DELETE FROM node_roles WHERE role_name = %s AND assignment_type = %s RETURNING node_id",
            (VNC_ROLE, MIGRATION_ASSIGNMENT_TYPE),
        )
        for (node_id,) in cursor.fetchall():
            cursor.execute(_UNDECLARE_SQL, (VNC_ROLE, node_id, VNC_ROLE))
        conn.commit()
    finally:
        conn.close()
