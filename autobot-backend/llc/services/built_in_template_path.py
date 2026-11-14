# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Select a built-in template file by key without the key ever reaching a path (#20884)."""

from pathlib import Path
from typing import Optional

from autobot_shared.security.path_validator import validate_relative_path


def select_built_in_template(templates_dir: Path, template_key: str) -> Optional[Path]:
    """Return the contained realpath of the template whose stem is *template_key*, or None.

    The key only selects among files that exist in *templates_dir*; it is never joined into a
    path. ``glob`` lists symlinks and ``read_text`` follows them, so the listed name is then
    checked by the canonical realpath containment validator (THREAT_MODEL s.1).

    Raises:
        ValueError: the listed file resolves outside *templates_dir* (a symlink escaping it).
    """
    known = {path.stem: path for path in templates_dir.glob("*.json")}
    listed = known.get(template_key)
    if listed is None:
        return None
    return validate_relative_path(listed.name, templates_dir)
