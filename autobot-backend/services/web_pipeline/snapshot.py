# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Accessibility Snapshot — captures and queries the accessibility tree of a Playwright page.

The accessibility tree is a structured representation of the page that screen readers
and assistive technology use.  It provides a robust, DOM-independent way to locate
interactive elements and verify page state without relying on fragile CSS selectors.

Issue #1967 — Web Pipeline Engine Phase 1.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class AccessibilityNode:
    """A single node in the accessibility tree.

    Fields mirror the subset of the ARIA spec exposed by Playwright's
    ``page.accessibility.snapshot()``.

    Ref: Issue #1967.
    """

    role: str
    name: str = ""
    value: str | None = None
    description: str | None = None
    checked: bool | None = None
    disabled: bool | None = None
    expanded: bool | None = None
    focused: bool | None = None
    level: int | None = None
    multiselectable: bool | None = None
    required: bool | None = None
    selected: bool | None = None
    children: List["AccessibilityNode"] = field(default_factory=list)
    # Raw properties that do not map to first-class fields
    properties: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain nested dict."""
        out: Dict[str, Any] = {"role": self.role, "name": self.name}
        for attr in (
            "value",
            "description",
            "checked",
            "disabled",
            "expanded",
            "focused",
            "level",
            "multiselectable",
            "required",
            "selected",
        ):
            val = getattr(self, attr)
            if val is not None:
                out[attr] = val
        if self.properties:
            out["properties"] = self.properties
        if self.children:
            out["children"] = [c.to_dict() for c in self.children]
        return out


# ---------------------------------------------------------------------------
# Type alias
# ---------------------------------------------------------------------------

AccessibilityTree = AccessibilityNode | None

# ---------------------------------------------------------------------------
# Snapshot class
# ---------------------------------------------------------------------------

# First-class ARIA attributes that become typed fields on AccessibilityNode
_TYPED_ATTRS = frozenset(
    {
        "name",
        "value",
        "description",
        "checked",
        "disabled",
        "expanded",
        "focused",
        "level",
        "multiselectable",
        "required",
        "selected",
    }
)


class AccessibilitySnapshot:
    """Captures and queries the accessibility tree of a Playwright page.

    Usage::

        snap = AccessibilitySnapshot()
        tree = await snap.capture(page)
        text = snap.to_text(tree)
        buttons = snap.find_by_role(tree, "button")
        submit = snap.find_by_name(tree, "Submit")

    Issue #1967 — Web Pipeline Engine Phase 1.
    """

    # ------------------------------------------------------------------
    # Capture
    # ------------------------------------------------------------------

    async def capture(self, page: Any) -> AccessibilityTree:
        """Capture the full accessibility tree from a Playwright page.

        Args:
            page: A Playwright ``Page`` object.

        Returns:
            Root :class:`AccessibilityNode`, or ``None`` when the page has no
            accessibility tree (e.g., blank page).
        """
        try:
            raw = await page.accessibility.snapshot(interesting_only=False)
        except Exception as exc:
            logger.error("AccessibilitySnapshot.capture failed: %s", exc)
            return None

        if raw is None:
            logger.debug("AccessibilitySnapshot.capture: page returned empty tree")
            return None

        root = self._parse_node(raw)
        logger.info(
            "AccessibilitySnapshot captured tree: role=%r name=%r children=%d",
            root.role,
            root.name,
            len(root.children),
        )
        return root

    # ------------------------------------------------------------------
    # Text rendering
    # ------------------------------------------------------------------

    def to_text(self, tree: AccessibilityTree, indent: int = 0) -> str:
        """Render the accessibility tree as an indented plain-text string.

        Useful for debugging and LLM consumption.

        Args:
            tree: Root node returned by :meth:`capture`.
            indent: Current indentation level (used in recursive calls).

        Returns:
            Multi-line string, or an empty string for a ``None`` tree.
        """
        if tree is None:
            return ""
        lines = self._node_to_lines(tree, indent)
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Search helpers
    # ------------------------------------------------------------------

    def find_by_role(self, tree: AccessibilityTree, role: str) -> List[AccessibilityNode]:
        """Return all nodes whose ``role`` matches (case-insensitive).

        Args:
            tree: Root node to search from.
            role: ARIA role string, e.g. ``"button"``, ``"textbox"``.

        Returns:
            Flat list of matching nodes in document order.
        """
        if tree is None:
            return []
        results: List[AccessibilityNode] = []
        self._collect(tree, lambda n: n.role.lower() == role.lower(), results)
        return results

    def find_by_name(self, tree: AccessibilityTree, name: str) -> List[AccessibilityNode]:
        """Return all nodes whose accessible ``name`` contains *name* (case-insensitive).

        Args:
            tree: Root node to search from.
            name: Substring to search for in the node's ``name`` field.

        Returns:
            Flat list of matching nodes in document order.
        """
        if tree is None:
            return []
        results: List[AccessibilityNode] = []
        self._collect(tree, lambda n: name.lower() in n.name.lower(), results)
        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _parse_node(self, raw: Dict[str, Any]) -> AccessibilityNode:
        """Recursively convert a raw Playwright accessibility dict into a node tree.

        Ref: Issue #1967.
        """
        role = str(raw.get("role", ""))
        kwargs: Dict[str, Any] = {"role": role}
        extra: Dict[str, Any] = {}

        for key, value in raw.items():
            if key in ("role", "children"):
                continue
            if key in _TYPED_ATTRS:
                kwargs[key] = value
            else:
                extra[key] = value

        if extra:
            kwargs["properties"] = extra

        children_raw = raw.get("children") or []
        kwargs["children"] = [self._parse_node(c) for c in children_raw]

        return AccessibilityNode(**kwargs)

    def _node_to_lines(self, node: AccessibilityNode, indent: int) -> List[str]:
        """Render a single node and its subtree as indented text lines.

        Ref: Issue #1967.
        """
        prefix = "  " * indent
        parts = [f"{node.role}"]
        if node.name:
            parts.append(f'"{node.name}"')
        if node.value is not None:
            parts.append(f"value={node.value!r}")
        if node.checked is not None:
            parts.append(f"checked={node.checked}")
        if node.disabled:
            parts.append("disabled")
        lines = [prefix + " ".join(parts)]
        for child in node.children:
            lines.extend(self._node_to_lines(child, indent + 1))
        return lines

    def _collect(
        self,
        node: AccessibilityNode,
        predicate: Any,
        results: List[AccessibilityNode],
    ) -> None:
        """Depth-first traversal collecting nodes that satisfy *predicate*.

        Ref: Issue #1967.
        """
        if predicate(node):
            results.append(node)
        for child in node.children:
            self._collect(child, predicate, results)
