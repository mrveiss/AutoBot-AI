<template>
  <BaseBadge
    v-if="visible"
    variant="warning"
    size="sm"
    class="provider-fallback-chip"
    :title="tooltip"
  >
    <Icon name="exclamation-triangle" class="chip-icon" />
    {{ t('chat.message.fallback.badge') }}
  </BaseBadge>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Provider Fallback Chip (#11997 / umbrella #11994)
 *
 * Opt-in, off-by-default inline chip shown on an assistant message when the
 * primary LLM provider was unavailable and a fallback provider answered.
 * Gated behind the `showFallbackChip` display setting (default OFF), preserving
 * the platform's "invisible by default" fallback design intent (#11994).
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseBadge } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import { useDisplaySettings } from '@/composables/useDisplaySettings'
import type { ProviderFallbackPayload } from '@/constants/providerFallbackEvents'

interface Props {
  /** Fallback decision that produced this message, or `null` when none. */
  fallbackInfo?: ProviderFallbackPayload | null
}

const props = withDefaults(defineProps<Props>(), {
  fallbackInfo: null,
})

const { t } = useI18n()
const { getSetting } = useDisplaySettings()

/** Opt-in + present-fallback gate. Default OFF → chip hidden unless enabled. */
const visible = computed<boolean>(() => getSetting('showFallbackChip') && props.fallbackInfo != null)

const tooltip = computed<string>(() => {
  const info = props.fallbackInfo
  const primary = info?.primary_provider || info?.primary_model || t('common.unknown')
  const fallback = info?.fallback_provider || info?.fallback_model || t('common.unknown')
  return t('chat.message.fallback.tooltip', { primary, fallback })
})
</script>

<style scoped>
.provider-fallback-chip {
  margin-inline-start: var(--spacing-1-5);
  vertical-align: middle;
}

.chip-icon {
  margin-inline-end: var(--spacing-1);
}
</style>
