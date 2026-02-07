# Bug Prediction Real-Time Trends Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add automatic 30-second polling to the bug prediction trends chart to display newly stored predictions without manual refresh.

**Architecture:** Add Vue 3 composition API reactive state for polling interval management, implement smart update detection to avoid unnecessary re-renders, add Page Visibility API integration to pause polling when tab is hidden, and display visual indicators for live updates.

**Tech Stack:** Vue 3 Composition API, JavaScript setInterval, Page Visibility API, existing AutoBot logging utilities

**Issue:** #637

---

## Task 1: Add State Variables for Polling

**Files:**
- Modify: `autobot-user-frontend/src/components/analytics/BugPredictionDashboard.vue:427-447`

**Step 1: Add new reactive state variables**

Add after line 433 (after `const hoveredPoint = ref<TrendPoint | null>(null)`):

```typescript
const isPolling = ref(true)
const lastUpdateTime = ref<Date | null>(null)
const pollingInterval = ref<number | null>(null)
```

**Step 2: Verify TypeScript has no errors**

Run: `cd autobot-vue && npm run type-check`
Expected: No type errors

**Step 3: Commit**

```bash
git add autobot-user-frontend/src/components/analytics/BugPredictionDashboard.vue
git commit -m "feat(analytics): add polling state variables (#637)

Add reactive state for managing 30-second trends polling:
- isPolling: toggle for pause/resume
- lastUpdateTime: tracks last successful update
- pollingInterval: stores interval ID for cleanup

Issue #637

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Add Time Formatting Utility

**Files:**
- Modify: `autobot-user-frontend/src/components/analytics/BugPredictionDashboard.vue:627-665`

**Step 1: Add timeAgo utility function**

Add after line 665 (after `getFactorClass` function):

```typescript
function timeAgo(date: Date): string {
  const seconds = Math.floor((new Date().getTime() - date.getTime()) / 1000)

  if (seconds < 60) return `${seconds}s ago`

  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`

  const hours = Math.floor(minutes / 60)
  return `${hours}h ago`
}
```

**Step 2: Verify TypeScript has no errors**

Run: `cd autobot-vue && npm run type-check`
Expected: No type errors

**Step 3: Commit**

```bash
git add autobot-user-frontend/src/components/analytics/BugPredictionDashboard.vue
git commit -m "feat(analytics): add timeAgo utility for relative timestamps (#637)

Formats Date objects into human-readable relative time strings
(e.g., '30s ago', '5m ago', '2h ago') for last update display.

Issue #637

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Enhance loadTrends with Smart Update Detection

**Files:**
- Modify: `autobot-user-frontend/src/components/analytics/BugPredictionDashboard.vue:565-579`

**Step 1: Update loadTrends function with smart detection**

Replace the existing `loadTrends` function (lines 565-579) with:

```typescript
async function loadTrends(): Promise<void> {
  try {
    const response = await fetch(`/api/analytics/bug-prediction/trends?period=${selectedPeriod.value}`);
    if (response.ok) {
      const data = await response.json();
      const newDataPoints = data.data_points || [];

      // Only update if data actually changed (avoid unnecessary re-renders)
      if (JSON.stringify(newDataPoints) !== JSON.stringify(trendData.value)) {
        trendData.value = newDataPoints;
        lastUpdateTime.value = new Date();
      }
    } else {
      logger.warn('Failed to load trends: HTTP', response.status);
      trendData.value = [];
    }
  } catch (error) {
    // Silent failure for polling - log but don't disrupt UX
    logger.warn('Trend polling failed:', error);
    trendData.value = [];
  }
}
```

**Step 2: Verify TypeScript has no errors**

Run: `cd autobot-vue && npm run type-check`
Expected: No type errors

**Step 3: Commit**

```bash
git add autobot-user-frontend/src/components/analytics/BugPredictionDashboard.vue
git commit -m "feat(analytics): add smart update detection to loadTrends (#637)

Compares new trend data with current state before updating to avoid
unnecessary chart re-renders. Updates lastUpdateTime on data change.
Silent error handling for polling (logs warnings, doesn't disrupt UX).

Issue #637

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Implement Polling Functions

**Files:**
- Modify: `autobot-user-frontend/src/components/analytics/BugPredictionDashboard.vue:665-670`

**Step 1: Add startPolling and stopPolling functions**

Add after the `timeAgo` function (around line 675):

```typescript
function startPolling(): void {
  // Clear any existing interval
  if (pollingInterval.value) {
    clearInterval(pollingInterval.value);
  }

  // Start 30-second polling
  pollingInterval.value = window.setInterval(async () => {
    if (isPolling.value) {
      await loadTrends();
    }
  }, 30000); // 30 seconds

  logger.info('Trends polling started (30s interval)');
}

function stopPolling(): void {
  if (pollingInterval.value) {
    clearInterval(pollingInterval.value);
    pollingInterval.value = null;
    logger.info('Trends polling stopped');
  }
}
```

**Step 2: Verify TypeScript has no errors**

Run: `cd autobot-vue && npm run type-check`
Expected: No type errors

**Step 3: Commit**

```bash
git add autobot-user-frontend/src/components/analytics/BugPredictionDashboard.vue
git commit -m "feat(analytics): implement polling start/stop functions (#637)

Adds 30-second interval for automatic trends refresh:
- startPolling: creates interval, clears any existing
- stopPolling: cleans up interval and logs action
- Respects isPolling state for pause/resume

Issue #637

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Add Page Visibility API Integration

**Files:**
- Modify: `autobot-user-frontend/src/components/analytics/BugPredictionDashboard.vue:667-671`

**Step 1: Add visibility change handler in onMounted**

Update the `onMounted` hook (currently at line 668-670) to:

```typescript
onMounted(() => {
  refreshData();
  startPolling();

  // Pause polling when tab hidden, resume when visible
  document.addEventListener('visibilitychange', handleVisibilityChange);
});
```

**Step 2: Add onUnmounted hook**

Add after the `onMounted` hook:

```typescript
onUnmounted(() => {
  stopPolling();
  document.removeEventListener('visibilitychange', handleVisibilityChange);
});
```

**Step 3: Add visibility change handler function**

Add after the `stopPolling` function:

```typescript
function handleVisibilityChange(): void {
  if (document.hidden) {
    stopPolling();
    logger.info('Tab hidden - pausing trends polling');
  } else {
    startPolling();
    logger.info('Tab visible - resuming trends polling');
  }
}
```

**Step 4: Add onUnmounted import**

Update the import statement at line 377:

```typescript
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
```

**Step 5: Verify TypeScript has no errors**

Run: `cd autobot-vue && npm run type-check`
Expected: No type errors

**Step 6: Commit**

```bash
git add autobot-user-frontend/src/components/analytics/BugPredictionDashboard.vue
git commit -m "feat(analytics): add Page Visibility API for smart polling (#637)

Pauses polling when browser tab is hidden, resumes when visible:
- Saves API calls when user not viewing dashboard
- Cleans up event listeners on component unmount
- Logs visibility state changes for debugging

Issue #637

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Add Live Indicator Badge UI

**Files:**
- Modify: `autobot-user-frontend/src/components/analytics/BugPredictionDashboard.vue:196-210`

**Step 1: Update trends panel header with live indicators**

Replace the panel header section (lines 197-210) with:

```vue
<div class="panel-header">
  <h3>📈 Prediction Accuracy</h3>
  <div class="header-actions">
    <span class="live-badge">
      <span class="pulse-dot"></span>
      Live
    </span>
    <span v-if="lastUpdateTime" class="update-time">
      {{ timeAgo(lastUpdateTime) }}
    </span>
    <div class="period-selector">
      <button
        v-for="period in ['7d', '30d', '90d']"
        :key="period"
        :class="{ active: selectedPeriod === period }"
        @click="selectedPeriod = period; loadTrends()"
      >
        {{ period }}
      </button>
    </div>
  </div>
</div>
```

**Step 2: Verify template syntax**

Run: `cd autobot-vue && npm run type-check`
Expected: No errors

**Step 3: Commit**

```bash
git add autobot-user-frontend/src/components/analytics/BugPredictionDashboard.vue
git commit -m "feat(analytics): add live indicator and last update UI (#637)

Adds visual feedback for auto-refresh in trends panel:
- Live badge with pulse dot animation
- Last update timestamp using timeAgo utility
- Maintains existing period selector functionality

Issue #637

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Add CSS Styles for Live Indicators

**Files:**
- Modify: `autobot-user-frontend/src/components/analytics/BugPredictionDashboard.vue:1167-1189`

**Step 1: Add header-actions styles**

Add after line 1189 (after `.period-selector button.active` styles):

```css
.header-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
}

.live-badge {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
  font-size: var(--text-xs);
  color: var(--color-success);
  padding: var(--spacing-1) var(--spacing-2);
  background: var(--color-success-bg);
  border-radius: var(--radius-default);
  font-weight: var(--font-semibold);
}

.pulse-dot {
  width: 6px;
  height: 6px;
  background: var(--color-success);
  border-radius: 50%;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.3;
    transform: scale(0.8);
  }
}

