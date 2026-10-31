# @autobot/slm-contract

The SLM backend's API contract as TypeScript types, shared by `autobot-frontend` and
`autobot-slm-frontend` (ADR 011, #19834).

- `src/generated/api.ts`: generated from the SLM OpenAPI schema. Never hand-edit; regenerate with
  `npm run gen:types:openapi && npm run gen:types` in `autobot-slm-frontend`
  (CI: `verify-generated-types-slm`).
- `src/*.ts`: the hand-written SLM types (nodes, services, blue-green, NPU, agents/security) built on it.
- `index.ts`: the public surface, `export type *` only.

Types only, no runtime code and no dependencies, so there is no `package.json` link or lockfile
entry in the consuming apps: each app maps `@autobot/slm-contract` and
`@autobot/slm-contract/generated` through its tsconfig `paths`. A runtime import (a value, an
enum, or `export *` without `type`) would not resolve and must not be added here.
