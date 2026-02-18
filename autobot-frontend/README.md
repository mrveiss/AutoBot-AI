# AutoBot User Frontend

> **Deploys to:** 172.16.168.20 (Main Server)

Vue 3 + TypeScript chat interface for AutoBot.

## Recommended IDE Setup

[VSCode](https://code.visualstudio.com/) + [Volar](https://marketplace.visualstudio.com/items?itemName=Vue.volar) (and disable Vetur).

## Type Support for `.vue` Imports in TS

TypeScript cannot handle type information for `.vue` imports by default, so we replace the `tsc` CLI with `vue-tsc` for type checking. In editors, we need [Volar](https://marketplace.visualstudio.com/items?itemName=Vue.volar) to make the TypeScript language service aware of `.vue` types.

## Customize configuration

See [Vite Configuration Reference](https://vite.dev/config/).

## Development

```bash
npm install
npm run dev
```

### Type-Check, Compile and Minify for Production

```bash
npm run build
```

### Run Unit Tests with [Vitest](https://vitest.dev/)

```bash
npm run test:unit
```

### Run End-to-End Tests with [Cypress](https://www.cypress.io/)

```bash
npm run test:e2e:dev
```

This runs the end-to-end tests against the Vite development server.
It is much faster than the production build.

But it's still recommended to test the production build with `test:e2e` before deploying (e.g. in CI environments):

```bash
npm run build
npm run test:e2e
```

### Lint with [ESLint](https://eslint.org/)

```bash
npm run lint
```

## Deployment

Synced to main server via:

```bash
./infrastructure/shared/scripts/sync-to-vm.sh main autobot-user-frontend/
```

## Infrastructure

Component-specific infrastructure is located at:

```text
infrastructure/autobot-user-frontend/
├── docker/      # Docker configurations
├── tests/       # Component-specific tests
├── config/      # Configuration files
├── scripts/     # Deployment scripts
└── templates/   # Service templates
```
