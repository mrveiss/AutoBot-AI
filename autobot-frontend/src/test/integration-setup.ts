// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { beforeAll, afterAll } from 'vitest'
import { setupServer } from 'msw/node'
import { handlers } from './mocks/api-handlers'

// Setup MSW server for integration tests.
// #9693: exported so test files can register per-test handlers via
// server.use(). Creating a SECOND setupServer() in a test file stacks two
// fetch interceptors, so every request hits matching handlers twice —
// which silently doubles stateful handler counters.
export const server = setupServer(...handlers)

beforeAll(() => {
  // Start the server before running integration tests
  server.listen({ onUnhandledRequest: 'warn' })
})

afterAll(() => {
  // Clean up after all tests are done
  server.close()
})

beforeEach(() => {
  // Reset handlers for each test
  server.resetHandlers()
})
