// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
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

// #12363: one HTTP client. A raw fetch()/private axios instance re-implements the transport that
// ApiClient (over the kit's ApiClientBase) already owns -- base URL, bearer, timeout, retry, 401 policy.
// A site that must not use it (bootstrap before any client exists, another origin, a worker, telemetry
// that must never throw) carries `// eslint-disable-next-line no-restricted-syntax -- <reason>` at the
// call site, under a comment giving the reason (repo_tests/frontend_single_api_client_12363_test.py).
const NO_RAW_TRANSPORT = [
  {
    selector: "CallExpression[callee.name='fetch']",
    message:
      'Raw fetch() is not allowed here. Use apiClient.call(...) (utils/ApiClient.ts) for the AutoBot backend, or rawRequest/callRaw for streams and blobs - they own base-URL resolution, the bearer token, the timeout and 401 handling (#12363).',
  },
  {
    selector: "CallExpression[callee.object.name='window'][callee.property.name='fetch']",
    message: 'Raw window.fetch() is not allowed here. Use apiClient.call(...) or rawRequest/callRaw (#12363).',
  },
  {
    selector: "CallExpression[callee.object.name='axios'][callee.property.name='create']",
    message:
      'A private axios instance re-implements a transport that already exists. Use apiClient.call(...) (#12363).',
  },
]

const BASE_RESTRICTED_SYNTAX = [
  {
    selector: "Literal[value=/^(https?:\\/\\/)?172\\.16\\.168\\.[0-9]+/]",
    message: 'Hardcoded AutoBot VM IP (172.16.168.X) — use window.location.hostname or VITE_*_HOST env var (#6784).',
  },
  {
    selector: "TemplateElement[value.cooked=/172\\.16\\.168\\.[0-9]+/]",
    message: 'Hardcoded AutoBot VM IP in template literal — use window.location.hostname or VITE_*_HOST env var (#6784).',
  },
  {
    // (await ApiClient.<verb>(...)).json()  — `.json()` on a parsed result.
    selector:
      "CallExpression[callee.property.name='json'][callee.object.type='AwaitExpression'][callee.object.argument.type='CallExpression'][callee.object.argument.callee.type='MemberExpression'][callee.object.argument.callee.property.name=/^(get|post|put|delete|patch)$/][callee.object.argument.callee.object.name=/^([aA]pi|[aA]piClient)$/]",
    message:
      'ApiClient already returns parsed JSON — do not call .json() on its result (#10025). Use `const data = await ApiClient.get<T>(...)` directly.',
  },
  {
    // (await ApiClient.<verb>(...)).data  — axios-envelope `.data` access.
    selector:
      "MemberExpression[property.name='data'][object.type='AwaitExpression'][object.argument.type='CallExpression'][object.argument.callee.type='MemberExpression'][object.argument.callee.property.name=/^(get|post|put|delete|patch)$/][object.argument.callee.object.name=/^([aA]pi|[aA]piClient)$/]",
    message:
      'ApiClient returns parsed JSON, not an axios envelope — do not read .data on its result (#10025). The awaited value IS the payload.',
  },
]

export default defineConfigWithVueTs(
  {
    name: 'app/files-to-lint',
    files: ['**/*.{ts,mts,tsx,vue}'],
  },

  globalIgnores([
    '**/dist/**',
    '**/dist-ssr/**',
    '**/coverage/**',
    // #9693: Storybook build output is an untracked artifact (gitignored);
    // ignore it here too so local `npm run lint` matches CI.
    '**/storybook-static/**',
    // #9693: generated code is not hand-maintained; eslint --fix strips the
    // generator's /* eslint-disable */ banner, breaking the
    // frontend-codegen-drift sync check (#7122).
    'src/types/_generated/**',
    // Issue #6784: ESLint rule fixtures contain intentional rule violations
    // (deny.test.ts) and counter-examples (allow.test.ts). Excluded from
    // production lint; verify manually with `npx eslint --no-ignore eslint-tests/`.
    'eslint-tests/**',
    // #17571: canonical-rule fixtures hold deliberate violations (unused
    // imports the rule must detect); the rule's own tests read them.
    'scripts/canonical/__tests__/fixtures/**',
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
        ignorePatterns: ['RouterLink', 'RouterView', 'Transition', 'TransitionGroup', 'KeepAlive', 'Teleport', 'Suspense', 'I18nT', 'i18n-t'],
      }],
      // Issue #6784: block hardcoded VM-IP fallbacks in `||` / `??` expressions
      // and any other literal/template containing the deployment range.
      // Use SSOT (window.location.hostname / VITE_*_HOST env vars) instead.
      // See docs/developer/HARDCODING_PREVENTION.md.
      //
      // Issue #10025: guard against ApiClient envelope misuse. The canonical
      // ApiClient (`ApiClient.*` / the `useApiClient()` result, conventionally
      // named `api` or `apiClient`) returns PARSED JSON directly — it is NOT a
      // fetch `Response` and NOT an axios envelope. Calling `.json()` on the
      // result throws `TypeError: .json is not a function`; reading `.data`
      // yields `undefined`. This class has caused 40+ runtime bugs (latest
      // #10013). See docs feedback "ApiClient.X returns parsed JSON directly".
      //
      // We flag the INLINE awaited-then-membered forms only:
      //   (await ApiClient.get(...)).json()   and   (await ApiClient.get(...)).data
      // (and the same for `api.*` / `apiClient.*`). The TWO-STATEMENT form
      //   const r = await ApiClient.get(...); r.json()
      // cannot be caught syntactically without type information and is NOT
      // covered here — a typed rule would be required (tracked for follow-up if
      // it recurs). The selectors are deliberately tight (callee identifier must
      // be `api`/`apiClient`/`ApiClient`, method must be an HTTP verb) so they
      // never fire on a real `fetch`/`rawRequest` Response `.json()`, nor on
      // legitimate `.data` of Pinia state, refs, chart configs, or event
      // payloads, nor on the two-statement `payload.data` pattern.
      'no-restricted-syntax': ['error', ...NO_RAW_TRANSPORT, ...BASE_RESTRICTED_SYNTAX],
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
        // NOTE: no `variant: danger` entry — #11998 reconciled the shared SemanticVariant/BadgeVariant
        // vocabulary TO canonical 'danger' (BaseBadge accepts 'danger', not 'error'), so forbidding it
        // here contradicts the component type. ButtonVariant still uses 'error' (its own type enforces it).
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
    // Tests stub and call fetch directly; fetchWithAuth.ts is the bridge slice 3 of #12363 retires; service workers
    // run in their own context with no access to the app's client; build/check scripts run in Node.
    name: 'app/raw-transport-owners',
    files: [
      'src/utils/fetchWithAuth.ts',
      '**/*.test.ts',
      '**/*.spec.ts',
      '**/__tests__/**',
      'public/service-worker.ts',
      'public/service-worker.js',
      'public/sw-cache-bust.js',
      'scripts/**/*.{ts,js,mjs,mts}',
    ],
    rules: {
      'no-restricted-syntax': ['error', ...BASE_RESTRICTED_SYNTAX],
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