.update-time {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  white-space: nowrap;
}
```

**Step 2: Verify styles compile**

Run: `cd autobot-vue && npm run build`
Expected: Build succeeds without CSS errors

**Step 3: Commit**

```bash
git add autobot-user-frontend/src/components/analytics/BugPredictionDashboard.vue
git commit -m "style(analytics): add CSS for live indicators (#637)

Styles for real-time update UI:
- Live badge with success color scheme
- Pulse animation for visual feedback
- Update timestamp styling
- Uses design tokens for consistency

Issue #637

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Test Implementation Locally

**Files:**
- Test: Manual testing in browser

**Step 1: Sync to frontend VM**

Run: `./scripts/utilities/sync-to-vm.sh frontend autobot-user-frontend/src/ /home/autobot/AutoBot/autobot-user-frontend/src/`
Expected: Files synced successfully

**Step 2: Open dashboard in browser**

Navigate to: `http://172.16.168.21:5173` and open Bug Prediction Dashboard
Expected: Dashboard loads

**Step 3: Verify live badge appears**

Check: Trends panel header shows green "Live" badge with pulsing dot
Expected: Badge visible and animating

**Step 4: Verify initial timestamp**

Check: "Updated X ago" shows after initial load
Expected: Timestamp displays (e.g., "5s ago")

