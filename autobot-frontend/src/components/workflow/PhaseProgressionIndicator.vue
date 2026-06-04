<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  PhaseProgressionIndicator.vue - On-demand phase progression display driven by the
  existing /api/validation-dashboard/report endpoint. All calls to the non-existent
  /api/project/* and /api/phases/* endpoints have been removed (#3382).
-->
<template>
  <div class="phase-progression-container">
    <!-- Header -->
    <div class="phase-header">
      <h2 class="phase-title">
        <Icon name="rocket" />
        {{ $t('workflow.phaseProgression.title') }}
      </h2>
      <div class="header-controls">
        <button
          @click="loadValidationData"
          :disabled="loading"
          class="btn-load-validation"
          aria-label="Load validation data"
        >
          <Icon name="spinner" class="animate-spin" v-if="loading" />
          <Icon name="play" v-else />
          {{ loading ? $t('workflow.phaseProgression.loading') : $t('workflow.phaseProgression.loadData') }}
        </button>
        <div v-if="phases.length > 0" class="overall-maturity">
          <span class="maturity-label">{{ $t('workflow.phaseProgression.systemMaturity') }}:</span>
          <div class="maturity-bar" role="progressbar" :aria-valuenow="systemMaturity" aria-valuemin="0" aria-valuemax="100">
            <div
              class="maturity-fill"
              :style="{ width: `${systemMaturity}%` }"
              :class="getMaturityClass(systemMaturity)"
            ></div>
          </div>
          <span class="maturity-percentage">{{ systemMaturity }}%</span>
        </div>
      </div>
    </div>

    <!-- Error State -->
    <div v-if="hasLoadError && !loading" class="error-notice" role="alert">
      <div class="error-content">
        <Icon name="exclamation-triangle" />
        <h3>{{ $t('workflow.phaseProgression.errorTitle') }}</h3>
        <p>{{ $t('workflow.phaseProgression.errorBody') }}</p>
        <button @click="retryLoad" class="btn-retry">
          <Icon name="redo" />
          {{ $t('workflow.phaseProgression.retry') }}
        </button>
      </div>
    </div>

    <!-- Empty / Ready State -->
    <div
      v-if="phases.length === 0 && !loading && !hasLoadError"
      class="no-data-state"
    >
      <div class="no-data-content">
        <Icon name="info-circle" />
        <h3>{{ $t('workflow.phaseProgression.readyTitle') }}</h3>
        <p>{{ $t('workflow.phaseProgression.readyHint') }}</p>
      </div>
    </div>

    <!-- Phase Grid -->
    <div v-if="!hasLoadError && phases.length > 0" class="phases-grid">
      <div
        v-for="phase in phases"
        :key="phase.name"
        class="phase-card"
        :class="getPhaseCardClass(phase)"
      >
        <!-- Phase Header -->
        <div class="phase-card-header">
          <div class="phase-icon">
            <Icon :name="getPhaseIcon(phase.name)" />
          </div>
          <div class="phase-info">
            <h3 class="phase-name">{{ phase.name }}</h3>
            <span class="phase-status" :class="getStatusClass(phase.status)">
              {{ formatStatus(phase.status) }}
            </span>
          </div>
          <div class="phase-completion">
            {{ phase.completion_percentage }}%
          </div>
        </div>

        <!-- Progress Bar -->
        <div class="progress-container">
          <div
            class="progress-bar"
            role="progressbar"
            :aria-valuenow="phase.completion_percentage"
            aria-valuemin="0"
            aria-valuemax="100"
          >
            <div
              class="progress-fill"
              :style="{ width: `${phase.completion_percentage}%` }"
              :class="getProgressClass(phase.completion_percentage)"
            ></div>
          </div>
        </div>

        <!-- Phase Description -->
        <div v-if="phase.description" class="phase-description">
          <p>{{ phase.description }}</p>
        </div>

        <!-- Capabilities -->
        <div v-if="phase.capabilities_unlocked?.length" class="capabilities">
          <strong>{{ $t('workflow.phaseProgression.capabilities') }}:</strong>
          <div class="capability-tags">
            <span
              v-for="capability in phase.capabilities_unlocked"
              :key="capability"
              class="capability-tag"
            >
              {{ capability }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- Loading Overlay -->
    <div v-if="loading" class="loading-overlay" aria-live="polite">
      <div class="loading-spinner">
        <Icon name="spinner" class="animate-spin" />
        <span>{{ $t('workflow.phaseProgression.loading') }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ApiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'
import { getApiBase } from '@/config/ssot-config'

const { t } = useI18n()
const logger = createLogger('PhaseProgressionIndicator')
const api = new ApiClient()

// ── Types ──────────────────────────────────────────────────────────────────

interface PhaseEntry {
  name: string
  completion_percentage: number
  status: string
  description?: string
  capabilities_unlocked?: string[]
}

interface ValidationReport {
  status: string
  report?: {
    system_overview?: { overall_maturity?: number }
    phase_details?: Array<{
      display_name?: string
      name?: string
      completion_percentage?: number
      status?: string
      description?: string
    }>
  }
}

// ── State ──────────────────────────────────────────────────────────────────

const phases = ref<PhaseEntry[]>([])
const systemMaturity = ref(0)
const loading = ref(false)
const hasLoadError = ref(false)

// ── API ────────────────────────────────────────────────────────────────────

/**
 * Load phase data from the validation-dashboard/report endpoint.
 * This is the only backend endpoint that covers phase progression and
 * actually exists. The former /api/phases/* and /api/project/* calls
 * have been removed as those endpoints do not exist (#3382).
 */
