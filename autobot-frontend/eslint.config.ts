import { globalIgnores } from 'eslint/config'
import { defineConfigWithVueTs, vueTsConfigs } from '@vue/eslint-config-typescript'
import pluginVue from 'eslint-plugin-vue'
import pluginVitest from '@vitest/eslint-plugin'
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore
import pluginCypress from 'eslint-plugin-cypress'
import pluginOxlint from 'eslint-plugin-oxlint'
import skipFormatting from '@vue/eslint-config-prettier/skip-formatting'

// To allow more languages other than `ts` in `.vue` files, uncomment the following lines:
// import { configureVueProject } from '@vue/eslint-config-typescript'
// configureVueProject({ scriptLangs: ['ts', 'tsx'] })
// More info at https://github.com/vuejs/eslint-config-typescript/#advanced-setup

export default defineConfigWithVueTs(
  {
    name: 'app/files-to-lint',
    files: ['**/*.{ts,mts,tsx,vue}'],
  },

  globalIgnores([
    '**/dist/**',
    '**/dist-ssr/**',
    '**/coverage/**',
    // Issue #6784: ESLint rule fixtures contain intentional rule violations
    // (deny.test.ts) and counter-examples (allow.test.ts). Excluded from
    // production lint; verify manually with `npx eslint --no-ignore eslint-tests/`.
    'eslint-tests/**',
  ]),

  pluginVue.configs['flat/essential'],
  vueTsConfigs.recommended,

  {
    ...pluginVitest.configs.recommended,
    files: ['src/**/__tests__/*'],
  },

  {
    ...pluginCypress.configs.recommended,
    files: [
      'cypress/e2e/**/*.{cy,spec}.{js,ts,jsx,tsx}',
      'cypress/support/**/*.{js,ts,jsx,tsx}'
    ],
  },
  {
    name: 'app/rule-overrides',
    rules: {
      '@typescript-eslint/no-explicit-any': 'warn',
      '@typescript-eslint/no-empty-object-type': 'warn',
      '@typescript-eslint/ban-ts-comment': 'warn',
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
      '@typescript-eslint/no-require-imports': 'warn',
      '@typescript-eslint/no-namespace': 'warn',
      '@typescript-eslint/no-unsafe-function-type': 'warn',
      'vue/block-lang': 'off',
      'vue/multi-word-component-names': 'off',
      'vue/no-deprecated-filter': 'warn',
      'vue/no-parsing-error': 'warn',
      'prefer-const': 'warn',
      'vue/no-undef-components': ['error', {
        ignorePatterns: ['RouterLink', 'RouterView', 'Transition', 'TransitionGroup', 'KeepAlive', 'Teleport', 'Suspense'],
      }],
      // Issue #6487: block new imports of deprecated useApi composable family.
      // Migrate to useFetchEndpoint (data loading) or useApiClient from @/plugins/api (mutations).
      'no-restricted-imports': [
        'error',
        {
          paths: [
            {
              name: '@/composables/useApi',
              message: 'useApi is deprecated (#6487). Use useFetchEndpoint from @/composables/api/useFetchEndpoint for data loading, or useApiClient() from @/plugins/api for imperative HTTP calls.',
            },
          ],
          patterns: [
            {
              group: ['*/composables/useApi'],
              message: 'useApi is deprecated (#6487). Use useFetchEndpoint from @/composables/api/useFetchEndpoint for data loading, or useApiClient() from @/plugins/api for imperative HTTP calls.',
            },
          ],
        },
      ],
      // Issue #6784: block hardcoded VM-IP fallbacks in `||` / `??` expressions
      // and any other literal/template containing the deployment range.
      // Use SSOT (window.location.hostname / VITE_*_HOST env vars) instead.
      // See docs/developer/HARDCODING_PREVENTION.md.
      'no-restricted-syntax': [
        'error',
        {
          selector: "Literal[value=/^(https?:\\/\\/)?172\\.16\\.168\\.[0-9]+/]",
          message: 'Hardcoded AutoBot VM IP (172.16.168.X) — use window.location.hostname or VITE_*_HOST env var (#6784).',
        },
        {
          selector: "TemplateElement[value.cooked=/172\\.16\\.168\\.[0-9]+/]",
          message: 'Hardcoded AutoBot VM IP in template literal — use window.location.hostname or VITE_*_HOST env var (#6784).',
        },
      ],
      // Issue #7085: forbid console.* in production code — use createLogger from @/utils/debugUtils instead.
      // Note: you cannot suppress this rule with eslint-disable-next-line — reportUnusedDisableDirectives blocks that too.
      'no-console': 'error',
      // MVA-192 design-token spec — Phase 4: block re-introduction of deprecated size/color tokens.
      // Use canonical tokens instead: size → sm|md|lg, danger → error.
      // See src/design-tokens/tokens.ts for the full token registry.
      'vue/no-restricted-static-attribute': [
        'error',
        { key: 'size', value: 'small',  message: "Deprecated size token 'small' — use 'sm' (MVA-192)." },
        { key: 'size', value: 'medium', message: "Deprecated size token 'medium' — use 'md' (MVA-192)." },
        { key: 'size', value: 'large',  message: "Deprecated size token 'large' — use 'lg' (MVA-192)." },
        { key: 'variant', value: 'danger', message: "Deprecated color token 'danger' — use 'error' (MVA-192)." },
      ],
      // Catches the same deprecated values passed as bound string literals, e.g. :size="'small'".
      // Scoped to VExpressionContainer inside VAttribute (template attribute expressions only).
      'vue/no-restricted-syntax': [
        'error',
        {
          selector: "VAttribute[directive=true] > VExpressionContainer > Literal[value='small']",
          message: "Deprecated size token 'small' — use 'sm' (MVA-192).",
        },
        {
          selector: "VAttribute[directive=true] > VExpressionContainer > Literal[value='medium']",
          message: "Deprecated size token 'medium' — use 'md' (MVA-192).",
        },
        {
          selector: "VAttribute[directive=true] > VExpressionContainer > Literal[value='large']",
          message: "Deprecated size token 'large' — use 'lg' (MVA-192).",
        },
        {
          selector: "VAttribute[directive=true] > VExpressionContainer > Literal[value='danger']",
          message: "Deprecated color token 'danger' — use 'error' (MVA-192).",
        },
      ],
    },
  },
  {
    name: 'app/console-allowed-in-debug-utils',
    files: [
      'src/utils/debugUtils.ts',
      'src/utils/RumConsoleHelper.ts',
      'src/utils/chunkTestUtility.ts',
    ],
    rules: {
      'no-console': 'off',
    },
  },
  {
    // Service workers run in a separate runtime context with no access to createLogger.
    name: 'app/console-allowed-in-service-worker',
    files: ['public/service-worker.ts', 'public/service-worker.js', 'public/sw-cache-bust.js'],
    rules: {
      'no-console': 'off',
    },
  },
  {
    // Build/check scripts and test fixtures run in Node.js, not the app bundle.
    name: 'app/console-allowed-in-scripts',
    files: ['scripts/**/*.{ts,js,mjs,mts}', 'scripts/**/__tests__/**'],
    rules: {
      'no-console': 'off',
    },
  },
  ...pluginOxlint.configs['flat/recommended'],
  skipFormatting,
)
