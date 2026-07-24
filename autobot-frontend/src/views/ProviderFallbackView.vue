<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  AutoBot - AI-Powered Automation Platform
  Author: mrveiss

  Always-on provider-fallback observability panel (admin) — #11996 / #11994.

  Surfaces the provider-routing decision path AutoBot previously hid:
    - Current state (reload-safe) from GET /api/llm/fallback-status: which
      conversations are on a fallback model, and the configured chains.
    - Live PROVIDER_FALLBACK events (#11995) on the global channel, appended to
      a capped timeline so ops sees fallback/exhaustion the moment it happens.
-->
<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
import { useProviderFallbackApi } from '@/composables/useProviderFallbackApi'
import type {
  ActiveFallbackEntry,
  ConfiguredFallbackChain,
  ProviderFallbackPayload,
} from '@/constants/providerFallbackEvents'

const { fetchFallbackStatus, subscribeToFallbackEvents } = useProviderFallbackApi()

// Cap the live timeline so a busy fallback storm can't grow the DOM unbounded.
const MAX_TIMELINE = 50

const loading = ref(false)
const configuredChains = ref<ConfiguredFallbackChain[]>([])
const activeFallbacks = ref<ActiveFallbackEntry[]>([])
const timeline = ref<ProviderFallbackPayload[]>([])

const hasActive = computed(() => activeFallbacks.value.length > 0)
const noData = computed(
  () =>
    !loading.value &&
    activeFallbacks.value.length === 0 &&
    configuredChains.value.length === 0 &&
    timeline.value.length === 0,
)

function formatTimestamp(seconds: number): string {
  if (!Number.isFinite(seconds)) return '—'
  return new Date(seconds * 1000).toLocaleString()
}

async function refresh(): Promise<void> {
  loading.value = true
  const status = await fetchFallbackStatus()
  configuredChains.value = status.configured_chains
  activeFallbacks.value = status.active_fallbacks
  loading.value = false
}

let unsubscribe: (() => void) | null = null

onMounted(() => {
  refresh()
  unsubscribe = subscribeToFallbackEvents((payload) => {
    timeline.value = [payload, ...timeline.value].slice(0, MAX_TIMELINE)
    // A live event means state changed — refresh the reload-safe view too.
    refresh()
  })
})

onUnmounted(() => {
  if (unsubscribe) unsubscribe()
  unsubscribe = null
})
</script>

<template>
  <div class="provider-fallback">
    <!-- Header -->
    <div class="pf-header">
      <div>
        <h1 class="pf-title">{{ $t('admin.providerFallback.title') }}</h1>
        <p class="pf-subtitle">{{ $t('admin.providerFallback.subtitle') }}</p>
      </div>
      <button class="pf-refresh" :disabled="loading" @click="refresh">
        {{ $t('admin.providerFallback.refresh') }}
      </button>
    </div>

    <!-- Overall state -->
    <div class="pf-state">
      <span class="pf-label">{{ $t('admin.providerFallback.status') }}</span>
      <BaseBadge :variant="hasActive ? 'warning' : 'success'" size="md">
        {{
          hasActive
            ? $t('admin.providerFallback.stateDegraded')
            : $t('admin.providerFallback.stateHealthy')
        }}
      </BaseBadge>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="pf-empty">
      {{ $t('admin.providerFallback.loading') }}
    </div>

    <!-- Empty -->
    <div v-else-if="noData" class="pf-empty">
      {{ $t('admin.providerFallback.noData') }}
    </div>

    <template v-else>
      <!-- Active fallbacks (reload-safe, from the read API) -->
      <section v-if="hasActive" class="pf-section">
        <h2 class="pf-section-title">{{ $t('admin.providerFallback.active') }}</h2>
        <div class="pf-cards">
          <div
            v-for="entry in activeFallbacks"
            :key="entry.conversation_id"
            class="pf-card"
          >
            <div class="pf-card-head">
              <span class="pf-conv">{{ entry.conversation_id }}</span>
              <span class="pf-time">{{ formatTimestamp(entry.timestamp) }}</span>
            </div>
            <div class="pf-hop">
              <BaseBadge variant="neutral" size="sm" monospace>
                {{ entry.primary_provider }}/{{ entry.primary_model }}
              </BaseBadge>
              <span class="pf-arrow" aria-hidden="true">→</span>
              <BaseBadge variant="warning" size="sm" monospace>
                {{ entry.fallback_provider }}/{{ entry.fallback_model }}
              </BaseBadge>
            </div>
          </div>
        </div>
      </section>

      <!-- Configured chains -->
      <section v-if="configuredChains.length" class="pf-section">
        <h2 class="pf-section-title">{{ $t('admin.providerFallback.chains') }}</h2>
        <div class="pf-cards">
          <div
            v-for="chain in configuredChains"
            :key="chain.primary_model"
            class="pf-card"
          >
            <div class="pf-card-head">
              <BaseBadge variant="primary" size="sm" monospace>
                {{ chain.primary_model }}
              </BaseBadge>
              <span class="pf-provider">{{ chain.provider }}</span>
            </div>
            <div class="pf-chain">{{ chain.fallback_chain }}</div>
          </div>
        </div>
      </section>

      <!-- Live timeline (PROVIDER_FALLBACK events) -->
      <section v-if="timeline.length" class="pf-section">
        <h2 class="pf-section-title">{{ $t('admin.providerFallback.timeline') }}</h2>
        <ul class="pf-timeline">
          <li v-for="(ev, idx) in timeline" :key="`${ev.conversation_id}-${idx}`" class="pf-event">
            <BaseBadge :variant="ev.exhausted ? 'danger' : 'warning'" size="sm">
              {{
                ev.exhausted
                  ? $t('admin.providerFallback.exhausted')
                  : $t('admin.providerFallback.switched')
              }}
            </BaseBadge>
            <span class="pf-event-body">
              <span class="pf-conv">{{ ev.conversation_id }}</span>
              <span class="pf-event-hop">
                {{ ev.primary_model }} → {{ ev.fallback_model || $t('admin.providerFallback.none') }}
              </span>
              <span class="pf-reason">{{ ev.reason }}</span>
            </span>
            <span class="pf-time">{{ formatTimestamp(ev.timestamp) }}</span>
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>

<style scoped>
.provider-fallback {
  max-width: 64rem;
  margin: 0 auto;
  padding: var(--spacing-6);
}

.pf-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-6);
}