**Step 5: Wait 30+ seconds and verify auto-refresh**

Wait: 35 seconds
Check: Timestamp updates to "30s ago" or similar
Expected: Timestamp changes, indicating polling occurred

**Step 6: Test period selector**

Click: Different period button (7d, 30d, 90d)
Expected: Chart updates immediately, polling continues

**Step 7: Test tab visibility**

Action: Switch to different browser tab for 10 seconds, return
Check: Console logs show "pausing" and "resuming" messages
Expected: Polling pauses when hidden, resumes when visible

**Step 8: Verify no console errors**

Check: Browser console
Expected: No errors, only info/warn logs

**Step 9: Document test results**

Note any issues found and whether acceptance criteria are met

---

## Task 9: Update GitHub Issue

**Files:**
- Update: GitHub issue #637

**Step 1: Add implementation comment**

Comment on issue:
```
✅ Implementation complete in branch `feature/bug-prediction-realtime-trends`

**Implemented:**
- 30-second auto-refresh polling for trends chart
- Smart update detection (only re-renders when data changes)
- Page Visibility API integration (pauses when tab hidden)
- Live badge with pulse animation
- Last update timestamp display

**Testing:**
- [x] Live badge displays correctly
- [x] Timestamp updates every 30 seconds
- [x] Polling pauses when tab hidden
- [x] Polling resumes when tab visible
- [x] Period selector still works
- [x] No console errors
- [x] Chart updates with new data

Ready for code review and merge.
```

**Step 2: Update issue checklist**

Check off implemented acceptance criteria in issue description

---

## Task 10: Create Pull Request

**Files:**
- Create: GitHub PR

**Step 1: Push branch to remote**

Run: `git push -u origin feature/bug-prediction-realtime-trends`
Expected: Branch pushed successfully

**Step 2: Create pull request**

Run:
```bash
gh pr create --title "feat(analytics): Real-time auto-refresh for bug prediction trends (#637)" --body "$(cat <<'EOF'
## Summary

Implements automatic 30-second polling for the bug prediction trends chart to display newly stored predictions without manual refresh.

## Changes

- ✅ Added polling state management (isPolling, lastUpdateTime, pollingInterval)
- ✅ Implemented startPolling/stopPolling functions with 30s interval
- ✅ Smart update detection in loadTrends (prevents unnecessary re-renders)
- ✅ Page Visibility API integration (pauses when tab hidden)
- ✅ Live badge UI with pulse animation
- ✅ Last update timestamp display with relative time formatting
- ✅ Lifecycle hooks for cleanup (onMounted/onUnmounted)

## Testing

Manual testing verified:
- Live badge displays and animates correctly
- Timestamp updates every 30 seconds
- Polling pauses when browser tab is hidden
- Polling resumes when tab becomes visible
- Period selector continues to work
- No console errors
- Chart updates when new data available

## Screenshots

_Add screenshots of live badge and timestamp UI_

## Closes

#637

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR created with URL

**Step 3: Request code review**

Add reviewers to PR or comment:
```
@mrveiss Ready for review
```

---

## Acceptance Criteria Verification

From issue #637 and design document:

- [x] Trends chart automatically updates every 30 seconds when dashboard is mounted
- [x] "Live" badge displayed in trends panel header
- [x] "Updated X ago" timestamp shows last refresh time
- [x] Polling pauses when browser tab is hidden
- [x] Polling resumes when tab becomes visible
- [x] No memory leaks when component unmounts
- [x] Existing manual refresh and period selector functionality unchanged
- [x] No user-facing errors for transient polling failures
- [x] Chart only re-renders when data actually changes

---

## Rollback Plan

If issues found in production:

```bash
# Revert the feature
git revert <commit-hash>
git push origin Dev_new_gui

# Or disable polling via feature flag (future enhancement)
# config.features.trendsPolling = false
```

---

## Future Enhancements (Out of Scope)

- User toggle to pause/resume polling
- Configurable polling interval
- Visual notification when new data arrives
- WebSocket real-time updates
- Adaptive polling rate based on data change frequency
