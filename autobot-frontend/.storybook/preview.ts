// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Preview } from '@storybook/vue3';
// The app's global stylesheets, the same list main.ts loads (#18687).
import '../src/assets/global-styles';

const preview: Preview = {
  tags: ['autodocs'],
  parameters: {
    actions: { argTypesRegex: '^on[A-Z].*' },
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
  },
};

export default preview;
