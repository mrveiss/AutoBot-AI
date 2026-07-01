<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Vision automation panel — backed by /api/vision/* endpoints (wired per #9890). -->
<script setup lang="ts">
/**
 * VisionAutomationView — Screen analysis, element detection, OCR, and
 * automation opportunity discovery backed by /api/vision/* endpoints.
 */

import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { createLogger } from '@/utils/debugUtils'
import { useVisionAutomation } from '@/composables/useVisionAutomation'
import Icon from '@/components/ui/Icon.vue'

const { t } = useI18n()
const logger = createLogger('VisionAutomationView')

const {
  isLoading,
  error,
  status,
  screenAnalysis,
  detectedElements,
  ocrResult,
  opportunities,
  fetchStatus,
  analyzeScreen,
  detectElements,
  extractOCR,
  fetchOpportunities,
} = useVisionAutomation()

type Tab = 'analysis' | 'elements' | 'ocr' | 'opportunities'
const activeTab = ref<Tab>('analysis')
const sessionId = ref('')
const elementTypeFilter = ref('')
const minConfidence = ref(0.5)

function statusBadgeClass(s: string): string {
  if (s === 'operational' || s === 'online') return 'badge-success'
  if (s === 'degraded') return 'badge-warning'
  return 'badge-error'
}

async function handleAnalyze(): Promise<void> {
  logger.debug('Starting screen analysis')
  await analyzeScreen(sessionId.value || undefined)
}

async function handleDetectElements(): Promise<void> {
  logger.debug('Detecting elements, type filter:', elementTypeFilter.value)
  await detectElements(
    elementTypeFilter.value || undefined,
    minConfidence.value,
    sessionId.value || undefined,
  )
}

async function handleExtractOCR(): Promise<void> {
  logger.debug('Extracting OCR')
  await extractOCR(sessionId.value || undefined)
}

async function handleFetchOpportunities(): Promise<void> {
  logger.debug('Fetching automation opportunities')
  await fetchOpportunities(sessionId.value || undefined)
}

onMounted(async () => {
  await fetchStatus()
})
</script>

