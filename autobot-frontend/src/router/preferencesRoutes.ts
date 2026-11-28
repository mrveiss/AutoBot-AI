// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Preferences routes: Settings itself and the provider sign-in callback it owns.
 * Split out of router/index.ts, which is over the 600-line limit (#19241).
 */
import type { RouteRecordRaw } from 'vue-router'
import { PROVIDER_OAUTH_CALLBACK_PATH, PROVIDER_OAUTH_SETTINGS_PATH } from '@/utils/providerOAuth'

export const preferencesRoutes: RouteRecordRaw[] = [
  // Issue #753: User preferences (appearance, font size, colors, etc.)
  {
    path: PROVIDER_OAUTH_SETTINGS_PATH,
    name: 'preferences',
    component: () => import('@/views/SettingsView.vue'),
    meta: {
      title: 'Preferences',
      icon: 'fas fa-cog',
      description: 'Customize your AutoBot experience',
      requiresAuth: true,
      hideInNav: true,
    },
  },
  // #19241: the provider's sign-in redirect lands here with ?code=..&state=..
  {
    path: PROVIDER_OAUTH_CALLBACK_PATH,
    name: 'provider-oauth-callback',
    component: () => import('@/views/ProviderOAuthCallbackView.vue'),
    meta: { title: 'Provider sign-in', requiresAuth: true, hideInNav: true },
  },
]
