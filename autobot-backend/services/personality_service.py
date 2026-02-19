# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Personality Profile Service

Manages AutoBot's personality profiles — named, structured identity documents
that shape tone, character traits, operating style, and hard limits.

Profiles are stored as individual JSON files under resources/personalities/.
index.json tracks which profile is active and whether personality is enabled.

Related Issue: #964 - Multi-profile personality system
"""

import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_PERSONALITIES_DIR = (
    Path(os.environ.get("AUTOBOT_BASE_DIR", "/opt/autobot"))
    / "autobot-backend"
    / "resources"
    / "personalities"
)

# Fallback for local dev (relative to this file)
_DEV_PERSONALITIES_DIR = Path(__file__).parent.parent / "resources" / "personalities"

_SYSTEM_PROFILES = {"default", "professional"}

_TONE_VALUES = ("direct", "professional", "casual", "technical")


def _personalities_dir() -> Path:
    """Return the personalities directory, preferring the installed path."""
    if _PERSONALITIES_DIR.exists():
        return _PERSONALITIES_DIR
    return _DEV_PERSONALITIES_DIR


@dataclass
class PersonalityProfile:
    """A named personality profile for AutoBot."""

    id: str
    name: str
    tagline: str = ""
    tone: str = "direct"
    character_traits: List[str] = field(default_factory=list)
    operating_style: List[str] = field(default_factory=list)
    off_limits: List[str] = field(default_factory=list)
    custom_notes: str = ""
    is_system: bool = False
    created_by: str = "system"
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = _now_iso()
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_prompt_block(self) -> str:
        """Render the profile as a system-prompt preamble block."""
        lines = [
            f"## Personality: {self.name}",
            f"*{self.tagline}*" if self.tagline else "",
            f"\n**Tone:** {self.tone.capitalize()}",
        ]
        if self.character_traits:
            lines.append("\n**Character Traits:**")
            lines.extend(f"- {t}" for t in self.character_traits)
        if self.operating_style:
            lines.append("\n**Operating Style:**")
            lines.extend(f"- {s}" for s in self.operating_style)
        if self.off_limits:
            lines.append("\n**Off Limits:**")
            lines.extend(f"- {o}" for o in self.off_limits)
        if self.custom_notes:
            lines.append(f"\n**Additional Notes:**\n{self.custom_notes}")
        return "\n".join(line for line in lines if line is not None)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


class PersonalityManager:
    """
    Manages personality profiles stored in resources/personalities/.

    Issue #964: Supports multiple profiles, activation, reset-to-default,
    and user-created custom profiles.
    """

    def __init__(self) -> None:
        self._dir = _personalities_dir()
        self._index_path = self._dir / "index.json"
        self._default_path = self._dir / "default.json"

    # ------------------------------------------------------------------
    # Index helpers
    # ------------------------------------------------------------------

    def _read_index(self) -> dict:
        """Read index.json; return seeded defaults if missing."""
        if not self._index_path.exists():
            return self._seed_index()
        try:
            return _load_json(self._index_path)
        except Exception as exc:
            logger.error("Failed to read personality index: %s", exc)
            return {"active_id": "default", "enabled": True, "profiles": []}

    def _write_index(self, index: dict) -> None:
        _save_json(self._index_path, index)

    def _seed_index(self) -> dict:
        """Write initial index.json from whatever profile files exist."""
        profiles = []
        for pid in _SYSTEM_PROFILES:
            p = self._dir / f"{pid}.json"
            if p.exists():
                try:
                    data = _load_json(p)
                    profiles.append(
                        {"id": pid, "name": data.get("name", pid), "is_system": True}
                    )
                except Exception:
                    pass
        index: Dict = {"active_id": "default", "enabled": True, "profiles": profiles}
        self._write_index(index)
        return index

    def _update_index_entry(
        self, index: dict, pid: str, name: str, is_system: bool
    ) -> None:
        entries = [e for e in index["profiles"] if e["id"] != pid]
        entries.append({"id": pid, "name": name, "is_system": is_system})
        index["profiles"] = entries

    def _remove_index_entry(self, index: dict, pid: str) -> None:
        index["profiles"] = [e for e in index["profiles"] if e["id"] != pid]

    # ------------------------------------------------------------------
    # Profile file helpers
    # ------------------------------------------------------------------

    def _profile_path(self, pid: str) -> Path:
        return self._dir / f"{pid}.json"

    def _load_profile(self, pid: str) -> Optional[PersonalityProfile]:
        path = self._profile_path(pid)
        if not path.exists():
            return None
        try:
            data = _load_json(path)
            return PersonalityProfile(**{k: v for k, v in data.items()})
        except Exception as exc:
            logger.error("Failed to load personality %s: %s", pid, exc)
            return None

    def _save_profile(self, profile: PersonalityProfile) -> None:
        _save_json(self._profile_path(profile.id), asdict(profile))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_profiles(self) -> List[dict]:
        """Return index profile list (id, name, is_system, active)."""
        index = self._read_index()
        active = index.get("active_id")
        result = []
        for entry in index.get("profiles", []):
            result.append({**entry, "active": entry["id"] == active})
        return result

    def get_profile(self, pid: str) -> Optional[PersonalityProfile]:
        """Return a specific profile by id, or None if not found."""
        return self._load_profile(pid)

    def create_profile(
        self, name: str, created_by: str = "user", **kwargs
    ) -> PersonalityProfile:
        """
        Create a new user profile, optionally copying fields from kwargs.

        Generates a UUID-based id so it never collides with system profiles.
        """
        pid = str(uuid.uuid4())[:8]
        profile = PersonalityProfile(
            id=pid,
            name=name,
            tagline=kwargs.get("tagline", ""),
            tone=kwargs.get("tone", "direct"),
            character_traits=list(kwargs.get("character_traits", [])),
            operating_style=list(kwargs.get("operating_style", [])),
            off_limits=list(kwargs.get("off_limits", [])),
            custom_notes=kwargs.get("custom_notes", ""),
            is_system=False,
            created_by=created_by,
        )
        self._save_profile(profile)
        index = self._read_index()
        self._update_index_entry(index, pid, name, False)
        self._write_index(index)
        logger.info("Personality profile created: %s (%s)", name, pid)
        return profile

    def update_profile(self, pid: str, updates: dict) -> PersonalityProfile:
        """
        Update an existing profile's fields.

        Raises ValueError if profile not found.
        System profiles can be updated (to allow minor edits) but not deleted.
        """
        profile = self._load_profile(pid)
        if profile is None:
            raise ValueError(f"Personality profile not found: {pid}")
        allowed = {
            "name",
            "tagline",
            "tone",
            "character_traits",
            "operating_style",
            "off_limits",
            "custom_notes",
        }
        for key, val in updates.items():
            if key in allowed:
                setattr(profile, key, val)
        profile.updated_at = _now_iso()
        self._save_profile(profile)
        index = self._read_index()
        self._update_index_entry(index, pid, profile.name, profile.is_system)
        self._write_index(index)
        logger.info("Personality profile updated: %s", pid)
        return profile

    def delete_profile(self, pid: str) -> None:
        """
        Delete a user-created profile.

        Raises ValueError if profile is a system profile or not found.
        If the deleted profile was active, falls back to 'default'.
        """
        if pid in _SYSTEM_PROFILES:
            raise ValueError(f"Cannot delete system profile: {pid}")
        path = self._profile_path(pid)
        if not path.exists():
            raise ValueError(f"Personality profile not found: {pid}")
        path.unlink()
        index = self._read_index()
        self._remove_index_entry(index, pid)
        if index.get("active_id") == pid:
            index["active_id"] = "default"
        self._write_index(index)
        logger.info("Personality profile deleted: %s", pid)

    def activate_profile(self, pid: str) -> None:
        """Set the active profile. Raises ValueError if not found."""
        if not self._profile_path(pid).exists():
            raise ValueError(f"Personality profile not found: {pid}")
        index = self._read_index()
        index["active_id"] = pid
        self._write_index(index)
        logger.info("Personality profile activated: %s", pid)

    def reset_profile(self, pid: str) -> PersonalityProfile:
        """
        Reset a profile's content to match the default profile.

        For system profiles: restores the profile file from default.json content,
        preserving id/name/is_system. For user profiles: overwrites all trait
        fields with default values, giving a clean starting point.
        Raises ValueError if default.json or the target profile is missing.
        """
        default = self._load_profile("default")
        if default is None:
            raise ValueError("default.json missing — cannot reset")
        profile = self._load_profile(pid)
        if profile is None:
            raise ValueError(f"Personality profile not found: {pid}")
        profile.tagline = default.tagline
        profile.tone = default.tone
        profile.character_traits = list(default.character_traits)
        profile.operating_style = list(default.operating_style)
        profile.off_limits = list(default.off_limits)
        profile.custom_notes = ""
        profile.updated_at = _now_iso()
        self._save_profile(profile)
        logger.info("Personality profile reset to default: %s", pid)
        return profile

    def get_active_profile(self) -> Optional[PersonalityProfile]:
        """Return the active profile if personality is enabled, else None."""
        index = self._read_index()
        if not index.get("enabled", True):
            return None
        active_id = index.get("active_id", "default")
        return self._load_profile(active_id)

    def set_enabled(self, enabled: bool) -> None:
        """Toggle personality on or off globally."""
        index = self._read_index()
        index["enabled"] = enabled
        self._write_index(index)
        logger.info("Personality %s", "enabled" if enabled else "disabled")

    def is_enabled(self) -> bool:
        return self._read_index().get("enabled", True)


# Module-level singleton
_manager: Optional[PersonalityManager] = None


def get_personality_manager() -> PersonalityManager:
    """Return the module-level PersonalityManager singleton."""
    global _manager
    if _manager is None:
        _manager = PersonalityManager()
    return _manager
