<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<template>
  <div class="connection-settings-panel">
    <div class="panel-header">
      <h3 class="text-sm font-semibold text-autobot-text-primary">{{ $t('desktop.connectionSettings.title') }}</h3>
    </div>

    <div v-if="error" class="error-message">
      {{ error }}
    </div>

    <div v-else-if="settings" class="settings-content">
      <!-- Quality Presets -->
      <div class="presets-section">
        <label class="text-xs text-autobot-text-secondary mb-2 block">{{ $t('desktop.connectionSettings.qualityPreset') }}</label>
        <div class="preset-buttons">
          <button
            v-for="preset in presets"
            :key="preset.value"
            @click="setPreset(preset.value)"
            :class="['preset-btn', { 'active': isActivePreset(preset.value) }]"
          >
            {{ preset.label }}
          </button>
        </div>
        <p class="text-xs text-autobot-text-muted mt-2">
          {{ presetDescription }}
        </p>
      </div>

      <!-- Auto-Reconnect -->
      <div class="reconnect-section">
        <label class="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            v-model="settings.auto_reconnect"
            @change="saveSettings"
            class="checkbox"
          />
          <span class="text-sm text-autobot-text-primary">{{ $t('desktop.connectionSettings.autoReconnect') }}</span>
        </label>
        <div v-if="settings.auto_reconnect" class="reconnect-details">
          <div class="detail-item">
            <span class="text-xs text-autobot-text-secondary">{{ $t('desktop.connectionSettings.delay') }}</span>
            <span class="text-xs text-autobot-text-primary">{{ settings.reconnect_delay_ms }}ms</span>
          </div>
          <div class="detail-item">
            <span class="text-xs text-autobot-text-secondary">{{ $t('desktop.connectionSettings.maxAttempts') }}</span>
            <span class="text-xs text-autobot-text-primary">{{ settings.max_reconnect_attempts }}</span>
          </div>
        </div>
      </div>

      <!-- Connection Metrics -->
      <div v-if="metrics" class="metrics-section">
        <h4 class="text-xs font-semibold text-autobot-text-primary mb-2">{{ $t('desktop.connectionSettings.connectionStatus') }}</h4>
        <div class="metrics-grid">
          <div class="metric-item">
            <span class="metric-label">{{ $t('desktop.connectionSettings.vncServer') }}</span>
            <span :class="['metric-value', metrics.vnc_running ? 'text-green-600' : 'text-red-600']">
              {{ metrics.vnc_running ? $t('desktop.connectionSettings.running') : $t('desktop.connectionSettings.stopped') }}
            </span>
          </div>
          <div v-if="metrics.latency_ms" class="metric-item">
            <span class="metric-label">{{ $t('desktop.connectionSettings.latency') }}</span>
            <span class="metric-value">{{ metrics.latency_ms.toFixed(1) }}ms</span>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="loading-state">
      {{ $t('desktop.connectionSettings.loading') }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useVncConnection } from '@/composables/useVncConnection'

const { t } = useI18n()
const { loading, error, settings, metrics, loadSettings, updateSettings, loadMetrics, setQualityPreset } = useVncConnection()

const presets = computed(() => [
  { value: 'low' as const, label: t('desktop.connectionSettings.presetLow'), desc: t('desktop.connectionSettings.presetLowDesc') },
  { value: 'medium' as const, label: t('desktop.connectionSettings.presetMedium'), desc: t('desktop.connectionSettings.presetMediumDesc') },
  { value: 'high' as const, label: t('desktop.connectionSettings.presetHigh'), desc: t('desktop.connectionSettings.presetHighDesc') },
  { value: 'best' as const, label: t('desktop.connectionSettings.presetBest'), desc: t('desktop.connectionSettings.presetBestDesc') }
])

const currentPreset = ref<'low' | 'medium' | 'high' | 'best'>('medium')

const presetDescription = computed(() => {
  return presets.value.find(p => p.value === currentPreset.value)?.desc || ''
})

function isActivePreset(preset: string): boolean {
  return preset === currentPreset.value
}

async function setPreset(preset: 'low' | 'medium' | 'high' | 'best') {
  currentPreset.value = preset
  await setQualityPreset(preset)
}

async function saveSettings() {
  if (settings.value) {
    await updateSettings(settings.value)
  }
}

onMounted(async () => {
  await loadSettings()
  await loadMetrics()

  // Auto-refresh metrics every 10 seconds
  setInterval(loadMetrics, 10000)
})
</script>

<style scoped>
.connection-settings-panel {
  @apply bg-autobot-bg-secondary rounded-lg border border-autobot-border p-4;
}

.panel-header {
  @apply mb-4 pb-2 border-b border-autobot-border;
}

.error-message {
  @apply text-sm text-red-600 p-2 bg-red-50 rounded;
}

.loading-state {
  @apply text-sm text-autobot-text-muted text-center py-4;
}

.settings-content {
  @apply space-y-4;
}

.presets-section {
  @apply space-y-2;
}

.preset-buttons {
  @apply grid grid-cols-4 gap-2;
}

.preset-btn {
  @apply px-2 py-1.5 text-xs font-medium rounded border transition-colors;
  @apply bg-autobot-bg-tertiary border-autobot-border;
  @apply text-autobot-text-primary;
  @apply hover:bg-autobot-bg-secondary;
}

.preset-btn.active {
  @apply bg-blue-600 border-blue-600 text-white;
  @apply hover:bg-blue-700;
}

.reconnect-section {
  @apply space-y-2 pt-2 border-t border-autobot-border;
}

.checkbox {
  @apply w-4 h-4 text-blue-600 rounded;
}

.reconnect-details {
  @apply ml-6 space-y-1;
}

.detail-item {
  @apply flex items-center justify-between;
}

.metrics-section {
  @apply pt-2 border-t border-autobot-border;
}

.metrics-grid {
  @apply space-y-1.5;
}

.metric-item {
  @apply flex items-center justify-between text-xs;
}

.metric-label {
  @apply text-autobot-text-secondary;
}

.metric-value {
  @apply font-mono;
}
</style>
