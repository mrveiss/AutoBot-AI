<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025-2026 mrveiss
  Author: mrveiss
  SPDX-License-Identifier: Apache-2.0

  Failure Analysis Dashboard
  Issue #9892: Wire causal-inference engine (analyze-failure) to the frontend.
-->
<template>
  <div class="failure-analysis-view">
    <!-- Page header -->
    <div class="page-header">
      <div class="page-header-content">
        <h2 class="page-title">{{ $t('analytics.failureAnalysis.title') }}</h2>
        <p class="page-subtitle">{{ $t('analytics.failureAnalysis.subtitle') }}</p>
      </div>
    </div>

    <!-- Submission form -->
    <div class="form-card">
      <h3 class="form-title">{{ $t('analytics.failureAnalysis.form.title') }}</h3>
      <div class="form-body">
        <div class="form-field">
          <label for="fa-task-id" class="form-label">
            {{ $t('analytics.failureAnalysis.form.taskId') }}
            <span class="required">*</span>
          </label>
          <input
            id="fa-task-id"
            v-model="taskId"
            type="text"
            class="form-input"
            :placeholder="$t('analytics.failureAnalysis.form.taskIdPlaceholder')"
            :disabled="loading"
            @keydown.enter="submitAnalysis"
          />
        </div>
        <div class="form-field">
          <label for="fa-error-desc" class="form-label">
            {{ $t('analytics.failureAnalysis.form.errorDescription') }}
          </label>
          <textarea
            id="fa-error-desc"
            v-model="errorDescription"
            class="form-textarea"
            :placeholder="$t('analytics.failureAnalysis.form.errorDescriptionPlaceholder')"
            :disabled="loading"
            rows="3"
          />
        </div>
        <div class="form-actions">
          <button
            class="btn-primary"
            :disabled="!taskId.trim() || loading"
            @click="submitAnalysis"
          >
            <span v-if="loading" class="spinner" aria-hidden="true" />
            {{ loading ? $t('analytics.failureAnalysis.form.analyzing') : $t('analytics.failureAnalysis.form.analyze') }}
          </button>
          <button
            v-if="result"
            class="btn-secondary"
            :disabled="loading"
            @click="clearResult"
          >
            {{ $t('analytics.failureAnalysis.form.clear') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Error banner -->
    <div v-if="error" class="error-banner" role="alert">
      <svg class="error-icon" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm.75-11.25a.75.75 0 00-1.5 0v4.5a.75.75 0 001.5 0v-4.5zm-.75 7a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd" />
      </svg>
      <span>{{ error }}</span>
      <button class="btn-dismiss" :aria-label="$t('common.dismiss')" @click="error = null">
        <svg viewBox="0 0 20 20" fill="currentColor" class="dismiss-icon" aria-hidden="true">
          <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
        </svg>
      </button>
    </div>

    <!-- Result panel -->
    <div v-if="result" class="result-panel">
      <!-- Summary row -->
      <div class="summary-row">
        <div class="summary-badge" :class="severityClass(result.severity)">
          {{ result.severity.toUpperCase() }}
        </div>
        <div class="summary-meta">
          <span class="meta-item">
            <strong>{{ $t('analytics.failureAnalysis.result.taskId') }}:</strong> {{ result.task_id }}
          </span>
          <span class="meta-item">
            <strong>{{ $t('analytics.failureAnalysis.result.confidence') }}:</strong>
            {{ (result.confidence * 100).toFixed(0) }}%
          </span>
          <span class="meta-item">
            <strong>{{ $t('analytics.failureAnalysis.result.status') }}:</strong>
            {{ result.analysis_status }}
          </span>
          <span class="meta-item">
            <strong>{{ $t('analytics.failureAnalysis.result.duration') }}:</strong>
            {{ result.analysis_duration_ms.toFixed(0) }} ms
          </span>
        </div>
      </div>

      <!-- Root cause -->
      <section v-if="result.root_cause" class="result-section">
        <h3 class="section-title">{{ $t('analytics.failureAnalysis.result.rootCause') }}</h3>
        <div class="event-card root-cause-card">
          <div class="event-header">
            <span class="event-name">{{ result.root_cause.name }}</span>
            <span class="event-type-badge">{{ result.root_cause.event_type }}</span>
            <span class="confidence-pill">{{ (result.root_cause.confidence * 100).toFixed(0) }}%</span>
          </div>
          <p class="event-description">{{ result.root_cause.description }}</p>
          <div v-if="result.root_cause.participants.length" class="participants">
            <strong>{{ $t('analytics.failureAnalysis.result.participants') }}:</strong>
            {{ result.root_cause.participants.join(', ') }}
          </div>
        </div>
      </section>

      <!-- Causal chain -->
      <section v-if="result.causal_chain.length" class="result-section">
        <h3 class="section-title">
          {{ $t('analytics.failureAnalysis.result.causalChain') }}
          <span class="count-badge">{{ result.causal_chain.length }}</span>
        </h3>
        <ol class="causal-chain-list">
          <li v-for="(event, idx) in result.causal_chain" :key="String(event.event_id || idx)" class="chain-item">
            <div class="chain-index">{{ Number(idx) + 1 }}</div>
            <div class="event-card">
              <div class="event-header">
                <span class="event-name">{{ event.name }}</span>
                <span class="event-type-badge">{{ event.event_type }}</span>
                <span class="confidence-pill">{{ (event.confidence * 100).toFixed(0) }}%</span>
              </div>
              <p v-if="event.description" class="event-description">{{ event.description }}</p>
            </div>
          </li>
        </ol>
      </section>

      <!-- Interventions -->
      <section v-if="result.interventions.length" class="result-section">
        <h3 class="section-title">
          {{ $t('analytics.failureAnalysis.result.interventions') }}
          <span class="count-badge">{{ result.interventions.length }}</span>
        </h3>
        <div class="interventions-grid">
          <div
            v-for="(intv, idx) in result.interventions"
            :key="idx"
            class="intervention-card"
          >
            <div class="intv-header">
              <span class="intv-rank">#{{ intv.impact_rank }}</span>
              <span class="intv-name">{{ intv.name }}</span>
              <span class="rec-type-badge" :class="recTypeClass(intv.recommendation_type)">
                {{ intv.recommendation_type.replace('_', ' ') }}
              </span>
            </div>
            <p class="intv-description">{{ intv.description }}</p>
            <p class="intv-mechanism">
              <strong>{{ $t('analytics.failureAnalysis.result.mechanism') }}:</strong>
              {{ intv.mechanism }}
            </p>
            <div class="intv-meta">
              <span class="meta-pill">
                {{ $t('analytics.failureAnalysis.result.successRate') }}: {{ (intv.predicted_success_rate * 100).toFixed(0) }}%
              </span>
              <span class="meta-pill cost-pill" :class="levelClass(intv.cost_level)">
                {{ $t('analytics.failureAnalysis.result.cost') }}: {{ intv.cost_level }}
              </span>
              <span class="meta-pill risk-pill" :class="levelClass(intv.risk_level)">
                {{ $t('analytics.failureAnalysis.result.risk') }}: {{ intv.risk_level }}
              </span>
            </div>
            <ul v-if="intv.evidence.length" class="evidence-list">
              <li v-for="(ev, ei) in intv.evidence" :key="ei">{{ ev }}</li>
            </ul>
          </div>
        </div>
      </section>

      <!-- Confounders -->
      <section v-if="result.confounders.length" class="result-section">
        <h3 class="section-title">
          {{ $t('analytics.failureAnalysis.result.confounders') }}
          <span class="count-badge">{{ result.confounders.length }}</span>
        </h3>
        <div class="confounders-list">
          <div v-for="(conf, idx) in result.confounders" :key="String(conf.event_id || idx)" class="event-card">
            <div class="event-header">
              <span class="event-name">{{ conf.name }}</span>
              <span class="event-type-badge">{{ conf.event_type }}</span>
              <span class="confidence-pill">{{ (conf.confidence * 100).toFixed(0) }}%</span>
            </div>
            <p v-if="conf.description" class="event-description">{{ conf.description }}</p>
          </div>
        </div>
        <p v-if="result.confounding_strength > 0" class="confounding-strength">
          {{ $t('analytics.failureAnalysis.result.confoundingStrength') }}:
          {{ (result.confounding_strength * 100).toFixed(0) }}%
        </p>
      </section>

      <!-- Recommendations -->
      <section v-if="result.recommendations.length" class="result-section">
        <h3 class="section-title">{{ $t('analytics.failureAnalysis.result.recommendations') }}</h3>
        <ul class="recommendations-list">
          <li v-for="(rec, idx) in result.recommendations" :key="idx">{{ rec }}</li>
        </ul>
      </section>
    </div>

    <!-- Empty state -->
    <div v-else-if="!loading && !error" class="empty-state">
      <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.75 9.75l4.5 4.5m0-4.5l-4.5 4.5M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      <p>{{ $t('analytics.failureAnalysis.empty') }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useFailureAnalysis } from '@/composables/useFailureAnalysis'

const { loading, error, result, analyzeFailure, clearResult } = useFailureAnalysis()

const taskId = ref('')
const errorDescription = ref('')

async function submitAnalysis() {
  if (!taskId.value.trim()) return
  await analyzeFailure(taskId.value.trim(), errorDescription.value.trim() || undefined)
}

function severityClass(severity: string): string {
  switch (severity) {
    case 'critical': return 'badge-critical'
    case 'degraded': return 'badge-degraded'
    default: return 'badge-warning'
  }
}

function recTypeClass(type: string): string {
  switch (type) {
    case 'immediate': return 'rec-immediate'
    case 'short_term': return 'rec-short'
    default: return 'rec-long'
  }
}

function levelClass(level: string): string {
  switch (level) {
    case 'high': return 'level-high'
    case 'medium': return 'level-medium'
    default: return 'level-low'
  }
}
</script>

<style scoped>
.failure-analysis-view {
  padding: var(--spacing-6) var(--spacing-8);
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-6);
}

/* Page header */
.page-header {
  border-bottom: 1px solid var(--border-default);
  padding-bottom: var(--spacing-4);
}

.page-title {
  margin: 0;
  font-size: var(--text-2xl);
  font-weight: 600;
  color: var(--text-primary);
  font-family: var(--font-sans);
}

.page-subtitle {
  margin: var(--spacing-1) 0 0;
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

/* Form card */
.form-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--spacing-6);
}

