<template>
  <div class="flag-change-history">
    <div class="section-header">
      <h3><Icon name="history" /> {{ $t('featureFlags.changeHistory.title') }}</h3>
      <p class="description">
        {{ $t('featureFlags.changeHistory.description') }}
      </p>
    </div>

    <!-- Loading State -->
    <div v-if="loading && !history.length" class="loading-state">
      <LoadingSpinner />
    </div>

    <!-- Empty State -->
    <div v-else-if="!history.length" class="empty-state">
      <div class="empty-icon">
        <Icon name="clock" />
      </div>
      <h4>{{ $t('featureFlags.changeHistory.noChanges') }}</h4>
      <p>{{ $t('featureFlags.changeHistory.noChanges') }}</p>
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
            <Icon :name="getModeIcon(entry.mode)" />
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
                <Icon name="user" />
                {{ entry.changed_by || t('featureFlags.changeHistory.system') }}
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
      <span class="legend-title">{{ t('featureFlags.changeHistory.modeLegend') }}</span>
      <div class="legend-items">
        <div class="legend-item">
          <span class="legend-dot disabled"></span>
          <span>{{ t('featureFlags.changeHistory.modeDisabled') }}</span>
        </div>
        <div class="legend-item">
          <span class="legend-dot log_only"></span>
          <span>{{ t('featureFlags.changeHistory.modeLogOnly') }}</span>
        </div>
        <div class="legend-item">
          <span class="legend-dot enforced"></span>
          <span>{{ t('featureFlags.changeHistory.modeEnforced') }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { useI18n } from 'vue-i18n';
import type { EnforcementMode } from '@/utils/FeatureFlagsApiClient';
import LoadingSpinner from '@/components/ui/LoadingSpinner.vue';

const { t } = useI18n();

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
    disabled: t('featureFlags.changeHistory.modeDisabled'),
    log_only: t('featureFlags.changeHistory.modeLogOnly'),
    enforced: t('featureFlags.changeHistory.modeEnforced'),
  };
  return labels[mode] || mode;
};

const getModeIcon = (mode: EnforcementMode) => {
  const icons: Record<EnforcementMode, string> = {
    disabled: 'ban',
    log_only: 'clipboard-list',
    enforced: 'shield-alt',
  };
  return icons[mode] || 'question';
};

const getActionText = (mode: EnforcementMode) => {
  const texts: Record<EnforcementMode, string> = {
    disabled: t('featureFlags.changeHistory.actionDisabled'),
    log_only: t('featureFlags.changeHistory.actionLogOnly'),
    enforced: t('featureFlags.changeHistory.actionEnforced'),
  };
  return texts[mode] || t('featureFlags.changeHistory.actionUpdated');
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

  if (minutes < 1) return t('featureFlags.changeHistory.justNow');
  if (minutes < 60) return t('featureFlags.changeHistory.minutesAgo', { count: minutes });
  if (hours < 24) return t('featureFlags.changeHistory.hoursAgo', { count: hours });
  if (days < 30) return t('featureFlags.changeHistory.daysAgo', { count: days });
  return formatTimestamp(timestamp);
};
</script>

<style scoped>
.flag-change-history {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
  padding: var(--spacing-6);
}

.section-header {
  margin-bottom: var(--spacing-6);
}

.section-header h3 {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-2);
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
}

.section-header h3 i {
  color: var(--color-primary);
}

.section-header .description {
  margin: var(--spacing-0);
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

/* Loading & Empty States */
.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-10);
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
  font-size: var(--text-2xl);
  margin-bottom: var(--spacing-4);
}

.empty-state h4 {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-2);
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
}

.empty-state p {
  margin: var(--spacing-0);
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

/* Timeline */
.history-timeline {
  display: flex;
  flex-direction: column;
}

.timeline-entry {
  display: flex;
  gap: var(--spacing-5);
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
  font-size: var(--text-base);
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
  margin: var(--spacing-2) var(--spacing-0);
}

.timeline-content {
  flex: 1;
  padding-bottom: var(--spacing-8);
}

.timeline-entry:last-child .timeline-content {
  padding-bottom: var(--spacing-0);
}

.entry-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  margin-bottom: var(--spacing-2);
}

.mode-badge {
  display: inline-flex;
  align-items: center;
  padding: var(--spacing-1) var(--spacing-2-5);
  border-radius: var(--radius-default);
  font-size: var(--text-xs);
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
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

.entry-details {
  padding: var(--spacing-3-5);
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
}

.action-text {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-2-5);
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.meta-info {
  display: flex;
  gap: var(--spacing-5);
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.changed-by {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
}

.relative-time {
  color: var(--text-muted);
}

/* Legend */
.legend {
  margin-top: var(--spacing-6);
  padding-top: var(--spacing-5);
  border-top: 1px solid var(--border-default);
  display: flex;
  align-items: center;
  gap: var(--spacing-5);
}

.legend-title {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

.legend-items {
  display: flex;
  gap: var(--spacing-4);
}

.legend-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-xs);
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
    gap: var(--spacing-0);
  }

  .legend {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-3);
  }
}
</style>
