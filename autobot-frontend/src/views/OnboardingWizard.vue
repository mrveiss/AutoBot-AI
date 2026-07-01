<!--
AutoBot - AI-Powered Automation Platform
Copyright (c) 2025 mrveiss
Author: mrveiss

OnboardingWizard.vue — First-run UX wizard (Issue #5061)

3-step flow:
  Step 1: Doctor report — hardware + service health
  Step 2: Preset picker — choose a starter configuration
  Step 3: Review + Apply
-->

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('OnboardingWizard')
const router = useRouter()
const api = useApiClient()

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

const step = ref(1)
const loading = ref(false)
const error = ref<string | null>(null)
const errorSoft = ref(false)

function dismissError() {
  error.value = null
  errorSoft.value = false
}

interface HardwareInfo {
  ram_gb: number
  ram_available_gb: number
  disk_total_gb: number
  disk_free_gb: number
  cpu_cores: number
}

interface ServiceInfo {
  reachable: boolean
  detail: string
  url?: string
}

interface DoctorReport {
  hardware: HardwareInfo
  services: Record<string, ServiceInfo>
  recommendation: {
    llm_tier: string
    suggested_preset: string
    provider_note: string
  }
}

interface Preset {
  name: string
  title: string
  description: string
  agents: string[]
  skills: string[]
  connectors: string[]
  system_prompt: string
  llm_tier: string
}

const doctorReport = ref<DoctorReport | null>(null)
const presets = ref<Preset[]>([])
const selectedPreset = ref<string | null>(null)
const applyResult = ref<Record<string, unknown> | null>(null)

// ---------------------------------------------------------------------------
// Computed helpers
// ---------------------------------------------------------------------------

const selectedPresetData = computed<Preset | null>(
  () => presets.value.find(p => p.name === selectedPreset.value) ?? null
)

const STEPS = [
  { n: 1, label: 'System Check' },
  { n: 2, label: 'Choose Preset' },
  { n: 3, label: 'Review & Apply' },
]

const stepTitle = computed(() => {
  switch (step.value) {
    case 1: return 'System Health Check'
    case 2: return 'Choose a Starter Preset'
    case 3: return 'Review & Apply'
    default: return ''
  }
})

const canGoNext = computed(() => {
  if (step.value === 1) return !loading.value && !!doctorReport.value
  if (step.value === 2) return !!selectedPreset.value
  return false
})

function navigatePreset(currentIndex: number, direction: number) {
  const next = currentIndex + direction
  if (next < 0 || next >= presets.value.length) return
  selectedPreset.value = presets.value[next].name
  const cards = document.querySelectorAll<HTMLElement>('[role="listbox"] [role="option"]')
  cards[next]?.focus()
}

const tierBadgeClass = (tier: string) => {
  switch (tier) {
    case 'powerful': return 'badge-tier-powerful'
    case 'fast': return 'badge-tier-fast'
    default: return 'badge-tier-balanced'
  }
}

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------

async function loadDoctor() {
  loading.value = true
  error.value = null
  try {
    const response = await api.get<{ data: DoctorReport }>('/api/onboarding/doctor')
    doctorReport.value = (response as { data: DoctorReport }).data
    if (doctorReport.value?.recommendation?.suggested_preset) {
      selectedPreset.value = doctorReport.value.recommendation.suggested_preset
    }
  } catch (err) {
    logger.error('Doctor report failed', err)
    error.value = 'Could not load system health report. You can still continue.'
    errorSoft.value = true
  } finally {
    loading.value = false
  }
}

async function loadPresets() {
  try {
    const response = await api.get<{ data: Preset[] }>('/api/onboarding/presets')
    presets.value = (response as { data: Preset[] }).data ?? []
  } catch (err) {
    logger.error('Failed to load presets', err)
    error.value = 'Could not load presets.'
  }
}

async function applyPreset() {
  if (!selectedPreset.value) return
  loading.value = true
  error.value = null
  try {
    const response = await api.post<{ data: Record<string, unknown> }>('/api/onboarding/apply', {
      preset_name: selectedPreset.value,
      overrides: {},
    })
    applyResult.value = (response as { data: Record<string, unknown> }).data
    logger.info('Preset applied', applyResult.value)
    // #6452: clear router-guard cache so next navigation re-checks status
    // and sees preset_applied=true (then caches that).
    sessionStorage.removeItem('onboarding_preset_applied')
  } catch (err) {
    logger.error('Apply preset failed', err)
    error.value = 'Failed to apply preset. Please try again.'
  } finally {
    loading.value = false
  }
}

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------

function nextStep() {
  error.value = null
  errorSoft.value = false
  if (step.value < 3) step.value++
}

function prevStep() {
  error.value = null
  errorSoft.value = false
  if (step.value > 1) step.value--
}

async function handleApply() {
  await applyPreset()
  if (!error.value) {
    step.value = 4 // success state
  }
}

function goToChat() {
  router.push('/chat')
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

onMounted(async () => {
  await Promise.all([loadDoctor(), loadPresets()])
})
</script>

<template>
  <div class="onboarding-wizard view-container">
    <!-- Header -->
    <div class="wizard-header">
      <div class="wizard-brand">
        <Icon name="robot" class="text-autobot-accent" />
        <span class="ml-2 text-lg font-semibold text-autobot-text">AutoBot Setup</span>
      </div>
      <nav class="wizard-steps" aria-label="Setup progress">
        <template v-for="(s, idx) in STEPS" :key="s.n">
          <div
            :class="['step-item', { active: step === s.n, done: step > s.n }]"
            :aria-current="step === s.n ? 'step' : undefined"
          >
            <div class="step-circle" aria-hidden="true">
              <i v-if="step > s.n" class="fas fa-check"></i>
              <span v-else>{{ s.n }}</span>
            </div>
            <span class="step-label">{{ s.label }}</span>
          </div>
          <div v-if="idx < STEPS.length - 1" class="step-connector" aria-hidden="true"></div>
        </template>
      </nav>
    </div>

    <!-- Success state -->
    <div v-if="step === 4" class="wizard-card success-card">
      <Icon name="check-circle" class="text-green-400 text-5xl mb-4" />
      <h2 class="text-xl font-semibold text-autobot-text mb-2">You're all set!</h2>
      <p class="text-autobot-text-muted mb-6">
        Your preset has been applied. Head to Chat to start using AutoBot.
      </p>
      <button class="btn-primary" @click="goToChat">
        <Icon name="comments" class="mr-2" />Open Chat
      </button>
    </div>

    <!-- Wizard steps -->
    <template v-else>
      <div class="wizard-card">
        <h2 class="wizard-step-title">{{ stepTitle }}</h2>

        <!-- Error banner -->
        <div v-if="error" :class="['error-banner', { 'error-banner--soft': errorSoft }]" role="alert">
          <Icon name="exclamation-triangle" class="mr-2" />
          <span class="error-banner__message">{{ error }}</span>
          <button class="error-banner__dismiss" @click="dismissError" aria-label="Dismiss error">×</button>
        </div>

        <!-- ----------------------------------------------------------------
             STEP 1 — Doctor report
             ---------------------------------------------------------------- -->
        <div v-if="step === 1" class="step-content">
          <div v-if="loading" class="loading-state">
            <Icon name="spinner" class="animate-spin text-2xl text-autobot-accent" />
            <p class="mt-2 text-autobot-text-muted">Scanning system…</p>
          </div>

          <template v-else-if="doctorReport">
            <!-- Hardware -->
            <section class="doctor-section">
              <h3 class="section-title"><Icon name="cube" class="mr-2" />Hardware</h3>
              <div class="metrics-grid">
                <div class="metric-card">
                  <span class="metric-label">RAM</span>
                  <span class="metric-value">{{ doctorReport.hardware.ram_gb }} GiB</span>
                  <span class="metric-sub">{{ doctorReport.hardware.ram_available_gb }} GiB free</span>
                </div>
                <div class="metric-card">
                  <span class="metric-label">Disk</span>
                  <span class="metric-value">{{ doctorReport.hardware.disk_total_gb }} GiB</span>
                  <span class="metric-sub">{{ doctorReport.hardware.disk_free_gb }} GiB free</span>
                </div>
                <div class="metric-card">
                  <span class="metric-label">CPU cores</span>
                  <span class="metric-value">{{ doctorReport.hardware.cpu_cores }}</span>
                </div>
              </div>
            </section>

            <!-- Services -->
            <section class="doctor-section">
              <h3 class="section-title"><Icon name="server" class="mr-2" />Services</h3>
              <div class="services-list">
                <div
                  v-for="(info, name) in doctorReport.services"
                  :key="name"
                  class="service-row"
                >
                  <i
                    :class="['fas', info.reachable ? 'fa-check-circle text-green-400' : 'fa-times-circle text-red-400']"
                  ></i>
                  <span class="service-name capitalize">{{ name }}</span>
                  <span class="service-detail text-autobot-text-muted text-xs">{{ info.detail }}</span>
                </div>
              </div>
            </section>

            <!-- Recommendation -->
            <section class="doctor-section recommendation-box">
              <h3 class="section-title"><Icon name="lightbulb" class="mr-2" />Recommendation</h3>
              <div class="flex items-center gap-3 mb-2">
                <span class="text-autobot-text-muted text-sm">Suggested tier:</span>
                <span :class="['tier-badge', tierBadgeClass(doctorReport.recommendation.llm_tier)]">
                  {{ doctorReport.recommendation.llm_tier }}
                </span>
              </div>
              <p class="text-autobot-text-muted text-sm">{{ doctorReport.recommendation.provider_note }}</p>
            </section>
          </template>

          <div v-else class="loading-state text-autobot-text-muted">
            No system data available. You can continue to preset selection.
          </div>
        </div>

        <!-- ----------------------------------------------------------------
             STEP 2 — Preset picker
             ---------------------------------------------------------------- -->
        <div v-if="step === 2" class="step-content">
          <p class="text-autobot-text-muted text-sm mb-4">
            Choose a starter configuration that best matches your primary use-case.
            You can adjust everything later in Settings.
          </p>
          <div
            class="presets-grid"
            role="listbox"
            aria-label="Choose a starter preset"
            aria-required="true"
          >
            <div
              v-for="(preset, index) in presets"
              :key="preset.name"
              :class="['preset-card', { selected: selectedPreset === preset.name }]"
              @click="selectedPreset = preset.name"
              :aria-selected="selectedPreset === preset.name"
              role="option"
              :tabindex="selectedPreset === preset.name || (!selectedPreset && index === 0) ? 0 : -1"
              @keydown.enter="selectedPreset = preset.name"
              @keydown.space.prevent="selectedPreset = preset.name"
              @keydown.up.prevent="navigatePreset(index, -1)"
              @keydown.down.prevent="navigatePreset(index, 1)"
            >
              <div class="preset-card-header">
                <span class="preset-title">{{ preset.title }}</span>
                <span :class="['tier-badge', tierBadgeClass(preset.llm_tier)]">
                  {{ preset.llm_tier }}
                </span>
              </div>
              <p class="preset-description">{{ preset.description }}</p>
              <div v-if="preset.skills.length" class="preset-tags">
                <span v-for="skill in preset.skills.slice(0, 3)" :key="skill" class="tag">
                  {{ skill }}
                </span>
                <span v-if="preset.skills.length > 3" class="tag tag-more">
                  +{{ preset.skills.length - 3 }}
                </span>
              </div>
              <div v-if="selectedPreset === preset.name" class="preset-check-mark">
                <Icon name="check-circle" class="text-autobot-accent" />
              </div>
            </div>
          </div>
        </div>

        <!-- ----------------------------------------------------------------
             STEP 3 — Review + Apply
             ---------------------------------------------------------------- -->
        <div v-if="step === 3" class="step-content">
          <div v-if="selectedPresetData" class="review-box">
            <h3 class="font-semibold text-autobot-text mb-1">{{ selectedPresetData.title }}</h3>
            <p class="text-autobot-text-muted text-sm mb-4">{{ selectedPresetData.description }}</p>

            <div class="review-row">
              <span class="review-label">Agents</span>
              <span class="review-value">{{ selectedPresetData.agents.join(', ') || '—' }}</span>
            </div>
            <div class="review-row">
              <span class="review-label">Skills</span>
              <span class="review-value">{{ selectedPresetData.skills.join(', ') || '—' }}</span>
            </div>
            <div class="review-row">
              <span class="review-label">LLM tier</span>
              <span :class="['tier-badge', tierBadgeClass(selectedPresetData.llm_tier)]">
                {{ selectedPresetData.llm_tier }}
              </span>
            </div>
            <div class="review-row">
              <span class="review-label">System prompt</span>
              <span class="review-value italic text-autobot-text-muted">
                "{{ selectedPresetData.system_prompt.slice(0, 80) }}…"
              </span>
            </div>
          </div>
        </div>

        <!-- Footer navigation -->
        <div class="wizard-footer">
          <button
            v-if="step > 1"
            class="btn-secondary"
            :disabled="loading"
            @click="prevStep"
          >
            <Icon name="chevron-left" class="mr-1" />Back
          </button>
          <div class="flex-1"></div>
          <button
            v-if="step < 3"
            class="btn-primary"
            :disabled="!canGoNext"
            @click="nextStep"
          >
            Next<Icon name="chevron-right" class="ml-1" />
          </button>
          <button
            v-if="step === 3"
            class="btn-primary"
            :disabled="loading || !selectedPreset"
            @click="handleApply"
          >
            <Icon v-if="loading" name="spinner" class="animate-spin mr-2" />
            <span>{{ loading ? 'Applying…' : 'Apply Preset' }}</span>
          </button>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.onboarding-wizard {
  display: flex;
  flex-direction: column;
  align-items: center;
  /* #10750 C2: .view-container already clamps to viewport-header and scrolls;
     100vh forced the wizard-footer (Back/Next/Apply) below the fold */
  min-height: 100%;
  padding: 2rem 1rem;
  background: var(--bg-primary, #0f1117);
}

.wizard-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  max-width: 680px;
  margin-bottom: 2rem;
}

.wizard-brand {
  display: flex;
  align-items: center;
}

.wizard-steps {
  display: flex;
  align-items: center;
  gap: 0;
}

.step-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.3rem;
}

.step-circle {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 2px solid var(--border-default, #2a2d3a);
  background: transparent;
  color: var(--text-muted, #94a3b8);
  font-size: 0.75rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: border-color 0.2s, background 0.2s, color 0.2s;
}

.step-label {
  font-size: 0.65rem;
  font-weight: 500;
  color: var(--text-muted, #94a3b8);
  white-space: nowrap;
  transition: color 0.2s;
}

.step-item.active .step-circle {
  border-color: var(--color-accent, #6366f1);
  background: var(--color-accent, #6366f1);
  color: #fff;
}

.step-item.active .step-label {
  color: var(--text-primary, #e2e8f0);
}

.step-item.done .step-circle {
  border-color: var(--color-success, #22c55e);
  background: var(--color-success, #22c55e);
  color: #fff;
}

.step-item.done .step-label {
  color: var(--color-success, #22c55e);
}

.step-connector {
  width: 2rem;
  height: 2px;
  background: var(--border-default, #2a2d3a);
  margin-bottom: 1.1rem;
  flex-shrink: 0;
}

@media (max-width: 480px) {
  .step-label {
    display: none;
  }
  .step-connector {
    width: 1rem;
  }
}

.wizard-card {
  background: var(--bg-elevated, #1a1d27);
  border: 1px solid var(--border-default, #2a2d3a);
  border-radius: 12px;
  padding: 2rem;
  width: 100%;
  max-width: 680px;
}

.success-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 3rem;
}

.wizard-step-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary, #e2e8f0);
  margin-bottom: 1.5rem;
}

.error-banner {
  display: flex;
  align-items: center;
  background: rgba(239, 68, 68, 0.15);
  border: 1px solid rgba(239, 68, 68, 0.4);
  color: #fca5a5;
  border-radius: 6px;
  padding: 0.75rem 1rem;
  margin-bottom: 1rem;
  font-size: 0.875rem;
}

.error-banner--soft {
  background: rgba(234, 179, 8, 0.12);
  border-color: rgba(234, 179, 8, 0.35);
  color: #fde68a;
}

.error-banner__message {
  flex: 1;
}

.error-banner__dismiss {
  background: transparent;
  border: none;
  color: inherit;
  font-size: 1.1rem;
  line-height: 1;
  cursor: pointer;
  padding: 0 0 0 0.75rem;
  opacity: 0.7;
  transition: opacity 0.15s;
  flex-shrink: 0;
}

.error-banner__dismiss:hover {
  opacity: 1;
}

.step-content {
  min-height: 240px;
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem 0;
  color: var(--text-muted, #94a3b8);
}

/* Doctor sections */
.doctor-section {
  margin-bottom: 1.5rem;
}

.section-title {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-muted, #94a3b8);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 0.75rem;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 0.75rem;
}

.metric-card {
  background: var(--bg-primary, #0f1117);
  border: 1px solid var(--border-default, #2a2d3a);
  border-radius: 8px;
  padding: 0.75rem 1rem;
  display: flex;
  flex-direction: column;
}

.metric-label {
  font-size: 0.75rem;
  color: var(--text-muted, #94a3b8);
  margin-bottom: 0.25rem;
}

.metric-value {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary, #e2e8f0);
}

.metric-sub {
  font-size: 0.75rem;
  color: var(--text-muted, #94a3b8);
  margin-top: 0.125rem;
}

.services-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.service-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--border-default, #2a2d3a);
}

.service-name {
  color: var(--text-primary, #e2e8f0);
  font-size: 0.875rem;
  min-width: 80px;
}

.service-detail {
  margin-left: auto;
}

.recommendation-box {
  background: rgba(99, 102, 241, 0.07);
  border: 1px solid rgba(99, 102, 241, 0.25);
  border-radius: 8px;
  padding: 1rem;
}

.tier-badge {
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 0.15rem 0.5rem;
  border-radius: 4px;
}

.badge-tier-powerful {
  background: rgba(168, 85, 247, 0.2);
  color: #c084fc;
  border: 1px solid rgba(168, 85, 247, 0.4);
}

.badge-tier-balanced {
  background: rgba(99, 102, 241, 0.2);
  color: #818cf8;
  border: 1px solid rgba(99, 102, 241, 0.4);
}

.badge-tier-fast {
  background: rgba(34, 197, 94, 0.15);
  color: #4ade80;
  border: 1px solid rgba(34, 197, 94, 0.35);
}

/* Presets grid */
.presets-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 0.75rem;
}

.preset-card {
  position: relative;
  background: var(--bg-primary, #0f1117);
  border: 1px solid var(--border-default, #2a2d3a);
  border-radius: 10px;
  padding: 1rem;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  outline: none;
}

.preset-card:hover,
.preset-card:focus-visible {
  border-color: var(--color-accent, #6366f1);
}

.preset-card.selected {
  border-color: var(--color-accent, #6366f1);
  background: rgba(99, 102, 241, 0.06);
}

.preset-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.4rem;
}

.preset-title {
  font-weight: 600;
  font-size: 0.9rem;
  color: var(--text-primary, #e2e8f0);
}

.preset-description {
  font-size: 0.8rem;
  color: var(--text-muted, #94a3b8);
  line-height: 1.5;
  margin-bottom: 0.6rem;
}

.preset-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
}

.tag {
  font-size: 0.7rem;
  background: var(--bg-elevated, #1a1d27);
  color: var(--text-muted, #94a3b8);
  padding: 0.1rem 0.4rem;
  border-radius: 4px;
  border: 1px solid var(--border-default, #2a2d3a);
}

.tag-more {
  color: var(--color-accent, #6366f1);
  border-color: rgba(99, 102, 241, 0.3);
}

.preset-check-mark {
  position: absolute;
  top: 0.75rem;
  right: 0.75rem;
}

/* Review */
.review-box {
  background: var(--bg-primary, #0f1117);
  border: 1px solid var(--border-default, #2a2d3a);
  border-radius: 10px;
  padding: 1.25rem;
}

.review-row {
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--border-default, #2a2d3a);
  font-size: 0.875rem;
}

.review-row:last-child {
  border-bottom: none;
}

.review-label {
  color: var(--text-muted, #94a3b8);
  min-width: 90px;
  flex-shrink: 0;
}

.review-value {
  color: var(--text-primary, #e2e8f0);
}

/* Wizard footer */
.wizard-footer {
  display: flex;
  align-items: center;
  margin-top: 2rem;
  padding-top: 1.25rem;
  border-top: 1px solid var(--border-default, #2a2d3a);
  gap: 0.75rem;
}

.btn-primary {
  background: var(--color-accent, #6366f1);
  color: #fff;
  border: none;
  border-radius: 6px;
  padding: 0.5rem 1.25rem;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.15s;
  display: inline-flex;
  align-items: center;
}

.btn-primary:hover:not(:disabled) {
  opacity: 0.88;
}

.btn-primary:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.btn-secondary {
  background: transparent;
  color: var(--text-muted, #94a3b8);
  border: 1px solid var(--border-default, #2a2d3a);
  border-radius: 6px;
  padding: 0.5rem 1.25rem;
  font-size: 0.875rem;
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s;
  display: inline-flex;
  align-items: center;
}

.btn-secondary:hover:not(:disabled) {
  border-color: var(--color-accent, #6366f1);
  color: var(--text-primary, #e2e8f0);
}

.btn-secondary:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
