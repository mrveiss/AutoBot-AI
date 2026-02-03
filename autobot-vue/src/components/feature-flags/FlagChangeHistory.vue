<template>
  <div class="flag-change-history">
    <div class="section-header">
      <h3><i class="fas fa-history"></i> Change History</h3>
      <p class="description">
        Track all changes to feature flag configuration for audit purposes
      </p>
    </div>

    <!-- Loading State -->
    <div v-if="loading && !history.length" class="loading-state">
      <LoadingSpinner />
    </div>

    <!-- Empty State -->
    <div v-else-if="!history.length" class="empty-state">
      <div class="empty-icon">
        <i class="fas fa-clock"></i>
      </div>
      <h4>No History Available</h4>
      <p>No configuration changes have been recorded yet.</p>
    </div>

    <!-- History Timeline -->
    <div v-else class="history-timeline">
      <div
        v-for="(entry, index) in history"
        :key="index"
        class="timeline-entry"
        :class="entry.mode"
      >
        <div class="timeline-marker">
          <div class="marker-dot" :class="entry.mode">
            <i :class="getModeIcon(entry.mode)"></i>
          </div>
          <div class="marker-line" v-if="index < history.length - 1"></div>
        </div>

        <div class="timeline-content">
          <div class="entry-header">
            <span class="mode-badge" :class="entry.mode">
              {{ getModeLabel(entry.mode) }}
            </span>
            <span class="timestamp">{{ formatTimestamp(entry.timestamp) }}</span>
          </div>

          <div class="entry-details">
            <p class="action-text">{{ getActionText(entry.mode) }}</p>
            <div class="meta-info">
              <span class="changed-by">
                <i class="fas fa-user"></i>
                {{ entry.changed_by || 'System' }}
              </span>
              <span class="relative-time">
                {{ formatRelativeTime(entry.timestamp) }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Legend -->
    <div class="legend" v-if="history.length">
      <span class="legend-title">Mode Legend:</span>
      <div class="legend-items">
        <div class="legend-item">
          <span class="legend-dot disabled"></span>
          <span>Disabled</span>
        </div>
        <div class="legend-item">
          <span class="legend-dot log_only"></span>
          <span>Log Only</span>
        </div>
        <div class="legend-item">
          <span class="legend-dot enforced"></span>
          <span>Enforced</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { EnforcementMode } from '@/utils/FeatureFlagsApiClient';
import LoadingSpinner from '@/components/ui/LoadingSpinner.vue';

interface HistoryEntry {
  timestamp: string;
  mode: EnforcementMode;
  changed_by: string;
}

defineProps<{
  history: HistoryEntry[];
  loading: boolean;
}>();

// Methods
const getModeLabel = (mode: EnforcementMode) => {
  const labels: Record<EnforcementMode, string> = {
    disabled: 'Disabled',
    log_only: 'Log Only',
    enforced: 'Enforced',
  };
  return labels[mode] || mode;
};

const getModeIcon = (mode: EnforcementMode) => {
  const icons: Record<EnforcementMode, string> = {
    disabled: 'fas fa-ban',
    log_only: 'fas fa-clipboard-list',
    enforced: 'fas fa-shield-alt',
  };
  return icons[mode] || 'fas fa-question';
};

const getActionText = (mode: EnforcementMode) => {
  const texts: Record<EnforcementMode, string> = {
    disabled: 'Access control enforcement was disabled',
    log_only: 'Switched to log-only mode for safe testing',
    enforced: 'Full enforcement mode was enabled',
  };
  return texts[mode] || 'Configuration was updated';
};

const formatTimestamp = (timestamp: string) => {
  const date = new Date(timestamp);
  return date.toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
};

const formatRelativeTime = (timestamp: string) => {
  const date = new Date(timestamp);
  const now = new Date();
  const diff = now.getTime() - date.getTime();

  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);

  if (minutes < 1) return 'Just now';
  if (minutes < 60) return `${minutes} minute${minutes > 1 ? 's' : ''} ago`;
  if (hours < 24) return `${hours} hour${hours > 1 ? 's' : ''} ago`;
  if (days < 30) return `${days} day${days > 1 ? 's' : ''} ago`;
  return formatTimestamp(timestamp);
};
</script>

<style scoped>
.flag-change-history {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 24px;
}

.section-header {
  margin-bottom: 24px;
}

.section-header h3 {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 10px;
}

.section-header h3 i {
  color: var(--color-primary);
}

.section-header .description {
  margin: 0;
  font-size: 14px;
  color: var(--text-tertiary);
}

/* Loading & Empty States */
.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
  color: var(--text-tertiary);
}

.empty-icon {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: var(--bg-tertiary);
  color: var(--text-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  margin-bottom: 16px;
}

.empty-state h4 {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.empty-state p {
  margin: 0;
  font-size: 14px;
  color: var(--text-secondary);
}

/* Timeline */
.history-timeline {
  display: flex;
  flex-direction: column;
}

.timeline-entry {
  display: flex;
  gap: 20px;
}

.timeline-marker {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
}

.marker-dot {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  flex-shrink: 0;
}

.marker-dot.disabled {
  background: var(--bg-tertiary);
  color: var(--text-muted);
}

.marker-dot.log_only {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.marker-dot.enforced {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.marker-line {
  width: 2px;
  flex: 1;
  background: var(--border-default);
  margin: 8px 0;
}

.timeline-content {
  flex: 1;
  padding-bottom: 32px;
}

.timeline-entry:last-child .timeline-content {
  padding-bottom: 0;
}

.entry-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.mode-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
}

.mode-badge.disabled {
  background: var(--bg-tertiary);
  color: var(--text-muted);
}

.mode-badge.log_only {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.mode-badge.enforced {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.timestamp {
  font-size: 13px;
  color: var(--text-tertiary);
}

.entry-details {
  padding: 14px;
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: 10px;
}

.action-text {
  margin: 0 0 10px;
  font-size: 14px;
  color: var(--text-primary);
}

.meta-info {
  display: flex;
  gap: 20px;
  font-size: 12px;
  color: var(--text-tertiary);
}

.changed-by {
  display: flex;
  align-items: center;
  gap: 6px;
}

.relative-time {
  color: var(--text-muted);
}

/* Legend */
.legend {
  margin-top: 24px;
  padding-top: 20px;
  border-top: 1px solid var(--border-default);
  display: flex;
  align-items: center;
  gap: 20px;
}

.legend-title {
  font-size: 13px;
  color: var(--text-tertiary);
}

.legend-items {
  display: flex;
  gap: 16px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-secondary);
}

.legend-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
}

.legend-dot.disabled {
  background: var(--text-muted);
}

.legend-dot.log_only {
  background: var(--color-warning);
}

.legend-dot.enforced {
  background: var(--color-success);
}

/* Responsive */
@media (max-width: 600px) {
  .timeline-marker {
    display: none;
  }

  .timeline-entry {
    gap: 0;
  }

  .legend {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }
}
</style>
