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

export default tseslint.config(
  {
    name: 'app/files-to-lint',
    files: ['**/*.{ts,mts,tsx,vue}'],
  },

  globalIgnores([
    '**/dist/**',
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
