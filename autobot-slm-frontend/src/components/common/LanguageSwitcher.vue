<script setup lang="ts">
// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Language switcher for the SLM console (#14781).
 *
 * The console shipped eleven locales' worth of strings and no way to reach ten
 * of them. This is the control that makes them reachable.
 *
 * Each language is labelled in ITS OWN language, which is why the names below
 * are a static map rather than `$t(...)` keys: a user who has landed in a
 * language they cannot read needs to find their own in a list, and translating
 * "German" into German ("Deutsch") is the same string in every locale. That is
 * the one place in this app where a literal is the correct answer.
 *
 * They need no exemption from
 * `repo_tests/slm_frontend_bare_ui_literals_test.py`: that guard reads TEMPLATE
 * text and attributes, and these are script-block data rendered through
 * `{{ option.label }}`. Said explicitly because "the guard does not see it" and
 * "the guard permits it" are different facts, and only the first is true here.
 */

import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import i18n, { SUPPORTED_LOCALES, setLocale } from '@/i18n'

const { t } = useI18n()

/** Endonyms — each language named as its own speakers write it. */
const LOCALE_NAMES: Record<string, string> = {
  ar: 'العربية',
  de: 'Deutsch',
  en: 'English',
  es: 'Español',
  fa: 'فارسی',
  fr: 'Français',
  he: 'עברית',
  lv: 'Latviešu',
  pl: 'Polski',
  pt: 'Português',
  ur: 'اردو',
}

const current = computed(() => String(i18n.global.locale))

const options = computed(() =>
  SUPPORTED_LOCALES.map((code) => ({ code, label: LOCALE_NAMES[code] ?? code })),
)

function onChange(event: Event): void {
  setLocale((event.target as HTMLSelectElement).value)
}
</script>

<template>
  <div class="mb-2">
    <label
      for="slm-language-switcher"
      class="sr-only"
    >{{ t('common.sidebar.languageLabel') }}</label>
    <select
      id="slm-language-switcher"
      :value="current"
      :aria-label="t('common.sidebar.languageLabel')"
      class="w-full px-3 py-2 text-sm text-gray-300 bg-gray-800 border border-gray-700 rounded-lg hover:text-white focus:outline-none focus:ring-2 focus:ring-primary-500"
      @change="onChange"
    >
      <option
        v-for="option in options"
        :key="option.code"
        :value="option.code"
      >
        {{ option.label }}
      </option>
    </select>
  </div>
</template>
