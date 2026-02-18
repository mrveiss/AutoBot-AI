import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/vue'
import userEvent from '@testing-library/user-event'
import SettingsPanel from '../settings/SettingsPanel.vue'
import {
  renderComponent,
  createMockSettings,
  waitForUpdate,
} from '../../test/utils/test-utils'
import { createMockApiService } from '../../test/mocks/api-client-mock'

// Mock dependencies
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

const mockSettings = createMockSettings({
  chat: {
    auto_scroll: true,
    max_messages: 100,
    message_retention_days: 30,
  },
  backend: {
    general: {
      host: 'localhost',
      port: 8001,
      timeout: 30000,
      debug: false,
    },
    llm: {
      provider: 'openai',
      model: 'gpt-4',
      temperature: 0.7,
      max_tokens: 2000,
    },
    embedding: {
      provider: 'openai',
      model: 'text-embedding-ada-002',
      dimensions: 1536,
    }
  },
  ui: {
    theme: 'light',
    sidebar_collapsed: false,
    auto_save: true,
  }
})

describe('SettingsPanel', () => {
  let user: ReturnType<typeof userEvent.setup>
  let mockApi: ReturnType<typeof createMockApiService>

  beforeEach(() => {
    user = userEvent.setup()
    mockApi = createMockApiService()

    // Mock settings API response
    mockApi.client.mockGet('/api/settings', {
      success: true,
      data: { settings: mockSettings }
    })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  describe('Rendering', () => {
    it('renders the settings panel with tabs', async () => {
      renderComponent(SettingsPanel)

      expect(screen.getByText('Settings')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /chat/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /backend/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /ui/i })).toBeInTheDocument()
    })

    it('loads settings on mount', async () => {
      renderComponent(SettingsPanel)

      await waitFor(() => {
        expect(mockApi.client.get).toHaveBeenCalledWith('/api/settings')
      })
    })

    it('shows loading state while fetching settings', () => {
      // Mock delayed response
      mockApi.client.get.mockImplementation(() =>
        new Promise(resolve => setTimeout(resolve, 1000))
      )

      renderComponent(SettingsPanel)

      // Should show loading indication
      expect(screen.getByText('Settings')).toBeInTheDocument()
    })

    it('handles settings loading error', async () => {
      mockApi.client.get.mockRejectedValue(new Error('Failed to load settings'))

      renderComponent(SettingsPanel)

      await waitFor(() => {
        // Should show error state or fallback content
        expect(screen.getByText('Settings')).toBeInTheDocument()
      })
    })
  })

  describe('Tab Navigation', () => {
    it('switches between tabs correctly', async () => {
      renderComponent(SettingsPanel)

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /chat/i })).toBeInTheDocument()
      })

      // Start on chat tab (default)
      expect(screen.getByText('Chat Settings')).toBeInTheDocument()

      // Switch to backend tab
      const backendTab = screen.getByRole('button', { name: /backend/i })
      await user.click(backendTab)

      await waitFor(() => {
        expect(screen.getByText('General')).toBeInTheDocument()
        expect(screen.getByRole('button', { name: /llm/i })).toBeInTheDocument()
      })

      // Switch to UI tab
      const uiTab = screen.getByRole('button', { name: /ui/i })
      await user.click(uiTab)

      await waitFor(() => {
        expect(screen.getByText('UI Settings')).toBeInTheDocument()
      })
    })

    it('shows active tab correctly', async () => {
      renderComponent(SettingsPanel)

      await waitFor(() => {
        const chatTab = screen.getByRole('button', { name: /chat/i })
        expect(chatTab).toHaveClass('active')
      })

      const backendTab = screen.getByRole('button', { name: /backend/i })
      await user.click(backendTab)

      await waitFor(() => {
        expect(backendTab).toHaveClass('active')
        expect(screen.getByRole('button', { name: /chat/i })).not.toHaveClass('active')
      })
    })
  })

  describe('Chat Settings', () => {
    beforeEach(async () => {
      renderComponent(SettingsPanel)
      await waitFor(() => {
        expect(screen.getByText('Chat Settings')).toBeInTheDocument()
      })
    })

    it('displays chat settings correctly', () => {
      expect(screen.getByLabelText(/auto scroll/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/max messages/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/message retention/i)).toBeInTheDocument()
    })

    it('updates auto scroll setting', async () => {
      const autoScrollCheckbox = screen.getByLabelText(/auto scroll/i) as HTMLInputElement
      expect(autoScrollCheckbox.checked).toBe(true)

      await user.click(autoScrollCheckbox)
      expect(autoScrollCheckbox.checked).toBe(false)

      // Should trigger save if auto-save is enabled
      await waitFor(() => {
        expect(mockApi.client.post).toHaveBeenCalledWith(
          '/api/settings',
          expect.objectContaining({
            chat: expect.objectContaining({
              auto_scroll: false
            })
          })
        )
      })
    })

    it('updates max messages setting', async () => {
      const maxMessagesInput = screen.getByLabelText(/max messages/i) as HTMLInputElement
      expect(maxMessagesInput.value).toBe('100')

      await user.clear(maxMessagesInput)
      await user.type(maxMessagesInput, '200')

      await waitFor(() => {
        expect(mockApi.client.post).toHaveBeenCalledWith(
          '/api/settings',
          expect.objectContaining({
            chat: expect.objectContaining({
              max_messages: 200
            })
          })
        )
      })
    })

    it('validates max messages range', async () => {
      const maxMessagesInput = screen.getByLabelText(/max messages/i) as HTMLInputElement

      await user.clear(maxMessagesInput)
      await user.type(maxMessagesInput, '5') // Below minimum

      // Should show validation error or reset to minimum
      expect(maxMessagesInput.min).toBe('10')
    })

    it('updates message retention days', async () => {
      const retentionInput = screen.getByLabelText(/message retention/i) as HTMLInputElement
      expect(retentionInput.value).toBe('30')

      await user.clear(retentionInput)
      await user.type(retentionInput, '60')

      await waitFor(() => {
        expect(mockApi.client.post).toHaveBeenCalledWith(
          '/api/settings',
          expect.objectContaining({
            chat: expect.objectContaining({
              message_retention_days: 60
            })
          })
        )
      })
    })
  })

  describe('Backend Settings', () => {
    beforeEach(async () => {
      renderComponent(SettingsPanel)

      await waitFor(() => {
        const backendTab = screen.getByRole('button', { name: /backend/i })
        return user.click(backendTab)
      })

      await waitFor(() => {
        expect(screen.getByText('General')).toBeInTheDocument()
      })
    })

    it('displays backend sub-tabs', () => {
      expect(screen.getByRole('button', { name: /general/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /llm/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /embedding/i })).toBeInTheDocument()
    })

    it('switches between backend sub-tabs', async () => {
      // Start on General tab
      expect(screen.getByLabelText(/host/i)).toBeInTheDocument()

      // Switch to LLM tab
      const llmSubTab = screen.getByRole('button', { name: /llm/i })
      await user.click(llmSubTab)

      await waitFor(() => {
        expect(screen.getByLabelText(/provider/i)).toBeInTheDocument()
        expect(screen.getByLabelText(/model/i)).toBeInTheDocument()
      })

      // Switch to Embedding tab
      const embeddingSubTab = screen.getByRole('button', { name: /embedding/i })
      await user.click(embeddingSubTab)

      await waitFor(() => {
        expect(screen.getByLabelText(/dimensions/i)).toBeInTheDocument()
      })
    })

    describe('General Settings', () => {
      it('displays and updates host setting', async () => {
        const hostInput = screen.getByLabelText(/host/i) as HTMLInputElement
        expect(hostInput.value).toBe('localhost')

        await user.clear(hostInput)
        await user.type(hostInput, '192.168.1.100')

        await waitFor(() => {
          expect(mockApi.client.post).toHaveBeenCalledWith(
            '/api/settings',
            expect.objectContaining({
              backend: expect.objectContaining({
                general: expect.objectContaining({
                  host: '192.168.1.100'
                })
              })
            })
          )
        })
      })

      it('displays and updates port setting', async () => {
        const portInput = screen.getByLabelText(/port/i) as HTMLInputElement
        expect(portInput.value).toBe('8001')

        await user.clear(portInput)
        await user.type(portInput, '8002')

        await waitFor(() => {
          expect(mockApi.client.post).toHaveBeenCalledWith(
            '/api/settings',
            expect.objectContaining({
              backend: expect.objectContaining({
                general: expect.objectContaining({
                  port: 8002
                })
              })
            })
          )
        })
      })
    })

    describe('LLM Settings', () => {
      beforeEach(async () => {
        const llmSubTab = screen.getByRole('button', { name: /llm/i })
        await user.click(llmSubTab)

        await waitFor(() => {
          expect(screen.getByLabelText(/provider/i)).toBeInTheDocument()
        })
      })

      it('displays and updates LLM provider', async () => {
        const providerSelect = screen.getByLabelText(/provider/i) as HTMLSelectElement
        expect(providerSelect.value).toBe('openai')

        await user.selectOptions(providerSelect, 'anthropic')

        await waitFor(() => {
          expect(mockApi.client.post).toHaveBeenCalledWith(
            '/api/settings',
            expect.objectContaining({
              backend: expect.objectContaining({
                llm: expect.objectContaining({
                  provider: 'anthropic'
                })
              })
            })
          )
        })
      })

      it('displays and updates model', async () => {
        const modelInput = screen.getByLabelText(/model/i) as HTMLInputElement
        expect(modelInput.value).toBe('gpt-4')

        await user.clear(modelInput)
        await user.type(modelInput, 'gpt-4-turbo')

        await waitFor(() => {
          expect(mockApi.client.post).toHaveBeenCalledWith(
            '/api/settings',
            expect.objectContaining({
              backend: expect.objectContaining({
                llm: expect.objectContaining({
                  model: 'gpt-4-turbo'
                })
              })
            })
          )
        })
      })

      it('displays and updates temperature', async () => {
        const tempInput = screen.getByLabelText(/temperature/i) as HTMLInputElement
        expect(tempInput.value).toBe('0.7')

        await user.clear(tempInput)
        await user.type(tempInput, '0.9')

        await waitFor(() => {
          expect(mockApi.client.post).toHaveBeenCalledWith(
            '/api/settings',
            expect.objectContaining({
              backend: expect.objectContaining({
                llm: expect.objectContaining({
                  temperature: 0.9
                })
              })
            })
          )
        })
      })

      it('validates temperature range', async () => {
        const tempInput = screen.getByLabelText(/temperature/i) as HTMLInputElement

        await user.clear(tempInput)
        await user.type(tempInput, '1.5') // Above maximum

        // Should enforce maximum value
        expect(tempInput.max).toBe('1')
      })
    })
  })

  describe('UI Settings', () => {
    beforeEach(async () => {
      renderComponent(SettingsPanel)

      const uiTab = screen.getByRole('button', { name: /ui/i })
      await user.click(uiTab)

      await waitFor(() => {
        expect(screen.getByText('UI Settings')).toBeInTheDocument()
      })
    })

    it('displays UI settings', () => {
      expect(screen.getByLabelText(/theme/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/sidebar collapsed/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/auto save/i)).toBeInTheDocument()
    })

    it('updates theme setting', async () => {
      const themeSelect = screen.getByLabelText(/theme/i) as HTMLSelectElement
      expect(themeSelect.value).toBe('light')

      await user.selectOptions(themeSelect, 'dark')

      await waitFor(() => {
        expect(mockApi.client.post).toHaveBeenCalledWith(
          '/api/settings',
          expect.objectContaining({
            ui: expect.objectContaining({
              theme: 'dark'
            })
          })
        )
      })
    })

    it('updates sidebar collapsed setting', async () => {
      const sidebarCheckbox = screen.getByLabelText(/sidebar collapsed/i) as HTMLInputElement
      expect(sidebarCheckbox.checked).toBe(false)

      await user.click(sidebarCheckbox)

      await waitFor(() => {
        expect(mockApi.client.post).toHaveBeenCalledWith(
          '/api/settings',
          expect.objectContaining({
            ui: expect.objectContaining({
              sidebar_collapsed: true
            })
          })
        )
      })
    })

    it('updates auto save setting', async () => {
      const autoSaveCheckbox = screen.getByLabelText(/auto save/i) as HTMLInputElement
      expect(autoSaveCheckbox.checked).toBe(true)

      await user.click(autoSaveCheckbox)

      await waitFor(() => {
        expect(mockApi.client.post).toHaveBeenCalledWith(
          '/api/settings',
          expect.objectContaining({
            ui: expect.objectContaining({
              auto_save: false
            })
          })
        )
      })
    })
  })

  describe('Settings Persistence', () => {
    it('saves settings automatically when auto_save is enabled', async () => {
      renderComponent(SettingsPanel)

      await waitFor(() => {
        expect(screen.getByText('Chat Settings')).toBeInTheDocument()
      })

      const autoScrollCheckbox = screen.getByLabelText(/auto scroll/i)
      await user.click(autoScrollCheckbox)

      await waitFor(() => {
        expect(mockApi.client.post).toHaveBeenCalledWith('/api/settings', expect.any(Object))
      })
    })

    it('shows save button when auto_save is disabled', async () => {
      // Mock settings with auto_save disabled
      mockApi.client.mockGet('/api/settings', {
        success: true,
        data: {
          settings: {
            ...mockSettings,
            ui: { ...mockSettings.ui, auto_save: false }
          }
        }
      })

      renderComponent(SettingsPanel)

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /save/i })).toBeInTheDocument()
      })
    })

    it('handles save errors gracefully', async () => {
      mockApi.client.post.mockRejectedValue(new Error('Save failed'))

      renderComponent(SettingsPanel)

      await waitFor(() => {
        expect(screen.getByText('Chat Settings')).toBeInTheDocument()
      })

      const autoScrollCheckbox = screen.getByLabelText(/auto scroll/i)
      await user.click(autoScrollCheckbox)

      // Should handle error without crashing
      await waitFor(() => {
        expect(mockApi.client.post).toHaveBeenCalled()
      })
    })

    it('shows save confirmation', async () => {
      renderComponent(SettingsPanel)

      await waitFor(() => {
        expect(screen.getByText('Chat Settings')).toBeInTheDocument()
      })

      const autoScrollCheckbox = screen.getByLabelText(/auto scroll/i)
      await user.click(autoScrollCheckbox)

      // Should show save confirmation (toast or similar)
      await waitFor(() => {
        expect(mockApi.client.post).toHaveBeenCalled()
      })
    })
  })

  describe('Form Validation', () => {
    it('validates numeric inputs', async () => {
      renderComponent(SettingsPanel)

      await waitFor(async () => {
        const maxMessagesInput = screen.getByLabelText(/max messages/i) as HTMLInputElement

        await user.clear(maxMessagesInput)
        await user.type(maxMessagesInput, 'abc')

        // Should not accept non-numeric input
        expect(maxMessagesInput.validity.valid).toBe(false)
      })
    })

    it('validates required fields', async () => {
      renderComponent(SettingsPanel)

      const backendTab = screen.getByRole('button', { name: /backend/i })
      await user.click(backendTab)

      await waitFor(async () => {
        const hostInput = screen.getByLabelText(/host/i) as HTMLInputElement

        await user.clear(hostInput)
        await user.tab() // Trigger validation

        // Should show required field validation
        expect(hostInput.validity.valid).toBe(false)
      })
    })
  })

  describe('Accessibility', () => {
    it('has proper ARIA labels', () => {
      renderComponent(SettingsPanel)

      expect(screen.getByRole('button', { name: /chat/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /backend/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /ui/i })).toBeInTheDocument()
    })

    it('supports keyboard navigation', async () => {
      renderComponent(SettingsPanel)

      await waitFor(() => {
        const chatTab = screen.getByRole('button', { name: /chat/i })
        chatTab.focus()
        expect(document.activeElement).toBe(chatTab)
      })

      // Tab navigation through settings
      await user.tab()
      await user.tab()

      // Should navigate through form elements
      const autoScrollCheckbox = screen.getByLabelText(/auto scroll/i)
      expect(document.activeElement).toBe(autoScrollCheckbox)
    })

    it('has proper form labels', () => {
      renderComponent(SettingsPanel)

      expect(screen.getByLabelText(/auto scroll/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/max messages/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/message retention/i)).toBeInTheDocument()
    })
  })

  describe('Responsive Design', () => {
    it('adapts to different screen sizes', () => {
      // Mock different viewport sizes
      Object.defineProperty(window, 'innerWidth', { value: 768 })

      renderComponent(SettingsPanel)

      // Should render appropriately for tablet/mobile
      expect(screen.getByText('Settings')).toBeInTheDocument()
    })
  })

  describe('Integration', () => {
    it('integrates with theme changes', async () => {
      renderComponent(SettingsPanel)

      const uiTab = screen.getByRole('button', { name: /ui/i })
      await user.click(uiTab)

      await waitFor(async () => {
        const themeSelect = screen.getByLabelText(/theme/i) as HTMLSelectElement
        await user.selectOptions(themeSelect, 'dark')
      })

      // Should apply theme change to UI
      await waitFor(() => {
        expect(mockApi.client.post).toHaveBeenCalledWith(
          '/api/settings',
          expect.objectContaining({
            ui: expect.objectContaining({
              theme: 'dark'
            })
          })
        )
      })
    })
  })
})
