// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { setup, type Preview } from '@storybook/vue3';
// The app's global stylesheets, the same list main.ts loads (#18687).
import '../src/assets/global-styles';
// The app's own i18n instance, not a second one (#18694): components that call
// `$t`/`useI18n` rendered Storybook's error page without it.
import i18n, { setLocale } from '../src/i18n';
import { createMemoryHistory, createRouter } from 'vue-router';
import { routes } from '../src/router';
import { createPinia } from 'pinia';

// The app's own route records on a memory history (#18694). Components that call
// useRoute()/useRouter() or render <RouterLink :to="{ name }"> crashed without a router,
// and a named link only resolves against the real records. The app's router instance and
// its auth guards stay in main.ts: a story renders its component, it does not navigate.
const router = createRouter({ history: createMemoryHistory(), routes });

setup((app) => {
  app.use(i18n);
  app.use(router);
  // Stores need an active Pinia (#18694). Unlike main.ts it is NOT persisted: a store
  // restored from localStorage would carry one story's state into the next screenshot.
  app.use(createPinia());
});

const preview: Preview = {
  tags: ['autodocs'],
  // English, whatever the browser's locale: stories are visual-regression subjects,
  // and the app loads messages lazily, so they must be loaded before rendering.
  loaders: [
    async () => {
      await setLocale('en');
      return {};
    },
  ],
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
