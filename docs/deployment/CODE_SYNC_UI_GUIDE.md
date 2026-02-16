# Code Sync UI Guide
## Visual Walkthrough of SLM Code Deployment Interface

> **Access:** https://172.16.168.19/code-sync

---

## UI Overview

The Code Sync page consists of 6 main sections arranged vertically:

```
┌─────────────────────────────────────────────────────────────────────┐
│  [SLM Logo] Code Sync                               [Refresh Button] │
│  Manage agent code versions across the fleet                         │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─── Status Banner ───────────────────────────────────────────┐   │
│  │ Latest: 745e45ee  Last: 2026-02-16  Outdated: 1/9  [⚠ Warn]│   │
│  └──────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─── Sync Progress Banner (when active) ────────────────────┐     │
│  │ 🔄 Sync in Progress                                         │     │
│  │ Phase 2/5: Running npm install...                           │     │
│  └──────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─── Code Source Card ───────────────────────────────────────┐   │
│  │ Code Source                                   [Edit Button]  │   │
│  │ 01-Backend (Main Server)                                    │   │
│  │ /home/kali/Desktop/AutoBot (Dev_new_gui)                    │   │
│  │ Last commit: 745e45ee                      [Remove Button]  │   │
│  └──────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─── Pending Updates Table ──────────────────────────────────┐   │
│  │ [Select All] Outdated Nodes                                 │   │
│  │ ┌────────────────────────────────────────────────────────┐ │   │
│  │ │☐ frontend-01  Frontend  997018a9 → 745e45ee [Sync Now]│ │   │
│  │ │☐ npu-02       NPU       993f2d1a → 745e45ee [Sync Now]│ │   │
│  │ └────────────────────────────────────────────────────────┘ │   │
│  │ [Sync Strategy: Graceful ▼] [✓ Restart After] [Sync Sel.] │   │
│  └──────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─── Role-Based Sync ────────────────────────────────────────┐   │
│  │ frontend    3 nodes   1 outdated        [Sync Role]         │   │
│  │ backend     2 nodes   0 outdated        [Sync Role] (gray)  │   │
│  │ npu         2 nodes   1 outdated        [Sync Role]         │   │
│  └──────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─── Scheduled Updates ──────────────────────────────────────┐   │
│  │ No active schedules                  [Create Schedule]      │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Section 1: Header & Status Banner

### Header Bar

```
┌─────────────────────────────────────────────────────────────────┐
│  Code Sync                                       [🔄 Refresh]   │
│  Manage agent code versions across the fleet                    │
└─────────────────────────────────────────────────────────────────┘
```

- **Title**: "Code Sync" - always visible
- **Description**: Brief explanation of page purpose
- **Refresh Button**:
  - Icon: Spinning arrows (🔄)
  - Text: "Refresh" or "Refreshing..." when loading
  - Action: Fetches latest status from backend
  - Keyboard: No shortcut (click only)

### Status Banner (4 Metrics)

```
┌──────────────────────────────────────────────────────────────────┐
│  Latest Version    Last Fetch          Outdated Nodes    Status  │
│  745e45ee         2026-02-16 20:48      1 / 9        [⚠ Updates] │
│  (12 chars)       (datetime)            (ratio)       (badge)    │
└──────────────────────────────────────────────────────────────────┘
```

**Metric 1: Latest Version**
- Format: 12-character commit hash (e.g., `745e45ee`)
- Hover: Shows full 40-character hash (if available)
- Source: Latest commit from Code Source node
- Updates: When git post-commit hook fires

**Metric 2: Last Fetch**
- Format: `YYYY-MM-DD HH:MM:SS`
- Shows: When SLM last queried fleet node status
- Updates: Every page refresh or manual refresh click

**Metric 3: Outdated Nodes**
- Format: `X / Y` where X = outdated, Y = total
- Color:
  - Gray: 0 outdated (all up to date)
  - Yellow: 1+ outdated (updates available)
- Click: No action (display only)

**Metric 4: Status Badge**
- Two states:
  ```
  [✓ All Up To Date]  ← Green background, when outdated = 0
  [⚠ Updates Available] ← Yellow background, when outdated > 0
  ```

---

## Section 2: Sync Progress Banner

### Inactive State (Hidden)

Banner is not visible when no sync is running.

### Active State (Visible During Sync)

```
┌─────────────────────────────────────────────────────────────────┐
│  🔄 Sync in Progress                                             │
│  Phase 3/5: Running npm run build... (2m 15s elapsed)           │
└─────────────────────────────────────────────────────────────────┘
```

**Layout:**
- Background: Light blue (#EBF8FF)
- Border: Blue (#BEE3F8)
- Icon: Spinning refresh icon (animated)
- Title: "Sync in Progress" (bold)
- Progress: Current stage description + elapsed time

**Stage Messages:**
1. `Phase 1/5: Pulling code from source...`
2. `Phase 2/5: Running npm install...`
3. `Phase 3/5: Running npm run build...` ← Most time here (2-3 min)
4. `Phase 4/5: Deploying build to webroot...`
5. `Phase 5/5: Reloading nginx...`

**On Completion:**
- Banner changes to green: `✓ Node synchronized successfully`
- Auto-dismisses after 3 seconds
- Node removed from Pending Updates table

**On Error:**
- Banner changes to red: `✗ Sync failed: <error message>`
- Does NOT auto-dismiss
- User must click X to close
- Error logged in SLM backend logs

---

## Section 3: Code Source Card

### Configured State

```
┌─────────────────────────────────────────────────────────────────┐
│  Code Source                                       [Edit Button] │
│  ───────────────────────────────────────────────────────────────│
│  01-Backend (Main Server)                                        │
│  /home/kali/Desktop/AutoBot (Dev_new_gui)                        │
│  Last commit: 745e45ee (hover for full hash)                    │
│                                                 [Remove Button]  │
└─────────────────────────────────────────────────────────────────┘
```

**Fields:**
- **Line 1**: Node ID + hostname
- **Line 2**: Repository path + branch name (in parentheses)
- **Line 3**: Last known commit (12-char hash)
  - Hover: Shows full 40-char hash as tooltip
- **Edit Button**: Opens modal to change source/path/branch
- **Remove Button**: Unassigns code source (requires confirmation)

### Unconfigured State

```
┌─────────────────────────────────────────────────────────────────┐
│  Code Source                                  [Configure Button] │
│  ───────────────────────────────────────────────────────────────│
│  No code source configured. Assign a node that has git access   │
│  to the repository.                                              │
└─────────────────────────────────────────────────────────────────┘
```

**Action Required:**
1. Click "Configure" button
2. Modal opens (see Modal section below)
3. Select source node, set path/branch
4. Click "Save"

### Code Source Configuration Modal

```
┌─────────────────────────────────────────────────────────────────┐
│  Configure Code Source                                     [X]   │
│  ═══════════════════════════════════════════════════════════════│
│                                                                  │
│  Source Node *                                                   │
│  ┌────────────────────────────────────────┐                     │
│  │ Select a node...                     ▼ │                     │
│  └────────────────────────────────────────┘                     │
│  Options: 01-Backend (Main), 02-NPU, 03-Redis, etc.             │
│                                                                  │
│  Repository Path *                                               │
│  ┌────────────────────────────────────────┐                     │
│  │ /home/kali/Desktop/AutoBot               │                     │
│  └────────────────────────────────────────┘                     │
│  Must exist on source node and be a git repo                    │
│                                                                  │
│  Branch *                                                        │
│  ┌────────────────────────────────────────┐                     │
│  │ Dev_new_gui                              │                     │
│  └────────────────────────────────────────┘                     │
│  Git branch to track (main, Dev_new_gui, develop, etc.)         │
│                                                                  │
│  ───────────────────────────────────────────────────────────────│
│                                      [Cancel]  [Save]            │
└─────────────────────────────────────────────────────────────────┘
```

**Validation:**
- All fields required (marked with *)
- Path must exist on source node (checked via SSH)
- Branch doesn't need to exist yet (can be created later)

---

## Section 4: Pending Updates Table

### Table with Outdated Nodes

```
┌─────────────────────────────────────────────────────────────────┐
│  [☐ Select All] Outdated Nodes (2)                              │
│  ═══════════════════════════════════════════════════════════════│
│  Node ID      Hostname      Current    Target     Last Sync     │
│  ───────────────────────────────────────────────────────────────│
│  ☐ frontend-01 Frontend VM  997018a9   745e45ee  2 hours ago   │
│                                               [Sync Now] Button  │
│  ───────────────────────────────────────────────────────────────│
│  ☐ npu-02      NPU Worker   993f2d1a   745e45ee  3 days ago    │
│                                               [Sync Now] Button  │
│  ───────────────────────────────────────────────────────────────│
│                                                                  │
│  Sync Options:                                                   │
│  [Sync Strategy: Graceful ▼]  [✓ Restart After Sync]            │
│  [Sync Selected (2)] [Sync All Outdated]                        │
└─────────────────────────────────────────────────────────────────┘
```

**Column Descriptions:**
1. **Checkbox**: Select for batch sync
2. **Node ID**: Unique identifier (e.g., `frontend-01`)
3. **Hostname**: Human-readable name
4. **Current**: Commit hash on node (outdated)
5. **Target**: Latest commit hash (from Code Source)
6. **Last Sync**: Relative time (e.g., "2 hours ago", "3 days ago")
7. **Actions**: Individual "Sync Now" button per row

**Select All Checkbox:**
- ☐ Unchecked: No nodes selected
- ☑ Checked: All nodes selected
- ⊟ Indeterminate: Some nodes selected

**Sync Options (Bottom Controls):**

1. **Sync Strategy Dropdown**:
   ```
   [Sync Strategy: Graceful ▼]
   │
   ├─ Immediate  ← Sync ASAP, may cause downtime
   ├─ Graceful   ← Wait for idle, default
   └─ Manual     ← Sync only, don't restart
   ```

2. **Restart After Sync Checkbox**:
   - ✓ Checked: Services reload after build (recommended)
   - ☐ Unchecked: Build only, no service restart

3. **Batch Action Buttons**:
   - `[Sync Selected (X)]` - Disabled if none selected
   - `[Sync All Outdated]` - Syncs all nodes in table

### Empty State (No Outdated Nodes)

```
┌─────────────────────────────────────────────────────────────────┐
│  Outdated Nodes (0)                                              │
│  ═══════════════════════════════════════════════════════════════│
│                                                                  │
│  ✓ All nodes are up to date!                                    │
│                                                                  │
│  Latest version: 745e45ee                                        │
│  Last checked: 2026-02-16 20:48:32                               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Section 5: Role-Based Sync

