# Activity Tracking Integration

Issue #873 - Activity Tracking Integration Hooks (#608 Phase 5)

## Overview

This module tracks desktop automation activity (noVNC clicks, keyboard
input, screenshots) with user attribution.

**#16466 retired the terminal/file/browser hooks** this README used to
document (`integrations/terminal_tracking.py`, `integrations/file_tracking.py`,
`integrations/browser_tracking.py`, and `knowledge/activity_types.py`).
#873's own acceptance checklist for those three was never completed after
the issue was closed — none of them ever had a real caller anywhere in the
backend, and their target integration points (`integrations/terminal.py`,
`integrations/file_browser.py`, `autobot-browser-worker/automation_handler.py`)
were never built. Only the desktop path was ever actually wired.

The `terminal_activities`, `file_activities`, `browser_activities`, and
`secret_usage` database tables still exist (ported into the canonical
Alembic chain by #16464, for an unrelated cascade-delete-safety reason)
but currently receive no rows — see
`autobot_shared/store_authority.py`'s `activity_audit_trail` entry.

## Architecture

```
┌─────────────────────────────────┐
│ noVNC (api/vnc_proxy.py)        │
└────────────────┬─────────────────┘
                 │
    ┌────────────▼────────────┐
    │ integrations/            │
    │ desktop_tracking.py      │
    └────────────┬────────────┘
                 │
    ┌────────────▼────────────┐
    │ utils/activity_tracker.py │
    │ - track_desktop_activity │
    └────────────┬────────────┘
                 │
    ┌────────────▼────────────┐
    │ DesktopActivityModel     │
    │ (desktop_activities)     │
    └─────────────────────────┘
```

## Usage Example

```python
from integrations.desktop_tracking import track_mouse_click

async def handle_vnc_click(user_id, x, y, window_title=None):
    # Process VNC click...
    await vnc_client.click(x, y)

    # Track activity
    async with get_db_session() as db:
        activity_id = await track_mouse_click(
            db=db,
            user_id=user_id,
            x=x,
            y=y,
            window_title=window_title,
        )

    return {"clicked": True}
```

## Database Schema

**`desktop_activities`**
- `id`, `user_id`, `session_id`
- `action` (click, type, move, screenshot, window_focus)
- `coordinates` (tuple)
- `window_title` (string)
- `input_text` (text)
- `screenshot_path` (string)
- `metadata`, `timestamp`

## Testing

```bash
pytest autobot-backend/utils/activity_tracker_test.py -v
pytest autobot-backend/integrations/desktop_tracking_test.py -v
```

## Security & Privacy

- **User attribution**: All activities linked to authenticated users
- **Access control**: Activity records respect user/org/team boundaries
- **Sensitive data**: Passwords and tokens are NOT stored in plain text

## Related Issues

- #871 - Activity Entity Types (dependency)
- #870 - User & Secrets Models (dependency)
- #608 - User-Centric Session Tracking (parent epic)
- #873 - Activity Tracking Integration Hooks (this issue)
- #16464 - ported the tables into the canonical Alembic chain
- #16466 - retired the terminal/file/browser hooks as dead code