.form-title {
  margin: 0 0 var(--spacing-4);
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
}

.form-body {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.form-label {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-secondary);
}

.required {
  color: var(--color-red-500);
  margin-left: 2px;
}

.form-input,
.form-textarea {
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: var(--spacing-2) var(--spacing-3);
  font-size: var(--text-sm);
  color: var(--text-primary);
  width: 100%;
  box-sizing: border-box;
  transition: border-color 0.15s;
}

.form-input:focus,
.form-textarea:focus {
  outline: none;
  border-color: var(--color-blue-500);
}

.form-textarea {
  resize: vertical;
  min-height: 4rem;
}

.form-actions {
  display: flex;
  gap: var(--spacing-3);
  align-items: center;
}

.btn-primary {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-5);
  background: var(--color-blue-600);
  color: #fff;
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.15s;
}

.btn-primary:hover:not(:disabled) {
  background: var(--color-blue-700);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  padding: var(--spacing-2) var(--spacing-5);
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s;
}

.btn-secondary:hover:not(:disabled) {
  border-color: var(--text-secondary);
  color: var(--text-primary);
}

.spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.4);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Error banner */
.error-banner {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-3) var(--spacing-4);
  background: var(--color-red-50, #fef2f2);
  border: 1px solid var(--color-red-200, #fecaca);
  border-radius: var(--radius-md);
  color: var(--color-red-700, #b91c1c);
  font-size: var(--text-sm);
}

.error-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
}

.btn-dismiss {
  margin-left: auto;
  background: none;
  border: none;
  cursor: pointer;
  color: inherit;
  padding: 0;
  line-height: 1;
}

.dismiss-icon {
  width: 16px;
  height: 16px;
}

/* Result panel */
.result-panel {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-6);
}