```
┌─────────────────────────────────────────────────────────────────┐
│  Quick Actions - Sync by Role                                    │
│  ═══════════════════════════════════════════════════════════════│
│                                                                  │
│  Role        Total Nodes   Outdated   Action                    │
│  ───────────────────────────────────────────────────────────────│
│  frontend    3             1          [Sync frontend Role]      │
│  backend     2             0          [Sync backend Role] (gray)│
│  npu         2             1          [Sync npu Role]           │
│  browser     1             0          [Sync browser Role] (gray)│
│  redis       1             0          [Sync redis Role] (gray)  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Button States:**
- **Blue/Enabled**: Role has outdated nodes (clickable)
- **Gray/Disabled**: All nodes in role up to date
- **Loading**: Shows spinner when sync in progress

**Click Behavior:**
1. Click "Sync [role] Role"
2. Confirmation dialog: "Sync X [role] nodes?"
3. Batch sync starts (rolling deployment)
4. Progress shown in main progress banner
5. All role nodes sync one-by-one or in parallel (based on strategy)

---

## Section 6: Scheduled Updates (Optional)

```
┌─────────────────────────────────────────────────────────────────┐
│  Scheduled Updates                           [Create Schedule]  │
│  ═══════════════════════════════════════════════════════════════│
│                                                                  │
│  Name         Schedule       Target       Status     Actions    │
│  ───────────────────────────────────────────────────────────────│
│  Nightly      Daily 2 AM     frontend     Enabled    [Edit]     │
│  Weekly       Sunday 3 AM    all          Disabled   [Edit]     │
│  ───────────────────────────────────────────────────────────────│
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Features:**
- Automate periodic syncs (daily, weekly, monthly)
- Use cron expressions for flexible scheduling
- Target specific roles or all nodes
- Enable/disable without deleting

