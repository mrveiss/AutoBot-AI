# Bug Prediction Real-Time Trends Design

**Issue:** #637
**Date:** 2026-02-05
**Author:** mrveiss
**Status:** Approved

## Overview

Implement automatic real-time updates for the bug prediction trends chart in the frontend dashboard. Currently, users must manually refresh or change the period selector to see newly stored prediction data. This enhancement adds polling to automatically fetch and display new trend data every 30 seconds.

## Requirements

### Functional
- Auto-refresh trends chart every 30 seconds when dashboard is mounted
- Display visual indicator showing live updates are active
- Show last update timestamp
- Maintain existing manual refresh and period selector functionality
- Pause polling when browser tab is hidden to conserve resources

### Non-Functional
- Minimal performance impact (only refresh trends endpoint, not entire dashboard)
- No memory leaks from abandoned intervals
- Graceful error handling for transient network issues
- Smart update detection to avoid unnecessary re-renders

## Technical Design

### Component: BugPredictionDashboard.vue

#### New State Variables
```typescript
const isPolling = ref(true)  // Toggle for pause/resume (future enhancement)
const lastUpdateTime = ref<Date | null>(null)
const pollingInterval = ref<number | null>(null)
```

#### Polling Implementation

**Initialization (onMounted)**
```typescript
onMounted(() => {
  refreshData()  // Initial load
  startPolling() // Begin auto-refresh
})
```

**Polling Function**
```typescript
const startPolling = () => {
  pollingInterval.value = setInterval(async () => {
    await loadTrends() // Only refresh trends, not full dashboard
    lastUpdateTime.value = new Date()
  }, 30000) // 30 seconds
}
```

**Cleanup (onUnmounted)**
```typescript
onUnmounted(() => {
  if (pollingInterval.value) {
    clearInterval(pollingInterval.value)
    pollingInterval.value = null
  }
})
```

#### Smart Update Detection

Before updating `trendData.value`, compare incoming data:
```typescript
async function loadTrends(): Promise<void> {
  try {
    const response = await fetch(`/api/analytics/bug-prediction/trends?period=${selectedPeriod.value}`)
    if (response.ok) {
      const data = await response.json()
      const newDataPoints = data.data_points || []

      // Only update if data actually changed
      if (JSON.stringify(newDataPoints) !== JSON.stringify(trendData.value)) {
        trendData.value = newDataPoints
      }
    }
  } catch (error) {
    // Silent failure for polling - log but don't disrupt UX
    logger.warn('Trend polling failed:', error)
  }
}
```

#### Visual Indicators

**Live Badge (in panel-header)**
```html
<div class="panel-header">
  <h3>📈 Prediction Accuracy</h3>
  <div class="header-actions">
    <span class="live-badge">
      <span class="pulse-dot"></span>
      Live
    </span>
    <span v-if="lastUpdateTime" class="update-time">
      Updated {{ timeAgo(lastUpdateTime) }}
    </span>
    <!-- existing period selector -->
  </div>
</div>
```

**Styles**
```css
.live-badge {
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
  font-size: var(--text-xs);
  color: var(--color-success);
  padding: var(--spacing-1) var(--spacing-2);
  background: var(--color-success-bg);
  border-radius: var(--radius-default);
}

.pulse-dot {
  width: 6px;
  height: 6px;
  background: var(--color-success);
  border-radius: 50%;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.update-time {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}
```

### Error Handling

#### Network Failures
- Wrap polling calls in try/catch
- Log warnings to console only (no user-facing errors for polling failures)
- Continue polling even after failures (transient issues shouldn't break auto-refresh)

#### Page Visibility
```typescript
// Pause polling when tab hidden, resume when visible
document.addEventListener('visibilitychange', () => {
  if (document.hidden && pollingInterval.value) {
    clearInterval(pollingInterval.value)
    pollingInterval.value = null
  } else if (!document.hidden && !pollingInterval.value) {
    startPolling()
  }
})
```

#### Period Changes
- When user changes period selector, next poll automatically uses new period
- Existing `watch(selectedPeriod)` ensures immediate update, then polling continues

### Data Flow

```
Component Mount
    ↓
Initial refreshData() - loads all dashboard data
    ↓
startPolling() - begins 30s interval
    ↓
Every 30s:
    ↓
loadTrends() - fetches /api/analytics/bug-prediction/trends
    ↓
Compare with current trendData
    ↓
Update only if changed → Chart re-renders
    ↓
Update lastUpdateTime
    ↓
(repeat)
    ↓
Component Unmount → clearInterval()
```

### Edge Cases

| Scenario | Handling |
|----------|----------|
| Multiple dashboard tabs open | Each polls independently; backend read-only endpoint handles concurrent requests |
| User changes period while polling | Next poll uses new period automatically |
| Network request times out | Silent failure, continue polling |
| Backend returns "no data" | Display gracefully, keep polling |
| Tab hidden for extended period | Polling paused, resumes on tab focus |
| Component re-mounted quickly | Old interval cleared before new one created |

## Testing Strategy

### Manual Testing
1. Open dashboard, verify "Live" badge appears
2. Wait 30 seconds, verify "Updated X ago" timestamp changes
3. Run `/analyze` endpoint, verify chart updates within 30s
4. Change period selector, verify polling continues with new period
5. Hide browser tab, verify polling pauses (check network tab)
6. Show tab again, verify polling resumes
7. Open multiple tabs, verify each polls independently

### Integration Points
- Existing `loadTrends()` function - no changes to signature
- Existing period selector - watch hook maintains compatibility
- Existing manual refresh button - works independently of polling

## Implementation Checklist

- [ ] Add state variables (`isPolling`, `lastUpdateTime`, `pollingInterval`)
- [ ] Implement `startPolling()` function
- [ ] Add `onMounted` hook to start polling
- [ ] Add `onUnmounted` hook to clear interval
- [ ] Implement smart update detection in `loadTrends()`
- [ ] Add Page Visibility API listener
- [ ] Add "Live" badge to panel header
- [ ] Add "Updated X ago" timestamp display
- [ ] Add CSS for live indicator and pulse animation
- [ ] Add `timeAgo()` utility function for relative timestamps
- [ ] Test across all scenarios
- [ ] Update component documentation

## Future Enhancements (Out of Scope)

- Pause/resume toggle button for user control
- Configurable polling interval
- Visual notification when new data arrives (toast or badge)
- WebSocket implementation for true real-time push updates
- Adaptive polling (slower when no changes detected)

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| API rate limiting | Medium | 30s interval is conservative; backend can add rate limits if needed |
| Memory leaks | High | Ensure cleanup in `onUnmounted` and `onBeforeUnmount` |
| Unnecessary re-renders | Low | Smart update detection compares data before updating |
| User confusion about auto-refresh | Low | Clear "Live" badge and timestamp communicate behavior |

## Dependencies

- Existing `/api/analytics/bug-prediction/trends` endpoint
- Vue 3 composition API (`ref`, `onMounted`, `onUnmounted`)
- Page Visibility API (supported in all modern browsers)

## Acceptance Criteria

✅ Trends chart automatically updates every 30 seconds when dashboard is mounted
✅ "Live" badge displayed in trends panel header
✅ "Updated X ago" timestamp shows last refresh time
✅ Polling pauses when browser tab is hidden
✅ Polling resumes when tab becomes visible
✅ No memory leaks when component unmounts
✅ Existing manual refresh and period selector functionality unchanged
✅ No user-facing errors for transient polling failures
✅ Chart only re-renders when data actually changes
