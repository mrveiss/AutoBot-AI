<template>
  <BasePanel variant="bordered" size="medium">
    <template #header>
      <div class="section-header-content">
        <h4>
          <i class="fas fa-lightbulb"></i>
          Performance Optimization Recommendations
        </h4>
        <BaseButton variant="outline" size="sm" @click="$emit('refresh')">
          <i class="fas fa-sync"></i>
          Refresh
        </BaseButton>
      </div>
    </template>

    <div v-if="recommendations.length > 0" class="recommendations-list">
      <div
        v-for="rec in recommendations"
        :key="rec.category + rec.recommendation"
        :class="['recommendation-card', rec.priority]"
      >
        <div class="rec-header">
          <StatusBadge :variant="(getPriorityVariant(rec.priority) as any)" size="small">
            {{ rec.priority }}
          </StatusBadge>
          <span class="category">{{ rec.category.toUpperCase() }}</span>
        </div>
        <div class="rec-content">
          <p class="recommendation">{{ rec.recommendation }}</p>
          <p class="action">
            <strong>Action:</strong> {{ rec.action }}
          </p>
          <p class="expected-improvement">
            <strong>Expected:</strong> {{ rec.expected_improvement }}
          </p>
        </div>
      </div>
    </div>

    <div v-else class="no-recommendations">
      <i class="fas fa-check-circle"></i>
      No optimization recommendations at this time. System performing optimally!
    </div>
  </BasePanel>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Recommendations Panel Component
 *
 * Displays performance optimization recommendations.
 * Extracted from MonitoringDashboard.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

import BasePanel from '@/components/base/BasePanel.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'

interface Recommendation {
  category: string
  priority: 'high' | 'medium' | 'low'
  recommendation: string
  action: string
  expected_improvement: string
}

interface Props {
  recommendations: Recommendation[]
}

interface Emits {
  (e: 'refresh'): void
}

defineProps<Props>()
defineEmits<Emits>()

const getPriorityVariant = (priority: string) => {
  const variantMap: Record<string, string> = {
    'high': 'danger',
    'medium': 'warning',
    'low': 'info'
  }
  return variantMap[priority] || 'secondary'
}
</script>

<style scoped>
.section-header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.section-header-content h4 {
  margin: 0;
  color: #333;
  font-size: 1.2em;
}

.recommendations-list {
  padding: 20px;
}

.recommendation-card {
  border: 1px solid #dee2e6;
  border-radius: 6px;
  padding: 15px;
  margin-bottom: 15px;
  background: #fafafa;
}

.recommendation-card.high { border-left: 4px solid #f44336; }
.recommendation-card.medium { border-left: 4px solid #ff9800; }
.recommendation-card.low { border-left: 4px solid #2196f3; }

.rec-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.category {
  font-size: 0.8em;
  color: #666;
  font-weight: 500;
}

.rec-content p {
  margin: 8px 0;
  font-size: 0.9em;
  line-height: 1.4;
}

.no-recommendations {
  padding: 40px 20px;
  text-align: center;
  color: #4caf50;
}

.no-recommendations i {
  font-size: 2em;
  margin-bottom: 10px;
  display: block;
}
</style>
