# AutoBot Browser Worker

> **Deploys to:** 172.16.168.25 (Browser VM)

Playwright-based browser automation worker.

## Status

**Stub** - Browser automation code will be extracted from main backend in a future phase.

## Deployment

```bash
./infrastructure/shared/scripts/sync-to-vm.sh browser autobot-browser-worker/
```

## Infrastructure

Component-specific infrastructure is located at:

```text
infrastructure/autobot-browser-worker/
├── docker/      # Docker configurations
├── tests/       # Component-specific tests
├── config/      # Configuration files
├── scripts/     # Deployment scripts
└── templates/   # Service templates
```

## Testing

`npm test` runs the package's own suite with `node:test`, gated in CI by
`.github/workflows/npm-package-tests.yml` (#15675).

There is deliberately **no Playwright config here**. One used to sit in this
directory and was retired in #15695: it had never been loadable from this
package. Its `globalSetup` resolved `./tests/setup/global-setup.js`, which does
not exist here — `require.resolve` throws while the config is being read, so
Playwright could not even start. Its `webServer.cwd` pointed at `autobot-vue`,
a directory absent from the repository, and its viewport probe shelled into
`src/utils/display_utils`, which this package does not have either.

It arrived as a stray copy during the root-folder reorganisation in #781. The
copy it was separated from still exists and still has its setup file:
`autobot-infrastructure/shared/tests/playwright.config.js`. Browser-level
configuration belongs there, not beside a worker whose job is to *serve*
Playwright over a socket rather than be driven by it.