---

## User Interactions

### Syncing a Single Node (Most Common)

**Step-by-Step UI Flow:**

1. **Initial View** - See outdated node in table
   ```
   ☐ frontend-01  Frontend  997018a9 → 745e45ee  [Sync Now]
   ```

2. **Click "Sync Now"** - Button becomes disabled
   ```
   ☐ frontend-01  Frontend  997018a9 → 745e45ee  [⏳ Syncing...]
   ```

3. **Progress Banner Appears** (top of page)
   ```
   🔄 Sync in Progress
   Phase 1/5: Pulling code from source...
   ```

4. **Progress Updates** (every 5-10 seconds)
   ```
   🔄 Sync in Progress
   Phase 2/5: Running npm install... (45s elapsed)
   ```

5. **Build Phase** (longest, 2-3 minutes)
   ```
   🔄 Sync in Progress
   Phase 3/5: Running npm run build... (2m 15s elapsed)
   ```

6. **Success** - Banner turns green
   ```
   ✓ Node synchronized successfully
   ```

7. **Row Removed** - frontend-01 disappears from table

8. **Status Banner Updates**
   ```
   Outdated Nodes: 0 / 9  [✓ All Up To Date]
   ```

### Syncing Multiple Nodes (Batch)

1. **Select Nodes**
   ```
   ☑ frontend-01  [checked]
   ☑ npu-02       [checked]
   ```

