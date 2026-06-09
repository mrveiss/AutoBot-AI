// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import { createI18n } from 'vue-i18n'
import en from '@/locales/en.json'

const i18n = createI18n({
  legacy: true,
  locale: 'en',
  fallbackLocale: 'en',
  messages: { en },
})

export default i18n
