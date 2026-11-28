// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import i18n from '@/i18n'

/**
 * Set the browser tab title to "<page> - <product name>" (#19982).
 * The product name comes from the `common.appName` locale key, never a literal.
 */
export function setDocumentTitle(pageTitle: string): void {
  document.title = `${pageTitle} - ${i18n.global.t('common.appName')}`
}
