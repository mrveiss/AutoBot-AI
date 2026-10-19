<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  AdditionalThemesGroup — the "Additional themes" group of ThemePresetPicker
  (#18240). Lists the theme packages an administrator deployed through the SLM
  (the installed-theme registry, via useThemeVariant), each with a "Deployed
  via SLM" badge, and links to the SLM console where they are managed. The
  built-in Default / Ember variants stay in EmberThemeToggle; this group holds
  only deployed ones, so no theme is offered twice.
-->
<template>
  <div class="mt-5 space-y-3 border-t border-autobot-border pt-4" data-testid="additional-themes">
    <div class="flex flex-wrap items-center gap-2">
      <h4 id="additional-themes-title" class="flex-1 text-sm font-semibold text-autobot-text-primary">{{ $t('settings.additionalThemes.title') }}</h4>
      <span class="text-sm text-autobot-text-secondary">{{ $t('settings.additionalThemes.subtitle') }}</span>
    </div>

    <div v-if="installedThemes.length > 0" class="grid gap-3 sm:grid-cols-2" role="group" aria-labelledby="additional-themes-title">
      <button
        v-for="item in installedThemes"
        :key="item.id"
        type="button"
        :class="[cardClass, themeVariant === item.id ? 'border-autobot-primary bg-autobot-primary-bg' : 'border-autobot-border hover:bg-autobot-bg-tertiary']"
        :aria-pressed="themeVariant === item.id"
        :data-testid="`additional-theme-${item.id}`"
        @click="pick(item.id, item.name)"
      >
        <span class="font-semibold text-autobot-text-primary">{{ item.name }}</span>
        <span class="text-sm text-autobot-text-secondary">{{ item.author }}</span>
        <BaseBadge variant="neutral" size="sm" tone="solid" class="self-start">{{ $t('settings.additionalThemes.deployed', { version: item.version }) }}</BaseBadge>
      </button>
    </div>
    <p v-else class="text-sm text-autobot-text-secondary">{{ $t('settings.additionalThemes.empty') }}</p>

    <div class="flex flex-wrap items-center gap-3 rounded-lg bg-autobot-info-bg px-3 py-2.5 text-sm text-autobot-info">
      <span class="min-w-48 flex-1">{{ $t('settings.additionalThemes.info') }}</span>
      <a :href="slmSettingsUrl" target="_blank" rel="noopener noreferrer" class="font-semibold underline underline-offset-2">{{ $t('settings.additionalThemes.slmLink') }}</a>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseBadge, useAnnounce } from '@autobot/ui'
import { getSLMAdminUrl } from '@/config/ssot-config'
import { useThemeVariant } from '@/composables/useThemeVariant'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('AdditionalThemesGroup')
const { t } = useI18n()
const { announce } = useAnnounce()
const { themeVariant, installedThemes, setThemeVariant } = useThemeVariant()

const cardClass =
  'flex flex-col items-start gap-1 rounded-lg border p-3 text-start transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-autobot-primary'

// The SLM console has no dedicated Themes screen route yet, so this opens its
// Settings area, where deployed themes are managed.
const slmSettingsUrl = computed(() => `${getSLMAdminUrl()}/settings`)

async function pick(id: string, name: string): Promise<void> {
  try {
    await setThemeVariant(id)
    announce(t('ui.themeToggle.presetChanged', { name }))
  } catch (error) {
    logger.warn(`Deployed theme '${id}' could not be applied`, error)
  }
}
</script>