.pf-title {
  font-size: var(--text-2xl);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.pf-subtitle {
  margin-top: var(--spacing-1);
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

.pf-refresh {
  padding: var(--spacing-2) var(--spacing-4);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  background-color: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background-color var(--duration-150) var(--ease-out);
}

.pf-refresh:hover:not(:disabled) {
  background-color: var(--bg-tertiary);
}

.pf-refresh:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.pf-state {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-4);
  margin-bottom: var(--spacing-6);
  background-color: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
}

.pf-label {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--text-secondary);
}

.pf-empty {
  padding: var(--spacing-12) var(--spacing-4);
  text-align: center;
  color: var(--text-tertiary);
  font-size: var(--text-sm);
}

.pf-section {
  margin-bottom: var(--spacing-6);
}

.pf-section-title {
  margin-bottom: var(--spacing-3);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-tertiary);
}

.pf-cards {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.pf-card {
  padding: var(--spacing-4);
  background-color: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
}

.pf-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-2);
}

.pf-conv {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.pf-time {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  white-space: nowrap;
}

.pf-provider {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.pf-hop {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--spacing-2);
}

.pf-arrow {
  color: var(--text-tertiary);
}

.pf-chain {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.pf-timeline {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
  list-style: none;
  margin: 0;
  padding: 0;
}

.pf-event {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-3) var(--spacing-4);
  background-color: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
}

.pf-event-body {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--spacing-2);
  flex: 1;
  min-width: 0;
}

.pf-event-hop {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.pf-reason {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}
</style>