async function loadValidationData(): Promise<void> {
  loading.value = true
  hasLoadError.value = false

  try {
    const data = await api.get<ValidationReport>(`${getApiBase()}/validation-dashboard/report`)

    if (data.status === 'success' && data.report) {
      const overview = data.report.system_overview
      systemMaturity.value = overview?.overall_maturity ?? 0

      type PhaseDetail = NonNullable<NonNullable<typeof data.report>['phase_details']>[number]
      phases.value = (data.report.phase_details ?? []).map((p: PhaseDetail) => ({
        name: p.display_name ?? p.name ?? t('workflow.phaseProgression.unknownPhase'),
        completion_percentage: p.completion_percentage ?? 0,
        status:
          (p.completion_percentage ?? 0) >= 95
            ? 'complete'
            : (p.completion_percentage ?? 0) >= 75
              ? 'mostly_complete'
              : (p.completion_percentage ?? 0) >= 50
                ? 'in_progress'
                : 'incomplete',
        description: p.description,
        capabilities_unlocked: [],
      }))

      if (phases.value.length > 0) {
        const total = phases.value.reduce((sum, p) => sum + p.completion_percentage, 0)
        systemMaturity.value = Math.round(total / phases.value.length)
      }
    } else {
      phases.value = []
      systemMaturity.value = 0
      hasLoadError.value = true
    }
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err)
    logger.error('Failed to load validation report:', message)
    phases.value = []
    systemMaturity.value = 0
    hasLoadError.value = true
  } finally {
    loading.value = false
  }
}

async function retryLoad(): Promise<void> {
  hasLoadError.value = false
  await loadValidationData()
}

// ── Display helpers ────────────────────────────────────────────────────────

const PHASE_ICONS: Record<string, string> = {
  'Phase 1': 'server',
  'Phase 2': 'database',
  'Phase 3': 'brain',
  'Phase 4': 'shield-alt',
  'Phase 5': 'tachometer-alt',
  'Phase 6': 'chart-line',
  'Phase 7': 'desktop',
  'Phase 8': 'sitemap',
  'Phase 9': 'robot',
  'Phase 10': 'cloud',
}

function getPhaseIcon(name: string): string {
  for (const [key, icon] of Object.entries(PHASE_ICONS)) {
    if (name.startsWith(key)) return icon
  }
  return 'cog'
}

function getPhaseCardClass(phase: PhaseEntry): string[] {
  return [
    'phase-card-status',
    phase.status === 'complete'
      ? 'phase-complete'
      : phase.status === 'mostly_complete'
        ? 'phase-mostly-complete'
        : phase.status === 'in_progress'
          ? 'phase-in-progress'
          : 'phase-incomplete',
  ]
}

function getStatusClass(status: string): string {
  const map: Record<string, string> = {
    complete: 'status-complete',
    mostly_complete: 'status-mostly-complete',
    in_progress: 'status-in-progress',
    incomplete: 'status-incomplete',
    promoted: 'status-complete',
    eligible: 'status-in-progress',
    blocked: 'status-incomplete',
  }
  return map[status] ?? 'status-unknown'
}

function getProgressClass(pct: number): string {
  if (pct >= 95) return 'progress-complete'
  if (pct >= 75) return 'progress-mostly-complete'
  if (pct >= 50) return 'progress-in-progress'
  return 'progress-incomplete'
}

