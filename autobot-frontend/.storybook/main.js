// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/** @type { import('@storybook/vue3-vite').StorybookConfig } */
const config = {
  stories: ['../src/**/*.stories.ts'],
  addons: [
    '@storybook/addon-docs',
  ],
  framework: {
    name: '@storybook/vue3-vite',
    options: {},
  },
  docs: {
    autodocs: 'tag',
  },
};
export default config;