<template>
  <div class="vision-automation-view">
    <!-- Header -->
    <div class="page-header">
      <div class="page-header-content">
        <h2 class="page-title">{{ t('vision.visionAutomation.title') }}</h2>
        <p class="page-subtitle">{{ t('vision.visionAutomation.subtitle') }}</p>
      </div>
      <div v-if="status" class="status-summary">
        <span class="status-label">{{ t('vision.visionAutomation.serviceStatus') }}</span>
        <span :class="['badge', statusBadgeClass(status.status)]">
          {{ status.status }}
        </span>
      </div>
    </div>

    <!-- Error alert -->
    <div v-if="error" class="alert alert-error" role="alert">
      <Icon name="exclamation-circle" aria-hidden="true" />
      <div class="alert-content">
        <strong>{{ t('vision.visionAutomation.errorLabel') }}</strong>
        <p>{{ error }}</p>
      </div>
    </div>

    <!-- Session ID (optional context) -->
    <div class="card session-card">
      <div class="card-header">
        <span class="card-title">{{ t('vision.visionAutomation.sessionContext') }}</span>
      </div>
      <div class="card-body">
        <input
          v-model="sessionId"
          type="text"
          :placeholder="t('vision.visionAutomation.sessionIdPlaceholder')"
          class="field-input"
        />
      </div>
    </div>

    <!-- Tabs -->
    <nav class="tab-nav" role="tablist" :aria-label="t('vision.visionAutomation.tabsAriaLabel')">
      <button
        role="tab"
        :aria-selected="activeTab === 'analysis'"
        :class="['tab-btn', { active: activeTab === 'analysis' }]"
        @click="activeTab = 'analysis'"
      >
        <Icon name="camera" aria-hidden="true" />
        {{ t('vision.visionAutomation.tabs.analysis') }}
      </button>
      <button
        role="tab"
        :aria-selected="activeTab === 'elements'"
        :class="['tab-btn', { active: activeTab === 'elements' }]"
        @click="activeTab = 'elements'"
      >
        <Icon name="th" aria-hidden="true" />
        {{ t('vision.visionAutomation.tabs.elements') }}
      </button>
      <button
        role="tab"
        :aria-selected="activeTab === 'ocr'"
        :class="['tab-btn', { active: activeTab === 'ocr' }]"
        @click="activeTab = 'ocr'"
      >
        <Icon name="font" aria-hidden="true" />
        {{ t('vision.visionAutomation.tabs.ocr') }}
      </button>
      <button
        role="tab"
        :aria-selected="activeTab === 'opportunities'"
        :class="['tab-btn', { active: activeTab === 'opportunities' }]"
        @click="activeTab = 'opportunities'"
      >
        <Icon name="bolt" aria-hidden="true" />
        {{ t('vision.visionAutomation.tabs.opportunities') }}
      </button>
    </nav>

    <!-- Tab panels -->
    <div class="tab-content">
      <!-- Screen Analysis -->
      <div v-show="activeTab === 'analysis'" class="tab-panel">
        <div class="card">
          <div class="card-header">
            <span class="card-title">{{ t('vision.visionAutomation.analysis.cardTitle') }}</span>
            <button
              class="btn-action-primary"
              :disabled="isLoading"
              @click="handleAnalyze"
            >
              {{ isLoading ? t('vision.visionAutomation.analyzing') : t('vision.visionAutomation.analysis.trigger') }}
            </button>
          </div>
          <div v-if="screenAnalysis" class="card-body">
            <div class="stats-row">
              <div class="stat-chip">
                <span class="stat-value">{{ screenAnalysis.ui_elements.length }}</span>
                <span class="stat-label">{{ t('vision.visionAutomation.analysis.elementsFound') }}</span>
              </div>
              <div class="stat-chip">
                <span class="stat-value">{{ screenAnalysis.text_regions.length }}</span>
                <span class="stat-label">{{ t('vision.visionAutomation.analysis.textRegions') }}</span>
              </div>
              <div class="stat-chip">
                <span class="stat-value">{{ Math.round(screenAnalysis.confidence_score * 100) }}%</span>
                <span class="stat-label">{{ t('vision.visionAutomation.analysis.confidence') }}</span>
              </div>
              <div class="stat-chip">
                <span class="stat-value">{{ screenAnalysis.automation_opportunities.length }}</span>
                <span class="stat-label">{{ t('vision.visionAutomation.analysis.automationOpps') }}</span>
              </div>
            </div>

            <div v-if="screenAnalysis.ui_elements.length > 0" class="elements-section">
              <h3 class="section-subheading">{{ t('vision.visionAutomation.analysis.detectedElements') }}</h3>
              <div class="table-wrapper">
                <table class="data-table">
                  <thead>
                    <tr>
                      <th>{{ t('vision.visionAutomation.columns.id') }}</th>
                      <th>{{ t('vision.visionAutomation.columns.type') }}</th>
                      <th>{{ t('vision.visionAutomation.columns.confidence') }}</th>
                      <th>{{ t('vision.visionAutomation.columns.text') }}</th>
                      <th>{{ t('vision.visionAutomation.columns.interactions') }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="el in screenAnalysis.ui_elements" :key="el.element_id">
                      <td class="cell-mono">{{ el.element_id.slice(0, 10) }}…</td>
                      <td>
                        <span class="badge badge-neutral">{{ el.element_type }}</span>
                      </td>
                      <td>{{ Math.round(el.confidence * 100) }}%</td>
                      <td class="cell-text">{{ el.text_content ?? '—' }}</td>
                      <td class="cell-chips">
                        <span
                          v-for="interaction in el.possible_interactions"
                          :key="interaction"
                          class="chip"
                        >{{ interaction }}</span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
          <div v-else class="card-body empty-state">
            <Icon name="camera" size="xl" aria-hidden="true" />
            <p>{{ t('vision.visionAutomation.analysis.empty') }}</p>
          </div>
        </div>
      </div>

      <!-- Element Detection -->
      <div v-show="activeTab === 'elements'" class="tab-panel">
        <div class="card">
          <div class="card-header">
            <span class="card-title">{{ t('vision.visionAutomation.elements.cardTitle') }}</span>
          </div>
          <div class="card-body filter-row">
            <input
              v-model="elementTypeFilter"
              type="text"
              :placeholder="t('vision.visionAutomation.elements.typePlaceholder')"
              class="field-input field-input--narrow"
            />
            <label class="field-label">
              {{ t('vision.visionAutomation.elements.minConfidence') }}
              <input
                v-model.number="minConfidence"
                type="range"
                min="0"
                max="1"
                step="0.05"
                class="range-input"
              />
              <span class="range-value">{{ Math.round(minConfidence * 100) }}%</span>
            </label>
            <button
              class="btn-action-primary"
              :disabled="isLoading"
              @click="handleDetectElements"
            >
              {{ isLoading ? t('vision.visionAutomation.detecting') : t('vision.visionAutomation.elements.trigger') }}
            </button>
          </div>
        </div>

        <div v-if="detectedElements" class="card">
          <div class="card-header">
            <span class="card-title">
              {{ t('vision.visionAutomation.elements.results', {
                filtered: detectedElements.filtered_count,
                total: detectedElements.total_detected,
              }) }}
            </span>
          </div>
          <div v-if="detectedElements.elements.length > 0" class="card-body">
            <div class="table-wrapper">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>{{ t('vision.visionAutomation.columns.id') }}</th>
                    <th>{{ t('vision.visionAutomation.columns.type') }}</th>
                    <th>{{ t('vision.visionAutomation.columns.confidence') }}</th>
                    <th>{{ t('vision.visionAutomation.columns.text') }}</th>
                    <th>{{ t('vision.visionAutomation.columns.position') }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="el in detectedElements.elements" :key="el.element_id">
                    <td class="cell-mono">{{ el.element_id.slice(0, 10) }}…</td>
                    <td>
                      <span class="badge badge-neutral">{{ el.element_type }}</span>
                    </td>
                    <td>{{ Math.round(el.confidence * 100) }}%</td>
                    <td class="cell-text">{{ el.text_content ?? '—' }}</td>
                    <td class="cell-mono">
                      {{ el.center_point.map((v: number) => Math.round(v)).join(', ') }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          <div v-else class="card-body empty-state">
            <p>{{ t('vision.visionAutomation.elements.empty') }}</p>
          </div>
        </div>
      </div>

      <!-- OCR -->
      <div v-show="activeTab === 'ocr'" class="tab-panel">
        <div class="card">
          <div class="card-header">
            <span class="card-title">{{ t('vision.visionAutomation.ocr.cardTitle') }}</span>
            <button
              class="btn-action-primary"
              :disabled="isLoading"
              @click="handleExtractOCR"
            >
              {{ isLoading ? t('vision.visionAutomation.extracting') : t('vision.visionAutomation.ocr.trigger') }}
            </button>
          </div>
          <div v-if="ocrResult" class="card-body">
            <p class="result-summary">
              {{ t('vision.visionAutomation.ocr.regionsFound', { count: ocrResult.total_text_regions }) }}
            </p>
            <div v-if="ocrResult.text_regions.length > 0" class="ocr-regions">
              <div
                v-for="(region, idx) in ocrResult.text_regions"
                :key="idx"
                class="ocr-region-item"
              >
                <pre class="region-pre">{{ JSON.stringify(region, null, 2) }}</pre>
              </div>
            </div>
            <div v-else class="empty-state">
              <p>{{ t('vision.visionAutomation.ocr.noRegions') }}</p>
            </div>
          </div>
          <div v-else class="card-body empty-state">
            <Icon name="font" size="xl" aria-hidden="true" />
            <p>{{ t('vision.visionAutomation.ocr.empty') }}</p>
          </div>
        </div>
      </div>

      <!-- Automation Opportunities -->
      <div v-show="activeTab === 'opportunities'" class="tab-panel">
        <div class="card">
          <div class="card-header">
            <span class="card-title">{{ t('vision.visionAutomation.opportunities.cardTitle') }}</span>
            <button
              class="btn-action-primary"
              :disabled="isLoading"
              @click="handleFetchOpportunities"
            >
              {{ isLoading ? t('vision.visionAutomation.scanning') : t('vision.visionAutomation.opportunities.trigger') }}
            </button>
          </div>
          <div v-if="opportunities" class="card-body">
            <div class="stats-row">
              <div class="stat-chip">
                <span class="stat-value">{{ opportunities.total_opportunities }}</span>
                <span class="stat-label">{{ t('vision.visionAutomation.opportunities.total') }}</span>
              </div>
              <div class="stat-chip">
                <span class="stat-value">{{ Math.round(opportunities.confidence * 100) }}%</span>
                <span class="stat-label">{{ t('vision.visionAutomation.analysis.confidence') }}</span>
              </div>
            </div>

            <div v-if="opportunities.opportunities.length > 0" class="opportunities-list">
              <div
                v-for="(opp, idx) in opportunities.opportunities"
                :key="idx"
                class="opportunity-item card"
              >
                <pre class="region-pre">{{ JSON.stringify(opp, null, 2) }}</pre>
              </div>
            </div>
            <div v-else class="empty-state">
              <Icon name="bolt" size="xl" aria-hidden="true" />
              <p>{{ t('vision.visionAutomation.opportunities.empty') }}</p>
            </div>
          </div>
          <div v-else class="card-body empty-state">
            <Icon name="bolt" size="xl" aria-hidden="true" />
            <p>{{ t('vision.visionAutomation.opportunities.emptyHint') }}</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.vision-automation-view {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: 1.5rem;
  max-width: 1200px;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.75rem;
}

.page-title {
  font-size: 1.375rem;
  font-weight: 700;
  color: var(--color-text-primary, #111827);
  margin: 0;
}

.page-subtitle {
  font-size: 0.875rem;
  color: var(--color-text-secondary, #6b7280);
  margin: 0.25rem 0 0;
}

.status-summary {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
}

.status-label {
  color: var(--color-text-secondary, #6b7280);
}

.session-card {
  margin-bottom: 0;
}

.tab-nav {
  display: flex;
  gap: 0.25rem;
  border-bottom: 1px solid var(--color-border, #e5e7eb);
  padding-bottom: 0;
  flex-wrap: wrap;
}

.tab-btn {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.5rem 1rem;
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--color-text-secondary, #6b7280);
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
}

.tab-btn:hover {
  color: var(--color-text-primary, #111827);
}

.tab-btn.active {
  color: var(--color-primary, #6366f1);
  border-bottom-color: var(--color-primary, #6366f1);
}

.tab-content {
  flex: 1;
}

.tab-panel {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.card {
  background: var(--color-surface, #fff);
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: 0.5rem;
  overflow: hidden;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--color-border, #e5e7eb);
  background: var(--color-surface-secondary, #f9fafb);
}

.card-title {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-text-primary, #111827);
}

.card-body {
  padding: 1rem;
}

.filter-row {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}

.field-input {
  flex: 1;
  min-width: 0;
  padding: 0.5rem 0.75rem;
  font-size: 0.875rem;
  border: 1px solid var(--color-border, #d1d5db);
  border-radius: 0.375rem;
  background: var(--color-surface, #fff);
  color: var(--color-text-primary, #111827);
}

.field-input--narrow {
  max-width: 14rem;
}

.field-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  color: var(--color-text-secondary, #6b7280);
  white-space: nowrap;
}

.range-input {
  width: 6rem;
  cursor: pointer;
}

.range-value {
  font-weight: 600;
  color: var(--color-text-primary, #111827);
  min-width: 3rem;
}

.btn-action-primary {
  padding: 0.5rem 1rem;
  font-size: 0.875rem;
  font-weight: 500;
  color: #fff;
  background: var(--color-primary, #6366f1);
  border: none;
  border-radius: 0.375rem;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s;
}

.btn-action-primary:hover:not(:disabled) {
  background: var(--color-primary-hover, #4f46e5);
}

.btn-action-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.stats-row {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
  margin-bottom: 1rem;
}

.stat-chip {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0.5rem 1rem;
  background: var(--color-surface-secondary, #f9fafb);
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: 0.5rem;
  min-width: 5rem;
}

.stat-value {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--color-primary, #6366f1);
}

.stat-label {
  font-size: 0.75rem;
  color: var(--color-text-secondary, #6b7280);
  text-align: center;
}

.section-subheading {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-text-primary, #111827);
  margin: 0 0 0.75rem;
}

.elements-section {
  margin-top: 1rem;
}

.table-wrapper {
  overflow-x: auto;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}

.data-table th,
.data-table td {
  padding: 0.5rem 0.75rem;
  text-align: left;
  border-bottom: 1px solid var(--color-border, #e5e7eb);
}

.data-table th {
  font-weight: 600;
  color: var(--color-text-secondary, #6b7280);
  background: var(--color-surface-secondary, #f9fafb);
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.cell-mono {
  font-family: monospace;
  font-size: 0.8125rem;
  color: var(--color-text-secondary, #6b7280);
}

.cell-text {
  max-width: 14rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cell-chips {
  display: flex;
  gap: 0.25rem;
  flex-wrap: wrap;
}

.badge {
  display: inline-flex;
  align-items: center;
  padding: 0.125rem 0.5rem;
  border-radius: 9999px;
  font-size: 0.75rem;
  font-weight: 500;
}

.badge-success {
  background: #dcfce7;
  color: #15803d;
}

.badge-warning {
  background: #fef9c3;
  color: #a16207;
}

.badge-error {
  background: #fee2e2;
  color: #b91c1c;
}

.badge-neutral {
  background: var(--color-surface-secondary, #f3f4f6);
  color: var(--color-text-secondary, #6b7280);
}

.chip {
  display: inline-flex;
  align-items: center;
  padding: 0.125rem 0.375rem;
  background: var(--color-surface-secondary, #e5e7eb);
  border-radius: 0.25rem;
  font-size: 0.75rem;
  color: var(--color-text-secondary, #374151);
}

.result-summary {
  font-size: 0.875rem;
  color: var(--color-text-secondary, #6b7280);
  margin: 0 0 0.75rem;
}

.ocr-regions {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  max-height: 32rem;
  overflow-y: auto;
}

.ocr-region-item {
  background: var(--color-surface-secondary, #f9fafb);
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: 0.375rem;
  padding: 0.5rem;
}

.region-pre {
  font-family: monospace;
  font-size: 0.8125rem;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  color: var(--color-text-primary, #111827);
}

.opportunities-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  max-height: 32rem;
  overflow-y: auto;
}

.opportunity-item {
  padding: 0.75rem;
  background: var(--color-surface-secondary, #f9fafb);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  padding: 2rem 1rem;
  color: var(--color-text-secondary, #6b7280);
  font-size: 0.875rem;
  text-align: center;
}

.alert {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  border-radius: 0.5rem;
  font-size: 0.875rem;
}

.alert-error {
  background: #fee2e2;
  color: #b91c1c;
  border: 1px solid #fca5a5;
}

.alert-content strong {
  display: block;
  font-weight: 600;
  margin-bottom: 0.125rem;
}

.alert-content p {
  margin: 0;
}
</style>
