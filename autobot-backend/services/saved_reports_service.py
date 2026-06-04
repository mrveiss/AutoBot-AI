# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Saved Reports Service — Redis-backed CRUD for saved analytics reports.

Provides persistence for user-configured report definitions that can be
re-run on demand. Each report stores a name, type, and list of sections
to include (e.g. cost, agents). Running a report fetches live analytics
data filtered by the saved configuration.

Related Issues: #1295 (saved reports persistence layer)
Parent Issue: #1282 (bi_export_endpoints.py integration)
"""

import json
import uuid
from datetime import timedelta
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import RedisDatabase
from autobot_shared.redis_mixin import AsyncRedisClientMixin
from autobot_shared.time_utils import now_utc, utc_timestamp

logger = get_logger(__name__)

# Redis key patterns (ANALYTICS db, index 11)
_REPORT_KEY_PREFIX = "saved_report:"
_REPORT_INDEX_KEY = "saved_reports:index"


class SavedReportsService(AsyncRedisClientMixin):
    """Redis-backed CRUD service for saved analytics reports."""

    _redis_database = RedisDatabase.ANALYTICS

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def create_report(
        self,
        name: str,
        report_type: str = "executive",
        sections: List[str] | None = None,
    ) -> Dict[str, Any]:
        """Create and persist a new saved report."""
        redis = await self._get_redis()
        report_id = str(uuid.uuid4())
        now = utc_timestamp()

        report = {
            "id": report_id,
            "name": name,
            "report_type": report_type,
            "sections": sections or ["cost", "agents"],
            "created_at": now,
            "updated_at": now,
        }

        await redis.set(f"{_REPORT_KEY_PREFIX}{report_id}", json.dumps(report))
        await redis.sadd(_REPORT_INDEX_KEY, report_id)

        logger.info("Created saved report %s: %s", report_id, name)
        return report

    async def list_reports(self) -> List[Dict[str, Any]]:
        """Return all saved reports."""
        redis = await self._get_redis()
        report_ids = await redis.smembers(_REPORT_INDEX_KEY)
        if not report_ids:
            return []

        reports = []
        for rid in sorted(report_ids):
            rid_str = rid if isinstance(rid, str) else rid.decode()
            data = await redis.get(f"{_REPORT_KEY_PREFIX}{rid_str}")
            if data:
                raw = data if isinstance(data, str) else data.decode()
                reports.append(json.loads(raw))
        return reports

    async def get_report(self, report_id: str) -> Dict[str, Any] | None:
        """Get a single saved report by ID."""
        redis = await self._get_redis()
        data = await redis.get(f"{_REPORT_KEY_PREFIX}{report_id}")
        if data is None:
            return None
        raw = data if isinstance(data, str) else data.decode()
        return json.loads(raw)

    async def update_report(
        self,
        report_id: str,
        name: str,
        report_type: str = "executive",
        sections: List[str] | None = None,
    ) -> Dict[str, Any] | None:
        """Update an existing saved report. Returns None if not found."""
        redis = await self._get_redis()
        existing = await self.get_report(report_id)
        if existing is None:
            return None

        existing["name"] = name
        existing["report_type"] = report_type
        existing["sections"] = sections or existing.get("sections", ["cost", "agents"])
        existing["updated_at"] = utc_timestamp()

        await redis.set(f"{_REPORT_KEY_PREFIX}{report_id}", json.dumps(existing))
        logger.info("Updated saved report %s: %s", report_id, name)
        return existing

    async def delete_report(self, report_id: str) -> bool:
        """Delete a saved report. Returns True if it existed."""
        redis = await self._get_redis()
        deleted = await redis.delete(f"{_REPORT_KEY_PREFIX}{report_id}")
        await redis.srem(_REPORT_INDEX_KEY, report_id)
        if deleted:
            logger.info("Deleted saved report %s", report_id)
        return bool(deleted)

    # ------------------------------------------------------------------
    # Report execution
    # ------------------------------------------------------------------

    async def run_report(self, report_id: str, days: int = 30) -> Dict[str, Any] | None:
        """
        Run a saved report: fetch live analytics for configured sections.

        Returns None if the report doesn't exist.
        """
        report = await self.get_report(report_id)
        if report is None:
            return None

        from services.analytics_service import get_analytics_service

        service = get_analytics_service()
        sections = report.get("sections", [])
        result: Dict[str, Any] = {
            "report_id": report_id,
            "report_name": report["name"],
            "report_type": report["report_type"],
            "days": days,
            "generated_at": utc_timestamp(),
            "data": {},
        }

        if "cost" in sections:
            result["data"]["cost"] = await _fetch_cost_section(service, days)

        if "agents" in sections:
            result["data"]["agents"] = await _fetch_agents_section(service)

        return result


# ------------------------------------------------------------------
# Section data fetchers (module-level helpers)
# ------------------------------------------------------------------


async def _fetch_cost_section(service, days: int) -> Dict[str, Any]:
    """Fetch cost analytics for the given period."""
    try:
        end = now_utc()
        start = end - timedelta(days=days)
        summary = await service.cost.get_cost_summary(start, end)
        return {"summary": summary}
    except Exception as exc:
        logger.warning("Failed to fetch cost section: %s", exc)
        return {"error": str(exc)}


async def _fetch_agents_section(service) -> Dict[str, Any]:
    """Fetch agent performance analytics."""
    try:
        metrics = await service.agents.get_all_agents_metrics()
        return {
            "total_agents": len(metrics),
            "agents": [m.to_dict() for m in metrics],
        }
    except Exception as exc:
        logger.warning("Failed to fetch agents section: %s", exc)
        return {"error": str(exc)}


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------

_instance: SavedReportsService | None = None


def get_saved_reports_service() -> SavedReportsService:
    """Get or create the SavedReportsService singleton."""
    global _instance
    if _instance is None:
        _instance = SavedReportsService()
    return _instance
