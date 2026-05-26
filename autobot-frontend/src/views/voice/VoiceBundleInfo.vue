<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!--
  VoiceBundleInfo.vue — read-only panel showing the user's active voice toolset bundle.
  GH#7422 — per-user voice toolset bundle + settings UI.
-->
<template>
  <div class="voice-bundle-info">
    <div v-if="loading" class="vbi-loading">
      <Icon name="sync-alt" :spin="true" />
      <span>Loading toolset…</span>
    </div>

    <div v-else-if="error" class="vbi-error">
      <Icon name="exclamation-circle" />
      <span>{{ error }}</span>
    </div>

    <div v-else-if="bundleInfo" class="vbi-content">
      <div class="vbi-label">Active toolset</div>
      <div class="vbi-value">
        <span class="vbi-bundle-name">{{ VOICE_BUNDLE_LABELS[bundleInfo.bundle_name] }}</span>
        <span class="vbi-tool-count">({{ bundleInfo.tool_count }} tools)</span>
      </div>
      <div class="vbi-resolution">
        Source:
        <span class="vbi-resolution-tag" :class="`vbi-res--${bundleInfo.resolution}`">
          {{ RESOLUTION_LABELS[bundleInfo.resolution] }}
        </span>
      </div>
    </div>

    <div v-else class="vbi-empty">
      <Icon name="microphone" />
      <span>No voice bundle assigned</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { inject, onMounted } from 'vue'
import Icon from '@/components/ui/Icon.vue'
import {
  useVoiceBundle,
  VOICE_BUNDLE_LABELS,
  VOICE_BUNDLE_STATE_KEY,
} from '@/composables/useVoiceBundle'
import type { VoiceBundleInjectedState } from '@/composables/useVoiceBundle'

const RESOLUTION_LABELS = {
  user_override: 'Admin override',
  role_default: 'Role default',
  global_env: 'System default',
} as const

const injected = inject<VoiceBundleInjectedState | null>(VOICE_BUNDLE_STATE_KEY, null)
const composable = injected === null ? useVoiceBundle() : null
const bundleInfo = injected?.bundleInfo ?? composable!.bundleInfo
const loading = injected?.loading ?? composable!.loading
const error = injected?.error ?? composable!.error

onMounted(() => {
  if (composable) composable.fetchMyBundle()
})
</script>

<style scoped>
.voice-bundle-info {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.vbi-loading,
.vbi-error,
.vbi-empty {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-sm);
  color: var(--color-text-secondary, #6b7280);
}

.vbi-error {
  color: var(--color-error, #dc2626);
}

.vbi-content {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-0-5);
}

.vbi-label {
  font-size: var(--text-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-secondary, #6b7280);
}

.vbi-value {
  display: flex;
  align-items: baseline;
  gap: var(--spacing-1-5);
}

.vbi-bundle-name {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--color-text, #111827);
}

.vbi-tool-count {
  font-size: var(--text-sm);
  color: var(--color-text-secondary, #6b7280);
}

.vbi-resolution {
  font-size: var(--text-xs);
  color: var(--color-text-secondary, #6b7280);
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
}

.vbi-resolution-tag {
  display: inline-block;
  padding: 1px var(--spacing-1-5);
  border-radius: var(--radius-full);
  font-size: 0.7rem;
  font-weight: 600;
}

.vbi-res--user_override {
  background: var(--color-warning-bg, #fffbeb);
  color: var(--color-warning, #d97706);
}

.vbi-res--role_default {
  background: var(--color-info-bg, #eff6ff);
  color: var(--color-info, #2563eb);
}

.vbi-res--global_env {
  background: var(--color-surface-alt, #f9fafb);
  color: var(--color-text-secondary, #6b7280);
}
</style>
