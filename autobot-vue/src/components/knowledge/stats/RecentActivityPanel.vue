<template>
  <BasePanel variant="bordered" size="medium">
    <h4>Recent Activity</h4>
    <div class="activity-timeline">
      <div v-for="activity in activities" :key="activity.id" class="activity-item">
        <div class="activity-icon" :class="activity.type">
          <i :class="getActivityIcon(activity.type)"></i>
        </div>
        <div class="activity-content">
          <p class="activity-description">{{ activity.description }}</p>
          <p class="activity-time">{{ formatTimeAgo(activity.timestamp) }}</p>
        </div>
      </div>
      <EmptyState
        v-if="activities.length === 0"
        icon="fas fa-clock"
        message="No recent activity"
      />
    </div>
  </BasePanel>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Recent Activity Panel Component
 *
 * Displays a timeline of recent knowledge base activities.
 * Extracted from KnowledgeStats.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

import BasePanel from '@/components/base/BasePanel.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import { formatTimeAgo } from '@/utils/formatHelpers'

interface Activity {
  id: string | number
  type: 'created' | 'updated' | 'deleted' | 'imported'
  description: string
  timestamp: Date | string
}

interface Props {
  activities: Activity[]
}

defineProps<Props>()

const getActivityIcon = (type: string): string => {
  const icons: Record<string, string> = {
    created: 'fas fa-plus-circle',
    updated: 'fas fa-edit',
    deleted: 'fas fa-trash',
    imported: 'fas fa-download'
  }
  return icons[type] || 'fas fa-circle'
}
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
h4 {
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin-bottom: var(--spacing-4);
}

.activity-timeline {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
  max-height: 300px;
  overflow-y: auto;
}

.activity-item {
  display: flex;
  gap: var(--spacing-4);
  padding: var(--spacing-3);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
}

.activity-icon {
  width: 2rem;
  height: 2rem;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-on-primary);
  font-size: var(--text-sm);
}

.activity-icon.created { background: var(--color-success); }
.activity-icon.updated { background: var(--color-primary); }
.activity-icon.deleted { background: var(--color-error); }
.activity-icon.imported { background: var(--chart-purple); }

.activity-content { flex: 1; }

.activity-description {
  font-size: var(--text-sm);
  color: var(--text-primary);
  margin-bottom: var(--spacing-1);
}

.activity-time {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}
</style>
