// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/* eslint-env node */
module.exports = {
  root: true,
  env: {
    browser: true,
    es2022: true,
    node: true,
  },
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:vue/vue3-essential',
  ],
  parser: 'vue-eslint-parser',
  parserOptions: {
    parser: '@typescript-eslint/parser',
    ecmaVersion: 'latest',
    sourceType: 'module',
  },
  plugins: ['@typescript-eslint'],
  ignorePatterns: [
    'dist/**',
    'node_modules/**',
    '*.config.js',
    '*.config.ts',
    'postcss.config.*',
    'tailwind.config.*',
    'vite.config.*',
  ],
  rules: {
    // Downgrade noisy rules to warnings
    '@typescript-eslint/no-explicit-any': 'warn',
    '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
    'vue/multi-word-component-names': 'off',
    'no-console': 'error',
    'no-unused-vars': 'off', // handled by @typescript-eslint/no-unused-vars
    // TypeScript handles undefined-variable checking; no-undef creates false
    // positives for DOM/TypeScript types like RequestInit, HTMLElement, etc.
    'no-undef': 'off',
  },
}
