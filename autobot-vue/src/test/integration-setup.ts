import { beforeAll, afterAll } from 'vitest'
import { setupServer } from 'msw/node'
import { handlers } from './mocks/api-handlers'

// Setup MSW server for integration tests
const server = setupServer(...handlers)

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