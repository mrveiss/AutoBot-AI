import '@testing-library/jest-dom'
import { vi } from 'vitest'

// Global test setup
beforeEach(() => {
  // Clear all mocks before each test
  vi.clearAllMocks()

  // Reset DOM
  document.body.innerHTML = ''

  // Reset location
  Object.defineProperty(window, 'location', {
    value: {
      href: 'http://localhost:3000',
      origin: 'http://localhost:3000',
      protocol: 'http:',
      hostname: 'localhost',
      port: '3000',
      pathname: '/',
      search: '',
      hash: '',
      reload: vi.fn(),
      assign: vi.fn(),
      replace: vi.fn()
    },
    writable: true
  })
})
