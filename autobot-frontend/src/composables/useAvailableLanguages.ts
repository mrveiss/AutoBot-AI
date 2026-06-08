// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { computed } from 'vue'
import { SUPPORTED_LOCALES } from '@/i18n'

export interface AvailableLanguage {
  code: string
  name: string
}

export function useAvailableLanguages() {
  const languages = computed<AvailableLanguage[]>(() =>
    SUPPORTED_LOCALES.map(code => ({
      code,
      name: new Intl.DisplayNames([code], { type: 'language' }).of(code) ?? code
    }))
  )

  return { languages }
}
