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
h4 {
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 1rem;
}

.activity-timeline {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  max-height: 300px;
  overflow-y: auto;
}

.activity-item {
  display: flex;
  gap: 1rem;
  padding: 0.75rem;
  background: #f9fafb;
  border-radius: 0.375rem;
}

.activity-icon {
  width: 2rem;
  height: 2rem;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 0.875rem;
}

.activity-icon.created { background: #10b981; }
.activity-icon.updated { background: #3b82f6; }
.activity-icon.deleted { background: #ef4444; }
.activity-icon.imported { background: #8b5cf6; }

.activity-content { flex: 1; }

.activity-description {
  font-size: 0.875rem;
  color: #374151;
  margin-bottom: 0.25rem;
}

.activity-time {
  font-size: 0.75rem;
  color: #6b7280;
}
</style>
