import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/vue'
import userEvent from '@testing-library/user-event'
import SettingsPanel from '../settings/SettingsPanel.vue'
import { renderComponent } from '../../test/utils/test-utils'
import axios from 'axios'

// ── Mock dependencies ──────────────────────────────────────────────────
// SettingsPanel imports axios directly for all API calls.
// The global vitest-setup.ts runs vi.clearAllMocks() in beforeEach,
// which wipes mockResolvedValue set in vi.mock factories.
// We must re-configure return values in our own beforeEach using
// the imported (mocked) axios instance.

vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    create: vi.fn().mockReturnThis(),
    interceptors: {
      request: { use: vi.fn(), eject: vi.fn() },
      response: { use: vi.fn(), eject: vi.fn() },
    },
  },
}))

vi.mock('@/utils/ApiClient', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

vi.mock('@/services/api', () => ({
  default: {
    getSettings: vi.fn(),
    saveSettings: vi.fn(),
  },
  apiService: {
    getSettings: vi.fn(),
    saveSettings: vi.fn(),
  },
}))

// Mock CacheService used by the component for cached settings fallback
vi.mock('@/services/CacheService', () => ({
  default: {
    get: vi.fn().mockReturnValue(null),
    set: vi.fn(),
    clear: vi.fn(),
  },
}))

// ── Mock settings response matching backend shape ──────────────────────
const mockSettingsResponse = {
  chat: {
    auto_scroll: true,
    max_messages: 100,
    message_retention_days: 30,
  },
  backend: {
    llm: {
      provider_type: 'local',
      local: { provider: 'ollama' },
    },
  },
  ui: {
    theme: 'light',
    language: 'en',
    show_timestamps: true,
    show_status_bar: true,
    auto_refresh_interval: 30,
  },
}

const mockHealthResponse = {
  status: 'healthy',
  services: {},
}

/**
 * Configure axios mock return values for all endpoints SettingsPanel
 * calls on mount:
 *   GET /api/settings/           -> loadSettings
 *   GET /api/cache/stats         -> checkCacheApiAvailability + refreshCacheStats
 *   GET /api/system/health/detailed -> loadHealthStatus
 *   GET /api/system/health       -> loadHealthStatus fallback
 */
function setupAxiosMocks() {
  vi.mocked(axios.get).mockImplementation((url: string, ..._args: any[]) => {
    if (url === '/api/settings/') {
      return Promise.resolve({ data: mockSettingsResponse })
    }
    if (url === '/api/cache/stats') {
      return Promise.resolve({ data: { hits: 0, misses: 0 } })
    }
    if (url === '/api/system/health/detailed') {
      return Promise.resolve({ data: mockHealthResponse })
    }
    if (url === '/api/system/health') {
      return Promise.resolve({ data: { status: 'healthy' } })
    }
    if (url === '/api/prompts') {
      return Promise.resolve({ data: [] })
    }
    // Default: resolve with empty data to prevent undefined crashes
    return Promise.resolve({ data: {} })
  })

  vi.mocked(axios.post).mockResolvedValue({ data: { success: true } })
  vi.mocked(axios.put).mockResolvedValue({ data: { success: true } })
  vi.mocked(axios.delete).mockResolvedValue({ data: { success: true } })
}

describe('SettingsPanel', () => {
  let _user: ReturnType<typeof userEvent.setup>

  beforeEach(() => {
    user = userEvent.setup()
    // Re-configure axios mocks after global vi.clearAllMocks() wipes them
    setupAxiosMocks()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  // Helper to render SettingsPanel with all required plugins
  function renderSettings() {
    return renderComponent(SettingsPanel, {
      router: true,
    })
  }

  describe('Rendering', () => {
    it('renders the settings panel layout', async () => {
      renderSettings()

      // Component always renders the layout container
      const layout = document.querySelector('.settings-panel-layout')
      expect(layout).not.toBeNull()
    })

    it('shows loading state initially', () => {
      renderSettings()

      // While settings are being fetched, loading indicator is shown
      // i18n returns the key path when no messages are provided in test i18n
      expect(screen.getByText('settings.loadingSettings')).toBeInTheDocument()
    })

    it('calls settings API on mount', async () => {
      renderSettings()

      await waitFor(() => {
        expect(axios.get).toHaveBeenCalledWith('/api/settings/')
      })
    })

    it('calls health API on mount', async () => {
      renderSettings()

      await waitFor(() => {
        expect(axios.get).toHaveBeenCalledWith('/api/system/health/detailed')
      })
    })

    it('calls cache availability check on mount', async () => {
      renderSettings()

      await waitFor(() => {
        expect(axios.get).toHaveBeenCalledWith(
          '/api/cache/stats',
          expect.objectContaining({ timeout: 3000 })
        )
      })
    })

    it('transitions from loading to loaded after successful fetch', async () => {
      renderSettings()

      await waitFor(() => {
        // Loading indicator should be gone
        const loadingEl = document.querySelector('.settings-loading')
        expect(loadingEl).toBeNull()
      })

      // router-view container should exist (content-inner always renders)
      const contentInner = document.querySelector('.settings-content-inner')
      expect(contentInner).not.toBeNull()
    })

    it('shows offline status when settings API fails', async () => {
      vi.mocked(axios.get).mockImplementation((url: string) => {
        if (url === '/api/settings/') {
          return Promise.reject(new Error('Network error'))
        }
        // Other endpoints still resolve to prevent cascading errors
        return Promise.resolve({ data: {} })
      })

      renderSettings()

      await waitFor(() => {
        const offlineEl = document.querySelector('.settings-status.offline')
        expect(offlineEl).not.toBeNull()
      })
    })
  })

  describe('Settings Loading', () => {
    it('loads settings data from API response', async () => {
      renderSettings()

      await waitFor(() => {
        expect(axios.get).toHaveBeenCalledWith('/api/settings/')
      })

      // After loading, the component should no longer show loading state
      await waitFor(() => {
        const loadingEl = document.querySelector('.settings-loading')
        expect(loadingEl).toBeNull()
      })
    })

    it('handles concurrent load prevention', async () => {
      renderSettings()

      // First call should go through
      await waitFor(() => {
        const settingsCalls = vi.mocked(axios.get).mock.calls.filter(
          (call) => call[0] === '/api/settings/'
        )
        // Should only call settings endpoint once (guard prevents concurrent)
        expect(settingsCalls.length).toBe(1)
      })
    })

    it('falls back to cache when API fails', async () => {
      const CacheService = await import('@/services/CacheService')
      const mockCacheGet = vi.mocked(CacheService.default.get)
      mockCacheGet.mockReturnValue({
        chat: { auto_scroll: false, max_messages: 50, message_retention_days: 7 },
      })

      vi.mocked(axios.get).mockImplementation((url: string) => {
        if (url === '/api/settings/') {
          return Promise.reject(new Error('Network error'))
        }
        return Promise.resolve({ data: {} })
      })

      renderSettings()

      await waitFor(() => {
        expect(mockCacheGet).toHaveBeenCalledWith('settings')
      })
    })
  })

  describe('Save and Discard', () => {
    it('does not show save button when there are no unsaved changes', async () => {
      renderSettings()

      await waitFor(() => {
        const loadingEl = document.querySelector('.settings-loading')
        expect(loadingEl).toBeNull()
      })

      // Save button should not be visible when no changes made
      const saveBtn = document.querySelector('.save-settings-btn')
      expect(saveBtn).toBeNull()
    })

    it('does not show actions section when no changes are pending', async () => {
      renderSettings()

      await waitFor(() => {
        const loadingEl = document.querySelector('.settings-loading')
        expect(loadingEl).toBeNull()
      })

      // Without changes, no actions section
      const actionsEl = document.querySelector('.settings-actions')
      expect(actionsEl).toBeNull()
    })
  })

  describe('Health Status', () => {
    it('loads detailed health status on mount', async () => {
      renderSettings()

      await waitFor(() => {
        expect(axios.get).toHaveBeenCalledWith('/api/system/health/detailed')
      })
    })

    it('falls back to basic health when detailed fails', async () => {
      vi.mocked(axios.get).mockImplementation((url: string) => {
        if (url === '/api/settings/') {
          return Promise.resolve({ data: mockSettingsResponse })
        }
        if (url === '/api/system/health/detailed') {
          return Promise.reject(new Error('Not found'))
        }
        if (url === '/api/system/health') {
          return Promise.resolve({ data: { status: 'healthy' } })
        }
        return Promise.resolve({ data: {} })
      })

      renderSettings()

      await waitFor(() => {
        expect(axios.get).toHaveBeenCalledWith('/api/system/health')
      })
    })
  })

  describe('Cache API', () => {
    it('checks cache API availability on mount', async () => {
      renderSettings()

      await waitFor(() => {
        expect(axios.get).toHaveBeenCalledWith(
          '/api/cache/stats',
          expect.objectContaining({ timeout: 3000 })
        )
      })
    })

    it('loads cache stats when cache API is available', async () => {
      renderSettings()

      await waitFor(() => {
        // Should have at least the availability check call
        const cacheCalls = vi.mocked(axios.get).mock.calls.filter(
          (call) => call[0] === '/api/cache/stats'
        )
        expect(cacheCalls.length).toBeGreaterThanOrEqual(1)
      })
    })

    it('handles cache API unavailability gracefully', async () => {
      vi.mocked(axios.get).mockImplementation((url: string) => {
        if (url === '/api/settings/') {
          return Promise.resolve({ data: mockSettingsResponse })
        }
        if (url === '/api/cache/stats') {
          return Promise.reject(new Error('Cache unavailable'))
        }
        if (url === '/api/system/health/detailed') {
          return Promise.resolve({ data: mockHealthResponse })
        }
        return Promise.resolve({ data: {} })
      })

      renderSettings()

      // Should not crash; component handles error gracefully
      await waitFor(() => {
        const layout = document.querySelector('.settings-panel-layout')
        expect(layout).not.toBeNull()
      })
    })
  })

  describe('Error Handling', () => {
    it('handles all API failures without crashing', async () => {
      vi.mocked(axios.get).mockRejectedValue(new Error('All APIs down'))

      renderSettings()

      // Component should still render (error boundary catches)
      await waitFor(() => {
        const layout = document.querySelector('.settings-panel-layout')
        expect(layout).not.toBeNull()
      })
    })

    it('shows offline state when settings fail to load', async () => {
      vi.mocked(axios.get).mockImplementation((url: string) => {
        if (url === '/api/settings/') {
          return Promise.reject(new Error('Offline'))
        }
        return Promise.resolve({ data: {} })
      })

      renderSettings()

      await waitFor(() => {
        const offlineEl = document.querySelector('.settings-status.offline')
        expect(offlineEl).not.toBeNull()
      })
    })
  })

  describe('Multiple API Calls on Mount', () => {
    it('makes all expected API calls on mount', async () => {
      renderSettings()

      await waitFor(() => {
        const calledUrls = vi.mocked(axios.get).mock.calls.map((call) => call[0])
        expect(calledUrls).toContain('/api/settings/')
        expect(calledUrls).toContain('/api/system/health/detailed')
        // Cache stats called with timeout option for availability check
        const cacheCall = vi.mocked(axios.get).mock.calls.find(
          (call) => call[0] === '/api/cache/stats'
        )
        expect(cacheCall).toBeDefined()
      })
    })
  })

  describe('Accessibility', () => {
    it('renders main landmark element', async () => {
      renderSettings()

      const main = document.querySelector('main.settings-content')
      expect(main).not.toBeNull()
    })

    it('renders loading spinner with descriptive text', () => {
      renderSettings()

      const spinner = document.querySelector('.loading-spinner')
      expect(spinner).not.toBeNull()

      // Loading text is present (i18n key in test environment)
      expect(screen.getByText('settings.loadingSettings')).toBeInTheDocument()
    })
  })
})