2. **Click "Sync Selected (2)"**

3. **Confirmation Dialog**
   ```
   ┌─────────────────────────────────────────┐
   │  Sync 2 Selected Nodes?                 │
   │  ───────────────────────────────────────│
   │  Strategy: Graceful                     │
   │  Restart: Yes                           │
   │  Estimated time: 10-15 minutes          │
   │                                         │
   │           [Cancel]  [Sync]              │
   └─────────────────────────────────────────┘
   ```

4. **Rolling Deployment** - Nodes sync one at a time
   ```
   🔄 Sync Progress: 1/2 nodes complete
   Currently syncing: frontend-01 (Phase 3/5)
   Queued: npu-02
   ```

5. **Completion**
   ```
   ✓ Successfully synced 2 nodes
   Duration: 8 minutes 32 seconds
   ```

---

## Color Coding Reference

| Element | Color | Hex Code | Meaning |
|---------|-------|----------|---------|
| Up to Date Badge | Green | #10B981 | All nodes current |
| Updates Badge | Yellow | #F59E0B | Updates available |
| Sync Progress | Blue | #3B82F6 | Operation in progress |
| Success | Green | #22C55E | Operation succeeded |
| Error | Red | #EF4444 | Operation failed |
| Disabled Button | Gray | #9CA3AF | Action unavailable |

---

## Keyboard Shortcuts

Currently, the UI does not support keyboard shortcuts. All interactions are click-based.

**Future Enhancement (Issue #XXX):**
- `R` - Refresh status
- `S` - Sync selected nodes
- `A` - Toggle select all
- `Esc` - Close modal/dismiss banner

---

## Accessibility Features

**Screen Reader Support:**
- Status banner: Announced as "Status: X outdated nodes"
- Buttons: Labeled with action + target (e.g., "Sync frontend-01 node")
- Progress: Live region announces stage changes

**Keyboard Navigation:**
- Tab order: Top to bottom, left to right
- Enter: Activate buttons
- Space: Toggle checkboxes

**High Contrast Mode:**
- Colors meet WCAG AA standards
- Focus indicators visible on all interactive elements

---

## Mobile Responsive Layout

**Desktop (>1024px):**
- Status banner: 4 columns
- Table: All columns visible
- Role cards: 2 columns

**Tablet (768px - 1024px):**
- Status banner: 2x2 grid
- Table: Scrollable horizontally
- Role cards: 1 column

**Mobile (<768px):**
- Status banner: Stacked (1 column)
- Table: Card layout (no table)
- Role cards: Full width

---

## Performance Notes

**Data Refresh Intervals:**
- Automatic refresh: None (manual only)
- WebSocket updates: Real-time for sync progress
- Typical load time: < 500ms

**Caching:**
- Status: No cache (always fresh)
- Node list: Cached for 30 seconds
- Code source: Cached until modified

---

**Document Version:** 1.0
**Created:** 2026-02-16
**Issue:** #243 (Phase 2 - Code Evolution Dashboard deployment)
**Screenshots:** ASCII art representations (actual UI may vary slightly)
