import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import CodeCell from './CodeCell.vue'
import { createI18n } from 'vue-i18n'

// Mock highlight.js
vi.mock('highlight.js', () => ({
  default: {
    highlight: vi.fn((code: string) => ({ value: `<span class="hljs-string">${code}</span>` })),
    highlightAuto: vi.fn((code: string) => ({ value: `<span class="hljs">${code}</span>` }))
  }
}))

// Mock navigator.clipboard
const mockClipboard = {
  writeText: vi.fn(async () => {})
}
Object.assign(navigator, { clipboard: mockClipboard })

// Setup i18n
const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: {
    en: {
      code: {
        cellPlaceholder: 'Code',
        copy: 'Copy',
        copied: 'Copied!',
        copyCodeAriaLabel: 'Copy code to clipboard',
        copyFailed: 'Failed to copy'
      }
    }
  }
})

describe('CodeCell.vue', () => {
  const pythonCode = 'def hello():\n    print("world")'
  const codePayload = { code: pythonCode }

  beforeEach(() => {
    vi.clearAllMocks()
    mockClipboard.writeText.mockClear()
  })

  describe('rendering', () => {
    it('shows placeholder when richPayload is null', () => {
      const wrapper = mount(CodeCell, {
        props: { richPayload: null },
        global: {
          stubs: { i: true },
          plugins: [i18n]
        }
      })

      expect(wrapper.find('.code-placeholder').exists()).toBe(true)
      expect(wrapper.find('.code-wrapper').exists()).toBe(false)
    })

    it('renders code wrapper when richPayload is provided', async () => {
      const wrapper = mount(CodeCell, {
        props: { richPayload: codePayload },
        global: {
          stubs: { i: true },
          plugins: [i18n]
        }
      })

      await wrapper.vm.$nextTick()
      expect(wrapper.find('.code-wrapper').exists()).toBe(true)
    })

    it('generates unique cell ID', () => {
      const wrapper1 = mount(CodeCell, {
        props: { richPayload: null },
        global: {
          stubs: { i: true },
          plugins: [i18n]
        }
      })

      const wrapper2 = mount(CodeCell, {
        props: { richPayload: null },
        global: {
          stubs: { i: true },
          plugins: [i18n]
        }
      })

      const id1 = wrapper1.vm.cellId
      const id2 = wrapper2.vm.cellId

      expect(id1).not.toBe(id2)
      expect(id1).toMatch(/^code-/)
    })
  })

  describe('syntax highlighting', () => {
    it('applies language class when language is specified', async () => {
      const wrapper = mount(CodeCell, {
        props: { richPayload: codePayload, language: 'python' },
        global: {
          stubs: { i: true },
          plugins: [i18n]
        }
      })

      await wrapper.vm.$nextTick()
      expect(wrapper.vm.codeClasses).toContain('language-python')
    })

    it('extracts code from code field', () => {
      const wrapper = mount(CodeCell, {
        props: { richPayload: { code: pythonCode } },
        global: {
          stubs: { i: true },
          plugins: [i18n]
        }
      })

      expect(wrapper.vm.rawCode).toBe(pythonCode)
    })
  })

  describe('accessibility', () => {
    it('has aria-label on code region', async () => {
      const wrapper = mount(CodeCell, {
        props: { richPayload: codePayload },
        global: {
          stubs: { i: true },
          plugins: [i18n]
        }
      })

      await wrapper.vm.$nextTick()
      const codeRegion = wrapper.find('[role="region"]')
      expect(codeRegion.exists()).toBe(true)
      expect(codeRegion.attributes('aria-label')).toBe('Highlighted code')
    })

    it('has aria-live region for copy feedback', async () => {
      const wrapper = mount(CodeCell, {
        props: { richPayload: codePayload },
        global: {
          stubs: { i: true },
          plugins: [i18n]
        }
      })

      await wrapper.vm.$nextTick()
      const liveRegion = wrapper.find('[role="status"]')
      expect(liveRegion.exists()).toBe(true)
      expect(liveRegion.attributes('aria-live')).toBe('polite')
      expect(liveRegion.attributes('aria-atomic')).toBe('true')
    })
  })

  describe('language display', () => {
    it('shows language badge when language is provided', async () => {
      const wrapper = mount(CodeCell, {
        props: { richPayload: codePayload, language: 'python' },
        global: {
          stubs: { i: true },
          plugins: [i18n]
        }
      })

      await wrapper.vm.$nextTick()
      const languageBadge = wrapper.find('.code-language')
      expect(languageBadge.exists()).toBe(true)
    })
  })

  describe('edge cases', () => {
    it('handles empty code gracefully', () => {
      const wrapper = mount(CodeCell, {
        props: { richPayload: { code: '' } },
        global: {
          stubs: { i: true },
          plugins: [i18n]
        }
      })

      expect(wrapper.vm.rawCode).toBe('')
    })
  })
})
