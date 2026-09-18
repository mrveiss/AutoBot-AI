# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An operation as the Operations panel reads it (#17017).

``OperationIntegrationManager._convert_operation_to_response`` built an
``OperationResponse`` out of ``LongRunningOperation.to_response_dict()``. The two
shapes had drifted apart (priority an int where a string was required, the progress
fields nested under another name), so every status or list request answered 500 and
the panel never showed an operation. This is the shape
``autobot-frontend/src/types/operations.ts`` declares for ``Operation``.
"""

from typing import Any, Dict

#: Backend states the panel has no word for, mapped to the nearest one it has.
_PANEL_STATUS = {"queued": "pending", "checkpoint_saved": "running", "resuming": "running"}


def _iso(moment) -> "str | None":
    return moment.isoformat() if moment else None


def operation_view(operation) -> Dict[str, Any]:
    """The frontend ``Operation`` for *operation*. Its creator is used for access, not shown."""
    progress, metadata = operation.progress, dict(operation.metadata or {})
    status = operation.status.value
    return {
        "operation_id": operation.operation_id,
        "name": operation.name,
        "description": operation.description,
        "operation_type": operation.operation_type.value,
        "status": _PANEL_STATUS.get(status, status),
        "priority": operation.priority.name.lower(),
        "progress": progress.progress_percent,
        "current_step": progress.current_step,
        "estimated_items": metadata.get("estimated_items", progress.total_items),
        "processed_items": progress.items_processed,
        "created_at": _iso(operation.created_at),
        "started_at": _iso(operation.started_at),
        "completed_at": _iso(operation.completed_at),
        "error_message": operation.error_message,
        "context": {key: value for key, value in metadata.items() if key != "created_by"},
        "checkpoints_count": len(operation.checkpoints),
        "can_resume": bool(operation.checkpoints),
    }
