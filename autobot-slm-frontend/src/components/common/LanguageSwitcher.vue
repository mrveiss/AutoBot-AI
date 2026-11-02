<script setup lang="ts">
// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * The SLM console's language picker (#14781): the kit's LanguageSwitcher
 * (#18354), bound to this app's i18n. The control, its endonym labels and its
 * styling are the kit's; this wrapper supplies the current locale, the
 * translated accessible label, and applies the choice through setLocale().
 */

import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { LanguageSwitcher, localeOptions } from '@autobot/ui'
import i18n, { SUPPORTED_LOCALES, setLocale } from '@/i18n'

const { t } = useI18n()

const current = computed(() => String(i18n.global.locale))
const options = computed(() => localeOptions(SUPPORTED_LOCALES))
</script>

<template>
  <div class="mb-2 slm-lang">
    <LanguageSwitcher
      :model-value="current"
      :options="options"
      :label="t('common.sidebar.languageLabel')"
      @update:model-value="setLocale"
    />
  </div>
</template>

<style scoped>
/* The sidebar is dark in every theme (Sidebar.vue bg-gray-900), so the kit
   control wears the sidebar's greys here -- the values the SLM select had. */
.slm-lang {
  --aui-color-surface: var(--slm-gray-800);
  --aui-color-text: var(--slm-gray-300);
  --aui-color-border: var(--slm-gray-700);
}
</style>