.summary-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--spacing-3);
  padding: var(--spacing-4) var(--spacing-5);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
}

.summary-badge {
  padding: var(--spacing-1) var(--spacing-3);
  border-radius: var(--radius-full, 9999px);
  font-size: var(--text-xs);
  font-weight: 700;
  letter-spacing: 0.05em;
}

.badge-critical {
  background: var(--color-red-100, #fee2e2);
  color: var(--color-red-800, #991b1b);
}

.badge-degraded {
  background: var(--color-amber-100, #fef3c7);
  color: var(--color-amber-800, #92400e);
}

.badge-warning {
  background: var(--color-yellow-100, #fef9c3);
  color: var(--color-yellow-800, #854d0e);
}

.summary-meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-4);
}

.meta-item {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.meta-item strong {
  color: var(--text-primary);
}

/* Sections */
.result-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--spacing-5);
}

.section-title {
  margin: 0 0 var(--spacing-4);
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.count-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  background: var(--bg-tertiary, var(--bg-primary));
  border: 1px solid var(--border-default);
  border-radius: 50%;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--text-secondary);
}

/* Event cards */
.event-card {
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: var(--spacing-3) var(--spacing-4);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.root-cause-card {
  border-left: 3px solid var(--color-red-500, #ef4444);
}

.event-header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--spacing-2);
}

.event-name {
  font-weight: 600;
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.event-type-badge {
  padding: 2px var(--spacing-2);
  background: var(--bg-tertiary, var(--bg-secondary));
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.confidence-pill {
  margin-left: auto;
  padding: 2px var(--spacing-2);
  background: var(--color-blue-50, #eff6ff);
  border-radius: var(--radius-full, 9999px);
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-blue-700, #1d4ed8);
}

.event-description {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: 1.5;
}

.participants {
  font-size: var(--text-xs);
  color: var(--text-tertiary, var(--text-secondary));
}

/* Causal chain list */
.causal-chain-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.chain-item {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-3);
}

.chain-index {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--color-blue-600, #2563eb);
  color: #fff;
  font-size: var(--text-xs);
  font-weight: 700;
  margin-top: var(--spacing-1);
}

.chain-item .event-card {
  flex: 1;
}

/* Interventions grid */
.interventions-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: var(--spacing-4);
}

.intervention-card {
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: var(--spacing-4);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.intv-header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--spacing-2);
}

.intv-rank {
  font-weight: 700;
  font-size: var(--text-sm);
  color: var(--text-tertiary, var(--text-secondary));
}

.intv-name {
  font-weight: 600;
  font-size: var(--text-sm);
  color: var(--text-primary);
  flex: 1;
}

.rec-type-badge {
  padding: 2px var(--spacing-2);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  font-weight: 600;
  text-transform: capitalize;
}

.rec-immediate {
  background: var(--color-red-100, #fee2e2);
  color: var(--color-red-700, #b91c1c);
}

.rec-short {
  background: var(--color-amber-100, #fef3c7);
  color: var(--color-amber-700, #b45309);
}

.rec-long {
  background: var(--color-blue-100, #dbeafe);
  color: var(--color-blue-700, #1d4ed8);
}

.intv-description {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: 1.5;
}

.intv-mechanism {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--text-secondary);
  line-height: 1.5;
}

.intv-meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-2);
}

.meta-pill {
  padding: 2px var(--spacing-2);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-full, 9999px);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.level-high {
  background: var(--color-red-50, #fef2f2);
  border-color: var(--color-red-200, #fecaca);
  color: var(--color-red-700, #b91c1c);
}

.level-medium {
  background: var(--color-amber-50, #fffbeb);
  border-color: var(--color-amber-200, #fde68a);
  color: var(--color-amber-700, #b45309);
}

.level-low {
  background: var(--color-green-50, #f0fdf4);
  border-color: var(--color-green-200, #bbf7d0);
  color: var(--color-green-700, #15803d);
}

.evidence-list {
  margin: 0;
  padding-left: var(--spacing-4);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

/* Confounders */
.confounders-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.confounding-strength {
  margin: var(--spacing-3) 0 0;
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

/* Recommendations */
.recommendations-list {
  margin: 0;
  padding-left: var(--spacing-5);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: 1.6;
}

/* Empty state */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-3);
  padding: var(--spacing-12) var(--spacing-8);
  color: var(--text-tertiary, var(--text-secondary));
  text-align: center;
}

.empty-icon {
  width: 48px;
  height: 48px;
  color: var(--border-default);
}
</style>
