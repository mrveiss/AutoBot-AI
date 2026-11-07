<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025-2026 mrveiss -->
<!--
  Cloud ASR (speech-to-text) provider selector (#10147c).

  Lets the user pick which cloud provider transcribes recordings. Only
  backend-configured providers (server-side API key present) are selectable;
  unconfigured providers are shown disabled with a "not configured" badge so
  the operator knows a key is required server-side.

  Privacy: selecting a cloud provider means audio leaves the box. This is
  opt-in — the local pipeline remains the default when nothing is selected.
-->
<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseButton } from '@autobot/ui'
import {
  useTranscriberApi,
  type AsrProvider,
} from '@/composables/transcriber/useTranscriberApi'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('AsrProviderSelector')

const { t } = useI18n()
const api = useTranscriberApi()

// #20671: a request settled after the panel unmounted must not write to (or
// log against) a component that is gone.
let unmounted = false
onBeforeUnmount(() => {
  unmounted = true
})

const providers = ref<AsrProvider[]>([])
const selected = ref<string | null>(null)
const loading = ref(false)
const saving = ref(false)
// loadError replaces the control (nothing to show); saveError is shown inline
// while keeping the control usable so the user can retry the selection.
const loadError = ref('')
const saveError = ref('')

async function load(): Promise<void> {
  loading.value = true
  loadError.value = ''
  try {
    const res = await api.listAsrProviders()
    if (unmounted) return
    providers.value = res.providers
    selected.value = res.selected
  } catch (err) {
    if (unmounted) return
    loadError.value = err instanceof Error ? err.message : String(err)
    logger.error('Failed to load ASR providers', err)
  } finally {
    if (!unmounted) loading.value = false
  }
}

async function onSelect(event: Event): Promise<void> {
  const next = (event.target as HTMLSelectElement).value
  const previous = selected.value
  if (next === previous) return

  // Optimistic update — revert on failure.
  selected.value = next
  saving.value = true
  saveError.value = ''
  try {
    await api.setAsrProvider(next)
  } catch (err) {
    if (unmounted) return
    selected.value = previous
    saveError.value = err instanceof Error ? err.message : String(err)
    logger.error('Failed to set ASR provider', err)
  } finally {
    if (!unmounted) saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="asr-selector" aria-labelledby="asr-selector-heading">
    <h3 id="asr-selector-heading" class="asr-selector-heading">{{ t('transcriber.asr.heading') }}</h3>
    <p class="asr-selector-help">{{ t('transcriber.asr.help') }}</p>

    <div v-if="loading" class="asr-selector-state">{{ t('transcriber.asr.loading') }}</div>

    <div v-else-if="loadError" class="asr-selector-state asr-selector-error" role="alert">
      {{ loadError }}
      <BaseButton size="sm" @click="load">{{ t('common.retry') }}</BaseButton>
    </div>

    <div v-else-if="providers.length === 0" class="asr-selector-state">
      {{ t('transcriber.asr.empty') }}
    </div>

    <div v-else class="asr-selector-control">
      <label class="asr-selector-label" for="asr-provider-select">{{ t('transcriber.asr.activeProvider') }}</label>
      <select
        id="asr-provider-select"
        class="input asr-selector-dropdown"
        :value="selected ?? ''"
        :disabled="saving"
        @change="onSelect"
      >
        <option value="" disabled>{{ t('transcriber.asr.selectPlaceholder') }}</option>
        <option
          v-for="p in providers"
          :key="p.id"
          :value="p.id"
          :disabled="!p.configured"
        >
          {{ p.configured ? p.name : t('transcriber.asr.optionNotConfigured', { name: p.name }) }}
        </option>
      </select>
      <span v-if="saving" class="asr-selector-saving">{{ t('transcriber.asr.saving') }}</span>
      <p v-if="saveError" class="asr-selector-error asr-selector-help" role="alert">{{ saveError }}</p>

      <ul class="asr-selector-list">
        <li v-for="p in providers" :key="p.id" class="asr-selector-list-item">
          <span class="asr-selector-name">{{ p.name }}</span>
          <span v-if="!p.configured" class="asr-selector-badge">{{ t('transcriber.asr.notConfigured') }}</span>
        </li>
      </ul>
      <p v-if="providers.some((p) => !p.configured)" class="asr-selector-help asr-selector-help-muted">
        {{ t('transcriber.asr.notConfiguredHelp') }}
      </p>
    </div>
  </section>
</template>

<style scoped>
.asr-selector {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: var(--card-padding, 1rem);
  background: var(--bg-card, var(--bg-surface));
  border: 1px solid var(--border-default);
  border-radius: var(--card-radius, var(--radius-md));
}

.asr-selector-heading {
  margin: 0;
  font-size: var(--text-lg);
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.asr-selector-help {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.asr-selector-help-muted {
  color: var(--text-muted, var(--text-tertiary));
}

.asr-selector-state {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.asr-selector-error {
  color: var(--color-error, var(--color-error));
}

.asr-selector-control {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.asr-selector-label {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.asr-selector-dropdown {
  max-width: 24rem;
}

.asr-selector-saving {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.asr-selector-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.asr-selector-list-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.asr-selector-badge {
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  color: var(--color-warning);
  border: 1px solid var(--color-warning);
  border-radius: var(--radius-full, 9999px);
  padding: 0.05rem 0.5rem;
}
</style>
