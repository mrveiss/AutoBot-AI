// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import { globalIgnores } from 'eslint/config'
import tseslint from 'typescript-eslint'
import pluginVue from 'eslint-plugin-vue'
import vueParser from 'vue-eslint-parser'

const tsRuleOverrides = {
  '@typescript-eslint/no-explicit-any': 'warn',
  '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
  'no-unused-vars': 'off',
  'no-undef': 'off',
}

// GH-13140 definition-of-done item 4 / GH-13079 — one transport client per
// (app, backend) pair.
//
// Unblocked once the last private transports were retired: the 53 SLM-backend
// and 17 autobot-backend raw `fetch` sites, and the five private `axios.create`
// instances in useSkills, useOrchestration, useOrchestrationManagement and
// useExternalAgents. Every one of them had diverged from its canonical client —
// missing token fallbacks, missing timeouts, swallowed 401s — so this rule
// exists to stop the next one appearing.
//
// ADR-008 decision rule 3 fixes the allowlist: `utils/ApiClient.ts` (SLM
// backend), `composables/useAutobotApi.ts` (autobot backend) and the
// `utils/slmApiCompat.ts` adapter over the former. Genuinely external targets
// (Prometheus, Grafana) carry an inline disable naming the service.
const NO_RAW_TRANSPORT = [
  {
    selector: "CallExpression[callee.name='fetch']",
    message:
      'Raw fetch() is not allowed here. Use slmApiClient (utils/ApiClient.ts) for the SLM backend, or useAutobotApi for the autobot backend - they own base-URL resolution, the bearer token fallback, the request timeout and 401 handling (ADR-008 rule 3).',
  },
  {
    selector: "CallExpression[callee.object.name='window'][callee.property.name='fetch']",
    message:
      'Raw window.fetch() is not allowed here. Use slmApiClient or useAutobotApi (ADR-008 rule 3).',
  },
  {
    selector: "CallExpression[callee.object.name='axios'][callee.property.name='create']",
    message:
      'A private axios instance re-implements a transport that already exists. Use slmApiClient / makeAxiosCompatClient for the SLM backend, or useAutobotApi for the autobot backend (ADR-008 rule 3).',
  },
]

/** Files that legitimately own a raw transport, plus the tests that stub one. */
const TRANSPORT_OWNERS = [
  'src/utils/ApiClient.ts',
  'src/utils/slmApiCompat.ts',
  'src/composables/useAutobotApi.ts',
  '**/*.test.ts',
  '**/*.spec.ts',
  '**/__tests__/**',
]

export default tseslint.config(
  {
    name: 'app/files-to-lint',
    files: ['**/*.{ts,mts,tsx,vue}'],
  },

  globalIgnores([
    '**/dist/**',
    '**/src/types/generated/**',
    '**/node_modules/**',
    '*.config.js',
    '*.config.ts',
    'postcss.config.*',
    'tailwind.config.*',
    'vite.config.*',
  ]),

  // Vue 3 essential rules
  ...pluginVue.configs['flat/essential'],

  // TypeScript recommended rules for .ts files
  ...tseslint.configs.recommended.map((config) => ({
    ...config,
    files: ['**/*.{ts,tsx}'],
  })),
  {
    files: ['**/*.{ts,tsx}'],
    rules: tsRuleOverrides,
  },

  // No raw transport outside the canonical clients.
  {
    name: 'app/no-raw-transport',
    files: ['src/**/*.{ts,tsx,vue}'],
    rules: {
      'no-restricted-syntax': ['error', ...NO_RAW_TRANSPORT],
    },
  },
  {
    name: 'app/no-raw-transport-owners',
    files: TRANSPORT_OWNERS,
    rules: {
      'no-restricted-syntax': 'off',
    },
  },

  // TypeScript rules for .vue files
  {
    files: ['**/*.vue'],
    plugins: {
      '@typescript-eslint': tseslint.plugin,
    },
    languageOptions: {
      parser: vueParser,
      parserOptions: {
        parser: tseslint.parser,
        ecmaVersion: 'latest',
        sourceType: 'module',
      },
    },
    rules: {
      ...tsRuleOverrides,
      'vue/multi-word-component-names': 'off',
      'no-console': 'error',
    },
  },
)