function getMaturityClass(maturity: number): string {
  if (maturity >= 95) return 'maturity-production'
  if (maturity >= 80) return 'maturity-beta'
  if (maturity >= 50) return 'maturity-alpha'
  return 'maturity-pre-alpha'
}

function formatStatus(status: string): string {
  return status.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}
</script>

<style scoped>
.phase-progression-container {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-5);
  padding: var(--spacing-5);
  background: var(--bg-primary);
  border-radius: var(--radius-md);
  position: relative;
}

/* Header */
.phase-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--spacing-3);
}

.phase-title {
  font-size: var(--text-xl);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.header-controls {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
  flex-wrap: wrap;
}

.btn-load-validation {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-4);
  background: var(--color-primary);
  color: var(--color-primary-fg, #fff);
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  cursor: pointer;
  transition: opacity var(--duration-150);
}

.btn-load-validation:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Maturity bar */
.overall-maturity {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.maturity-label {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  white-space: nowrap;
}

.maturity-bar {
  width: 120px;
  height: 8px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.maturity-fill {
  height: 100%;
  border-radius: var(--radius-full);
  transition: width 0.4s var(--ease-out);
}

.maturity-production { background: var(--color-success); }
.maturity-beta       { background: var(--color-info); }
.maturity-alpha      { background: var(--color-warning); }
.maturity-pre-alpha  { background: var(--color-error); }

.maturity-percentage {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  min-width: 3ch;
}

/* Error state */
.error-notice {
  border: 1px solid var(--color-error-border, #f87171);
  border-radius: var(--radius-md);
  background: var(--color-error-bg, rgba(239, 68, 68, 0.1));
  padding: var(--spacing-5);
}

.error-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-3);
  text-align: center;
  color: var(--color-error);
}

.error-content h3 {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
}

.error-content p {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.btn-retry {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-4);
  background: var(--color-error);
  color: #fff;
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  cursor: pointer;
}

/* No data state */
.no-data-state {
  text-align: center;
  padding: var(--spacing-10);
  color: var(--text-secondary);
}

.no-data-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-3);
}

.no-data-content i {
  font-size: var(--text-3xl);
  color: var(--color-info);
}

.no-data-content h3 {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.no-data-content p {
  font-size: var(--text-sm);
  max-width: 400px;
}

/* Phase grid */
.phases-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--spacing-4);
}

.phase-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: var(--spacing-4);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
  transition: box-shadow var(--duration-150);
}

.phase-card:hover {
  box-shadow: var(--shadow-md);
}

.phase-complete      { border-left: 4px solid var(--color-success); }
.phase-mostly-complete { border-left: 4px solid var(--color-info); }
.phase-in-progress   { border-left: 4px solid var(--color-warning); }
.phase-incomplete    { border-left: 4px solid var(--border-default); }

/* Phase card header */
.phase-card-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
}

.phase-icon {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  background: var(--bg-tertiary);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-primary);
  flex-shrink: 0;
}

.phase-info {
  flex: 1;
  min-width: 0;
}

.phase-name {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.phase-status {
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  text-transform: capitalize;
}

.status-complete        { color: var(--color-success); }
.status-mostly-complete { color: var(--color-info); }
.status-in-progress     { color: var(--color-warning); }
.status-incomplete      { color: var(--text-secondary); }
.status-unknown         { color: var(--text-secondary); }

.phase-completion {
  font-size: var(--text-lg);
  font-weight: var(--font-bold);
  color: var(--text-primary);
  flex-shrink: 0;
}

/* Progress bar */
.progress-container { width: 100%; }

.progress-bar {
  width: 100%;
  height: 6px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  border-radius: var(--radius-full);
  transition: width 0.4s var(--ease-out);
}

.progress-complete        { background: var(--color-success); }
.progress-mostly-complete { background: var(--color-info); }
.progress-in-progress     { background: var(--color-warning); }
.progress-incomplete      { background: var(--border-default); }

/* Description */
.phase-description p {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  line-height: var(--leading-relaxed);
}

/* Capabilities */
.capabilities {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.capability-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-1);
  margin-top: var(--spacing-1);
}

.capability-tag {
  padding: 2px var(--spacing-2);
  background: var(--bg-tertiary);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  color: var(--text-primary);
}

/* Loading overlay */
.loading-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
}

.loading-spinner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-3);
  color: #fff;
  font-size: var(--text-sm);
}

.loading-spinner i {
  font-size: var(--text-3xl);
}

@media (max-width: 640px) {
  .phases-grid { grid-template-columns: 1fr; }
  .header-controls { flex-direction: column; align-items: flex-start; }
}
</style>
