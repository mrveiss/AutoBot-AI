<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  ValidationTestRunner.vue - Run and View Validation Tests
  Provides UI for triggering validation tests (Issue #581)
-->
<template>
  <BasePanel variant="bordered" size="medium">
    <template #header>
      <div class="panel-header-content">
        <h2><i class="fas fa-vial"></i> Validation Tests</h2>
        <span v-if="running" class="running-indicator">
          <i class="fas fa-spinner fa-spin"></i>
          Running...
        </span>
      </div>
    </template>

    <div class="test-runner">
      <!-- Quick Actions -->
      <div class="quick-actions">
        <button
          class="action-btn primary"
          @click="$emit('run-quick')"
          :disabled="running"
          title="Run quick health check"
        >
          <i class="fas fa-bolt"></i>
          Quick Check
        </button>
        <button
          class="action-btn secondary"
          @click="$emit('run-comprehensive')"
          :disabled="running"
          title="Run comprehensive validation"
        >
          <i class="fas fa-tasks"></i>
          Full Validation
        </button>
      </div>

      <!-- Component Selection -->
      <div class="component-tests" v-if="components.length > 0">
        <h3 class="section-title">
          <i class="fas fa-cube"></i>
          Component Validation
        </h3>
        <div class="component-grid">
          <button
            v-for="component in components"
            :key="component"
            class="component-btn"
            @click="$emit('run-component', component)"
            :disabled="running"
          >
            <i :class="getComponentIcon(component)"></i>
            <span>{{ formatComponentName(component) }}</span>
          </button>
        </div>
      </div>

      <!-- Last Results -->
      <div class="last-results" v-if="lastResults">
        <h3 class="section-title">
          <i class="fas fa-clipboard-check"></i>
          Last Validation Results
        </h3>

        <div class="results-summary">
          <div class="result-stat">
            <span class="stat-label">Status</span>
            <span :class="['stat-value', `status-${lastResults.status}`]">
              {{ lastResults.status }}
            </span>
          </div>
          <div class="result-stat">
            <span class="stat-label">Score</span>
            <span class="stat-value">{{ lastResults.overall_score.toFixed(1) }}%</span>
          </div>
          <div class="result-stat">
            <span class="stat-label">Duration</span>
            <span class="stat-value">{{ lastResults.execution_time.toFixed(2) }}s</span>
          </div>
          <div class="result-stat">
            <span class="stat-label">Time</span>
            <span class="stat-value">{{ formatTimestamp(lastResults.timestamp) }}</span>
          </div>
        </div>

        <!-- Component Scores -->
        <div class="component-scores" v-if="lastResults.component_scores">
          <h4>Component Scores</h4>
          <div class="scores-list">
            <div
              v-for="(score, name) in lastResults.component_scores"
              :key="name"
              class="score-item"
            >
              <span class="score-name">{{ formatComponentName(String(name)) }}</span>
              <div class="score-bar-container">
                <div
                  class="score-bar"
                  :style="{ width: `${score}%` }"
                  :class="getScoreClass(score)"
                ></div>
              </div>
              <span class="score-value">{{ score.toFixed(0) }}%</span>
            </div>
          </div>
        </div>

        <!-- Recommendations from results -->
        <div class="result-recommendations" v-if="lastResults.recommendations && lastResults.recommendations.length">
          <h4>
            <i class="fas fa-lightbulb"></i>
            Recommendations
          </h4>
          <ul class="recommendations-list">
            <li v-for="(rec, index) in lastResults.recommendations" :key="index">
              {{ rec }}
            </li>
          </ul>
        </div>
      </div>

      <!-- No Results State -->
      <div v-else class="no-results">
        <i class="fas fa-clipboard-list"></i>
        <p>No validation results yet</p>
        <span>Run a validation test to see results</span>
      </div>
    </div>
  </BasePanel>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import BasePanel from '@/components/base/BasePanel.vue'

interface ValidationResult {
  validation_id: string
  status: string
  overall_score: number
  component_scores: Record<string, number>
  recommendations: string[]
  test_results: Record<string, unknown>
  execution_time: number
  timestamp: string
}

interface Props {
  components: string[]
  lastResults: ValidationResult | null
  running?: boolean
}

defineProps<Props>()

defineEmits<{
  (e: 'run-quick'): void
  (e: 'run-comprehensive'): void
  (e: 'run-component', component: string): void
}>()

const getComponentIcon = (component: string): string => {
  const iconMap: Record<string, string> = {
    cache: 'fas fa-database',
    caching: 'fas fa-database',
    search: 'fas fa-search',
    hybrid_search: 'fas fa-search-plus',
    monitoring: 'fas fa-chart-line',
    model: 'fas fa-brain',
    model_optimization: 'fas fa-bolt',
    integration: 'fas fa-puzzle-piece',
    comprehensive: 'fas fa-tasks',
    quick: 'fas fa-bolt'
  }
  return iconMap[component.toLowerCase()] || 'fas fa-cube'
}

const formatComponentName = (name: string): string => {
  return name
    .replace(/_/g, ' ')
    .replace(/\b\w/g, l => l.toUpperCase())
}

const formatTimestamp = (timestamp: string): string => {
  if (!timestamp) return 'N/A'
  try {
    return new Date(timestamp).toLocaleString()
  } catch {
    return timestamp
  }
}

const getScoreClass = (score: number): string => {
  if (score >= 90) return 'excellent'
  if (score >= 70) return 'good'
  if (score >= 50) return 'warning'
  return 'critical'
}
</script>

<style scoped>
.panel-header-content {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  width: 100%;
}

.panel-header-content h2 {
  margin: 0;
  font-size: var(--text-lg);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.panel-header-content h2 i {
  color: var(--color-primary);
}

.running-indicator {
  margin-left: auto;
  font-size: var(--text-sm);
  color: var(--color-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

/* Test Runner Container */
.test-runner {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-5);
}

/* Quick Actions */
.quick-actions {
  display: flex;
  gap: var(--spacing-3);
}

.action-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
  padding: var(--spacing-3) var(--spacing-4);
  border: none;
  border-radius: var(--radius-md);
  font-weight: var(--font-semibold);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: all var(--duration-150) var(--ease-in-out);
}

.action-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.action-btn.primary {
  background: var(--color-primary);
  color: white;
}

.action-btn.primary:hover:not(:disabled) {
  background: var(--color-primary-dark);
}

.action-btn.secondary {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
}

.action-btn.secondary:hover:not(:disabled) {
  background: var(--bg-hover);
}

/* Section Titles */
.section-title {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--text-secondary);
  margin: 0 0 var(--spacing-3) 0;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.section-title i {
  color: var(--color-primary);
}

/* Component Grid */
.component-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: var(--spacing-2);
}

.component-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-1);
  padding: var(--spacing-3);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--duration-150) var(--ease-in-out);
}

