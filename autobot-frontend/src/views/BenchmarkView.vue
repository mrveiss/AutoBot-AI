<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025-2026 mrveiss
  Author: mrveiss

  BenchmarkView.vue (Issue #9024) — LLM model-comparison dashboard.

  Runs a prompt (or a built-in prompt set) across several selected models via
  the existing useMultiModelCompare fan-out (POST /api/chat/compare, #4414),
  lets the operator rate each response 1-5, persists the run backend-side
  (/api/benchmarks/runs), lists historical runs with filters, plots cost vs
  quality, and exports results to CSV.
-->
<template>
  <div class="benchmark-view">
    <header class="benchmark-header">
      <h1 class="benchmark-title">{{ $t('benchmark.title') }}</h1>
      <p class="benchmark-subtitle">{{ $t('benchmark.subtitle') }}</p>
    </header>

    <!-- ── Run configuration ───────────────────────────────────────────── -->
    <section class="benchmark-panel">
      <div class="field">
        <label class="field-label">{{ $t('benchmark.promptSet') }}</label>
        <select v-model="selectedPromptSetId" class="field-input" @change="onPromptSetChange">
          <option value="">{{ $t('benchmark.customPrompt') }}</option>
          <option v-for="set in promptSets" :key="set.id" :value="set.id">{{ set.name }}</option>
        </select>
      </div>

      <div class="field">
        <label class="field-label">{{ $t('benchmark.prompt') }}</label>
        <textarea
          v-model="promptText"
          class="field-input field-textarea"
          rows="3"
          :placeholder="$t('benchmark.promptPlaceholder')"
        />
      </div>

      <div class="field">
        <label class="field-label">{{ $t('benchmark.models') }}</label>
        <div class="model-picker">
          <label v-for="model in availableModels" :key="model" class="model-chip">
            <input type="checkbox" :value="model" v-model="selectedModels" />
            <span>{{ model }}</span>
          </label>
        </div>
      </div>

      <div class="actions">
        <button
          class="btn btn-primary"
          :disabled="isComparing || !promptText.trim() || selectedModels.length === 0"
          @click="onRun"
        >
          {{ isComparing ? $t('benchmark.running') : $t('benchmark.runBenchmark') }}
        </button>
        <button class="btn" :disabled="!hasResults || isComparing" @click="onSaveRun">
          {{ $t('benchmark.saveRun') }}
        </button>
        <button class="btn" :disabled="!hasResults" @click="exportCsv">
          {{ $t('benchmark.exportCsv') }}
        </button>
      </div>
    </section>

    <!-- ── Side-by-side results ────────────────────────────────────────── -->
    <section v-if="resultRows.length" class="benchmark-results">
      <div v-for="row in resultRows" :key="row.model" class="result-card">
        <div class="result-card-head">
          <span class="result-model">{{ row.model }}</span>
          <span class="result-cost">{{ formatCost(row.costUsd) }}</span>
        </div>
        <pre v-if="!row.error" class="result-content">{{ row.content || '…' }}</pre>
        <p v-else class="result-error">{{ row.error }}</p>
        <div class="result-rating">
          <span class="rating-label">{{ $t('benchmark.quality') }}</span>
          <button
            v-for="star in 5"
            :key="star"
            type="button"
            class="star"
            :class="{ 'star-filled': star <= row.rating }"
            :aria-label="$t('benchmark.rateStars', { n: star })"
            @click="setRating(row.model, star)"
          >
            ★
          </button>
        </div>
      </div>
    </section>

    <!-- ── Cost / quality scatter ──────────────────────────────────────── -->
    <section v-if="scatterSeries.length" class="benchmark-chart">
      <BaseChart
        type="scatter"
        :series="scatterSeries"
        :options="scatterOptions"
        :title="$t('benchmark.scatterTitle')"
        :subtitle="$t('benchmark.scatterSubtitle')"
      />
    </section>

    <!-- ── Historical runs ─────────────────────────────────────────────── -->
    <section class="benchmark-history">
      <div class="history-head">
        <h2 class="history-title">{{ $t('benchmark.history') }}</h2>
        <div class="history-filters">
          <input
            v-model="filterModel"
            class="field-input field-input-sm"
            :placeholder="$t('benchmark.filterModel')"
            @keyup.enter="loadHistory"
          />
          <select v-model="filterPromptType" class="field-input field-input-sm" @change="loadHistory">
            <option value="">{{ $t('benchmark.allTypes') }}</option>
            <option v-for="t in promptTypes" :key="t" :value="t">{{ t }}</option>
          </select>
          <input
            v-model="filterSince"
            type="date"
            class="field-input field-input-sm"
            @change="loadHistory"
          />
          <button class="btn btn-sm" @click="loadHistory">{{ $t('benchmark.applyFilters') }}</button>
        </div>
      </div>

      <p v-if="!history.length" class="history-empty">{{ $t('benchmark.noRuns') }}</p>
      <table v-else class="history-table">
        <thead>
          <tr>
            <th>{{ $t('benchmark.date') }}</th>
            <th>{{ $t('benchmark.type') }}</th>
            <th>{{ $t('benchmark.modelsCol') }}</th>
            <th>{{ $t('benchmark.avgQuality') }}</th>
            <th>{{ $t('benchmark.totalCost') }}</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="run in history" :key="run.id">
            <td>{{ formatDate(run.createdAt) }}</td>
            <td>{{ run.promptType }}</td>
            <td>{{ run.models.join(', ') }}</td>
            <td>{{ avgQuality(run).toFixed(1) }}</td>
            <td>{{ formatCost(totalCost(run)) }}</td>
            <td>
              <button class="btn btn-sm btn-danger" @click="deleteRun(run.id)">
                {{ $t('benchmark.delete') }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ApexOptions } from 'apexcharts'
import ApiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'
import { useMultiModelCompare } from '@/composables/useMultiModelCompare'
import { useAvailableModels } from '@/composables/useAvailableModels'
import BaseChart from '@/components/charts/BaseChart.vue'
import {
  type BenchmarkResultRow,
  type BenchmarkRun,
  type PromptSet,
  estimateCostUsd,
  toCsv,
  avgQuality,
  totalCost,
} from '@/utils/benchmark'

const { t } = useI18n()
const logger = createLogger('BenchmarkView')

const { responses, selectedModels, isComparing, compare } = useMultiModelCompare()
const { availableModelNames, fetchModels } = useAvailableModels()

const promptText = ref('')
const selectedPromptSetId = ref('')
const promptSets = ref<PromptSet[]>([])
const ratings = ref<Record<string, number>>({})
const runStartedAt = ref<number>(0)

const history = ref<BenchmarkRun[]>([])
const filterModel = ref('')
const filterPromptType = ref('')
const filterSince = ref('')

const promptTypes = ['rag', 'code', 'summarization', 'reasoning', 'custom']

// #10718: build the picker from the live /api/models list (+ any already-selected
// model) — no hardcoded seed masquerading as real availability. Before fetch
// resolves the list is empty; the picker renders no fake models.
const availableModels = computed<string[]>(() => {
  const union = new Set<string>([...availableModelNames.value, ...selectedModels.value])
  return Array.from(union)
})

// Seed the selection once the live list loads, but only when the user has no
// persisted choice yet. The watcher handles the async fetch timing.
watch(availableModelNames, (names) => {
  if (selectedModels.value.length === 0 && names.length > 0) {
    selectedModels.value = [...names]
  }
})

const currentPromptType = computed(
  () => promptSets.value.find((s) => s.id === selectedPromptSetId.value)?.promptType ?? 'custom',
)

// Map streaming responses → flat result rows enriched with rating + est. cost.
const resultRows = computed<BenchmarkResultRow[]>(() => {
  const rows: BenchmarkResultRow[] = []
  for (const [model, resp] of responses.value.entries()) {
    rows.push({
      model,
      content: resp.content,
      error: resp.error,
      rating: ratings.value[model] ?? 0,
      costUsd: estimateCostUsd(model, promptText.value, resp.content),
      latencyMs: 0,
    })
  }
  return rows
})

const hasResults = computed(() => resultRows.value.some((r) => r.content || r.error))

const scatterSeries = computed(() => {
  const points = resultRows.value
    .filter((r) => r.rating > 0)
    .map((r) => ({ x: Number(r.costUsd.toFixed(4)), y: r.rating, model: r.model }))
  return points.length ? [{ name: t('benchmark.scatterSeries'), data: points }] : []
})

const scatterOptions = computed<ApexOptions>(() => ({
  xaxis: { title: { text: t('benchmark.axisCost') }, tickAmount: 5 },
  yaxis: { title: { text: t('benchmark.axisQuality') }, min: 0, max: 5, tickAmount: 5 },
  tooltip: {
    // Apex's custom-tooltip context is loosely typed; cast to read our point shape.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    custom: (ctx: { seriesIndex: number; dataPointIndex: number; w: any }) => {
      const data = ctx.w.config.series[ctx.seriesIndex].data as Array<{ model: string; x: number; y: number }>
      const p = data[ctx.dataPointIndex]
      return `<div style="padding:6px">${p.model}<br/>$${p.x} · ★${p.y}</div>`
    },
  },
  markers: { size: 7 },
}))

function onPromptSetChange(): void {
  const set = promptSets.value.find((s) => s.id === selectedPromptSetId.value)
  if (set?.prompts?.length) promptText.value = set.prompts[0]
}

function setRating(model: string, value: number): void {
  ratings.value = { ...ratings.value, [model]: value }
}

async function onRun(): Promise<void> {
  if (!promptText.value.trim() || selectedModels.value.length === 0 || isComparing.value) return
  ratings.value = {}
  runStartedAt.value = Date.now()
  await compare(promptText.value, [...selectedModels.value])
}

async function onSaveRun(): Promise<void> {
  if (!hasResults.value) return
  try {
    await ApiClient.post(`${getApiBase()}/benchmarks/runs`, {
      prompt: promptText.value,
      promptType: currentPromptType.value,
      promptSetId: selectedPromptSetId.value || null,
      results: resultRows.value.map((r) => ({
        model: r.model,
        content: r.content,
        rating: r.rating,
        costUsd: r.costUsd,
        latencyMs: r.latencyMs,
        error: r.error ?? null,
      })),
    })
    await loadHistory()
  } catch (err) {
    logger.error('saveRun failed:', err)
  }
}

function exportCsv(): void {
  const csv = toCsv(resultRows.value, promptText.value, currentPromptType.value)
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `benchmark-${Date.now()}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

async function loadHistory(): Promise<void> {
  const params = new URLSearchParams()
  if (filterModel.value.trim()) params.set('model', filterModel.value.trim())
  if (filterPromptType.value) params.set('prompt_type', filterPromptType.value)
  if (filterSince.value) params.set('since', `${filterSince.value}T00:00:00+00:00`)
  const qs = params.toString()
  try {
    history.value = await ApiClient.get<BenchmarkRun[]>(
      `${getApiBase()}/benchmarks/runs${qs ? `?${qs}` : ''}`,
    )
  } catch (err) {
    logger.error('loadHistory failed:', err)
    history.value = []
  }
}

async function deleteRun(id: string): Promise<void> {
  try {
    await ApiClient.delete(`${getApiBase()}/benchmarks/runs/${id}`)
    await loadHistory()
  } catch (err) {
    logger.error('deleteRun failed:', err)
  }
}

async function loadPromptSets(): Promise<void> {
  try {
    promptSets.value = await ApiClient.get<PromptSet[]>(`${getApiBase()}/benchmarks/prompt-sets`)
  } catch (err) {
    logger.error('loadPromptSets failed:', err)
  }
}

function formatCost(v: number): string {
  return `$${v.toFixed(4)}`
}
function formatDate(iso: string): string {
  return new Date(iso).toLocaleString()
}

onMounted(() => {
  fetchModels().catch(() => {})
  loadPromptSets()
  loadHistory()
})
</script>

<style scoped>
.benchmark-view {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-6);
  padding: var(--spacing-6);
  overflow-y: auto;
}

.benchmark-title {
  font-size: var(--text-xl);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: 0;
}
.benchmark-subtitle {
  color: var(--text-secondary);
  margin: var(--spacing-1) 0 0;
}

.benchmark-panel {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: var(--spacing-5);
}

.field {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}
.field-label {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--text-secondary);
}
.field-input {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  padding: var(--spacing-2) var(--spacing-3);
  font: inherit;
}
.field-input-sm {
  padding: var(--spacing-1) var(--spacing-2);
  font-size: var(--text-sm);
}
.field-textarea {
  resize: vertical;
}

.model-picker {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-2);
}
.model-chip {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-full, 999px);
  padding: var(--spacing-1) var(--spacing-3);
  font-size: var(--text-sm);
  color: var(--text-primary);
  cursor: pointer;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-3);
}
.btn {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  padding: var(--spacing-2) var(--spacing-4);
  cursor: pointer;
  font: inherit;
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn-primary {
  background: var(--color-primary);
  color: var(--text-on-primary, #fff);
  border-color: var(--color-primary);
}
.btn-sm {
  padding: var(--spacing-1) var(--spacing-3);
  font-size: var(--text-sm);
}
.btn-danger {
  color: var(--color-error, #ef4444);
}

.benchmark-results {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--spacing-4);
}
.result-card {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}
.result-card-head {
  display: flex;
  justify-content: space-between;
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}
.result-cost {
  color: var(--text-secondary);
}
.result-content {
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 240px;
  overflow-y: auto;
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-primary);
}
.result-error {
  color: var(--color-error, #ef4444);
  margin: 0;
}
.result-rating {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}
.rating-label {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}
.star {
  background: none;
  border: none;
  color: var(--text-tertiary, #64748b);
  font-size: 1.25rem;
  cursor: pointer;
  line-height: 1;
}
.star-filled {
  color: var(--chart-yellow, #f59e0b);
}

.benchmark-history {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: var(--spacing-5);
}
.history-head {
  display: flex;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--spacing-3);
  margin-bottom: var(--spacing-4);
}
.history-title {
  font-size: var(--text-lg);
  color: var(--text-primary);
  margin: 0;
}
.history-filters {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-2);
}
.history-empty {
  color: var(--text-secondary);
}
.history-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm);
}
.history-table th,
.history-table td {
  text-align: left;
  padding: var(--spacing-2) var(--spacing-3);
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-primary);
}
.history-table th {
  color: var(--text-secondary);
  font-weight: var(--font-semibold);
}
</style>
