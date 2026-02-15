# Activity Tracking Integration

Issue #873 - Activity Tracking Integration Hooks (#608 Phase 5)

## Overview

This module provides integration hooks for tracking user activities across all UI components in AutoBot. It enables comprehensive activity monitoring, secret usage auditing, and user attribution for terminal, file browser, browser automation, and desktop interactions.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ UI Components (Terminal, File Browser, Browser, noVNC) │
└────────────────────┬────────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        │ Integration Modules     │
        │ - terminal_tracking.py  │
        │ - file_tracking.py      │
        │ - browser_tracking.py   │
        │ - desktop_tracking.py   │
        └────────────┬────────────┘
                     │
        ┌────────────▼────────────┐
        │ utils/activity_tracker.py│
        │ - Secret detection      │
        │ - Activity recording    │
        │ - Audit trail           │
        └────────────┬────────────┘
                     │
        ┌────────────▼────────────┐
        │ Database Models         │
        │ - TerminalActivityModel │
        │ - FileActivityModel     │
        │ - BrowserActivityModel  │
        │ - DesktopActivityModel  │
        │ - SecretUsageModel      │
        └─────────────────────────┘
```

## Components

### Core Utility

**`utils/activity_tracker.py`**
- Centralized activity tracking utility
- Secret usage detection (pattern-based + known secrets)
- Async, non-blocking database operations
- Automatic secret usage audit trail creation

### Integration Hooks

**`integrations/terminal_tracking.py`**
- Track command execution with user attribution
- Detect secret usage in commands (passwords, tokens, API keys)
- PTY session lifecycle tracking
- Shell type and working directory recording

**`integrations/file_tracking.py`**
- Track file CRUD operations (create, read, update, delete, rename, move)
- File upload/download tracking
- File type and size recording
- Path traversal and operation auditing

**`integrations/browser_tracking.py`**
- Track browser navigation and interactions
- Form submission with secret usage detection
- Element click and scroll tracking
- HTTP status code and redirect recording

**`integrations/desktop_tracking.py`**
- Track mouse clicks and movements
- Keyboard input recording
- Screenshot capture tracking
- Window focus and application tracking

## Usage Examples

### Terminal Activity

```python
from integrations.terminal_tracking import track_command_execution
from database import get_db_session

async def execute_command_handler(user_id, command, session_id=None):
    # Execute command...
    result = await run_command(command)

    # Track activity
    async with get_db_session() as db:
        activity_id = await track_command_execution(
            db=db,
            user_id=user_id,
            command=command,
            session_id=session_id,
            working_directory=os.getcwd(),
            exit_code=result.exit_code,
            output=result.output,
            shell_type="bash"
        )

    return result
```

### File Operation

```python
from integrations.file_tracking import track_file_operation

async def upload_file_handler(user_id, file_path, size, session_id=None):
    # Save file...
    await save_uploaded_file(file_path, data)

    # Track activity
    async with get_db_session() as db:
        activity_id = await track_file_operation(
            db=db,
            user_id=user_id,
            operation="create",
            path=file_path,
            session_id=session_id,
            size_bytes=size,
        )

    return {"success": True}
```

### Browser Action

```python
from integrations.browser_tracking import track_form_submission

async def browser_submit_form(user_id, url, form_selector, secrets_used=None):
    # Submit form via Playwright...
    await page.locator(form_selector).submit()

    # Track activity
    async with get_db_session() as db:
        activity_id = await track_form_submission(
            db=db,
            user_id=user_id,
            url=url,
            form_selector=form_selector,
            secrets_used=secrets_used,
        )

    return {"submitted": True}
```

### Desktop Action

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

## Secret Usage Detection

The activity tracker automatically detects potential secret usage in commands and browser inputs using pattern matching:

**Detected Patterns:**
- `--password=<value>` or `-p <value>`
- `export PASSWORD=<value>` (and TOKEN, KEY, SECRET)
- `api_key=<value>` or `token=<value>`

When secrets are detected or explicitly provided:
1. Activity record includes `secrets_used` array
2. Separate `SecretUsageModel` record created for audit trail
3. Linked to activity via `activity_id` and `activity_type`

## Database Schema

### Activity Tables

**`terminal_activities`**
- `id` (UUID, primary key)
- `user_id` (UUID, foreign key to users)
- `session_id` (string, optional chat session)
- `command` (text)
- `working_directory` (string)
- `exit_code` (integer)
- `output` (text)
- `secrets_used` (UUID array)
- `metadata` (JSONB)
- `timestamp` (datetime)

**`file_activities`**
- `id`, `user_id`, `session_id`
- `operation` (create, read, update, delete, rename, move)
- `path` (string)
- `new_path` (string, for rename/move)
- `file_type` (string)
- `size_bytes` (integer)
- `metadata`, `timestamp`

**`browser_activities`**
- `id`, `user_id`, `session_id`
- `url` (string)
- `action` (navigate, click, type, submit, scroll)
- `selector` (CSS selector)
- `input_value` (text)
- `secrets_used` (UUID array)
- `metadata`, `timestamp`

**`desktop_activities`**
- `id`, `user_id`, `session_id`
- `action` (click, type, move, screenshot, window_focus)
- `coordinates` (tuple)
- `window_title` (string)
- `input_text` (text)
- `screenshot_path` (string)
- `metadata`, `timestamp`

**`secret_usage`**
- `id`, `secret_id`, `user_id`
- `activity_type` (terminal, browser, file, desktop)
- `activity_id` (UUID, references parent activity)
- `session_id` (optional)
- `access_granted` (boolean)
- `denial_reason` (string)
- `metadata`, `timestamp`

## Testing

All integration modules have comprehensive test coverage:

```bash
# Run all activity tracking tests
pytest autobot-user-backend/utils/activity_tracker_test.py -v
pytest autobot-user-backend/integrations/*_tracking_test.py -v

# Run specific integration tests
pytest autobot-user-backend/integrations/terminal_tracking_test.py -v
pytest autobot-user-backend/integrations/file_tracking_test.py -v
pytest autobot-user-backend/integrations/browser_tracking_test.py -v
pytest autobot-user-backend/integrations/desktop_tracking_test.py -v
```

## Integration Checklist

To integrate activity tracking into a new component:

- [ ] Import appropriate tracking module
- [ ] Extract `user_id` from current user context
- [ ] Extract optional `session_id` from chat context
- [ ] Call tracking function with activity details
- [ ] Handle tracking errors gracefully (log but don't block)
- [ ] Add integration tests

## Performance Considerations

- **Async operations**: All tracking is async and non-blocking
- **Fire-and-forget**: Tracking failures don't interrupt main workflow
- **Batching**: Consider batching for high-frequency events
- **Indexing**: Database tables are indexed on `user_id`, `session_id`, `timestamp`

## Security & Privacy

- **User attribution**: All activities linked to authenticated users
- **Secret auditing**: Complete audit trail for secret access
- **Access control**: Activity records respect user/org/team boundaries
- **Sensitive data**: Passwords and tokens are NOT stored in plain text

## Related Issues

- #871 - Activity Entity Types (dependency)
- #870 - User & Secrets Models (dependency)
- #608 - User-Centric Session Tracking (parent epic)
- #873 - Activity Tracking Integration Hooks (this issue)