.component-btn:hover:not(:disabled) {
  background: var(--bg-hover);
  border-color: var(--color-primary);
}

.component-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.component-btn i {
  font-size: var(--text-lg);
  color: var(--color-primary);
}

.component-btn span {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  text-align: center;
}

/* Results Summary */
.results-summary {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--spacing-3);
  padding: var(--spacing-3);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
}

.result-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-1);
}

.stat-label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  text-transform: uppercase;
}

.stat-value {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.stat-value.status-completed {
  color: var(--color-success);
}

.stat-value.status-failed {
  color: var(--color-error);
}

.stat-value.status-running {
  color: var(--color-primary);
}

/* Component Scores */
.component-scores {
  margin-top: var(--spacing-4);
}

.component-scores h4 {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-secondary);
  margin: 0 0 var(--spacing-3) 0;
}

.scores-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.score-item {
  display: grid;
  grid-template-columns: 100px 1fr 50px;
  align-items: center;
  gap: var(--spacing-3);
}

.score-name {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.score-bar-container {
  height: 8px;
  background: var(--bg-secondary);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.score-bar {
  height: 100%;
  border-radius: var(--radius-full);
  transition: width var(--duration-300) var(--ease-out);
}

.score-bar.excellent {
  background: var(--color-success);
}

.score-bar.good {
  background: var(--color-success-light);
}

.score-bar.warning {
  background: var(--color-warning);
}

.score-bar.critical {
  background: var(--color-error);
}

.score-value {
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  text-align: right;
}

/* Result Recommendations */
.result-recommendations {
  margin-top: var(--spacing-4);
  padding: var(--spacing-3);
  background: var(--color-warning-bg);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-warning);
}

.result-recommendations h4 {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--color-warning);
  margin: 0 0 var(--spacing-2) 0;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.recommendations-list {
  margin: 0;
  padding-left: var(--spacing-5);
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.recommendations-list li {
  margin-bottom: var(--spacing-1);
}

/* No Results State */
.no-results {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-8);
  color: var(--text-tertiary);
  text-align: center;
}

.no-results i {
  font-size: var(--text-3xl);
  margin-bottom: var(--spacing-3);
}

.no-results p {
  margin: 0;
  font-weight: var(--font-medium);
  color: var(--text-secondary);
}

.no-results span {
  font-size: var(--text-sm);
}

/* Responsive */
@media (max-width: 768px) {
  .quick-actions {
    flex-direction: column;
  }

  .results-summary {
    grid-template-columns: repeat(2, 1fr);
  }

  .score-item {
    grid-template-columns: 80px 1fr 40px;
    gap: var(--spacing-2);
  }
}
</style>
