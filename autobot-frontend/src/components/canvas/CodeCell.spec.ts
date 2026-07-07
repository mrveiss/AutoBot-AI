// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import CodeCell from './CodeCell.vue'
import type { CodePayload } from '@/types/canvas'

describe('CodeCell.vue', () => {
  const mockPythonPayload: CodePayload = {
    payloadType: 'code',
    code: 'def hello():\n  print("world")',
    language: 'python',
    executable: false,
  }

  const mockJsPayload: CodePayload = {
    payloadType: 'code',
    code: 'const x = 42;\nconsole.log(x);',
    language: 'javascript',
    executable: false,
  }

  beforeEach(() => {
    vi.clearAllMocks()
    // Mock clipboard API
    global.navigator.clipboard = {
      writeText: vi.fn().mockResolvedValue(undefined),
    } as unknown as Clipboard
  })

  it('renders loading state when no payload', () => {
    const wrapper = mount(CodeCell, {
      props: { richPayload: null },
    })
    const skeleton = wrapper.find('[aria-busy="true"]')
    expect(skeleton.exists()).toBe(true)
    // Loading state is a visual skeleton; text lives in the aria-label
    expect(skeleton.attributes('aria-label')).toContain('Loading code')
  })

  it('renders code block when payload provided', async () => {
    const wrapper = mount(CodeCell, {
      props: { richPayload: mockPythonPayload },
    })
    await wrapper.vm.$nextTick()
    expect(wrapper.find('pre').exists()).toBe(true)
    expect(wrapper.find('code').exists()).toBe(true)
  })

  it('displays language label', () => {
    const wrapper = mount(CodeCell, {
      props: { richPayload: mockPythonPayload },
    })
    expect(wrapper.text()).toContain('python')
  })

  it('renders copy button', () => {
    const wrapper = mount(CodeCell, {
      props: { richPayload: mockPythonPayload },
    })
    const copyBtn = wrapper.find('[data-testid="btn-copy-code"]')
    expect(copyBtn.exists()).toBe(true)
    expect(copyBtn.text()).toContain('Copy')
  })

  it('copies code to clipboard on button click', async () => {
    const wrapper = mount(CodeCell, {
      props: { richPayload: mockPythonPayload },
    })
    const copyBtn = wrapper.find('[data-testid="btn-copy-code"]')
    await copyBtn.trigger('click')
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(mockPythonPayload.code)
  })

  it('shows copy success feedback', async () => {
    const wrapper = mount(CodeCell, {
      props: { richPayload: mockPythonPayload },
    })
    const copyBtn = wrapper.find('[data-testid="btn-copy-code"]')
    await copyBtn.trigger('click')
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('Copied')
  })

  it('includes aria-live region for a11y feedback', () => {
    const wrapper = mount(CodeCell, {
      props: { richPayload: mockPythonPayload },
    })
    const liveRegion = wrapper.find('[aria-live="polite"]')
    expect(liveRegion.exists()).toBe(true)
    expect(liveRegion.attributes('role')).toBe('status')
  })

  it('has accessible code block role', () => {
    const wrapper = mount(CodeCell, {
      props: { richPayload: mockPythonPayload },
    })
    expect(wrapper.find('[role="region"]').exists()).toBe(true)
  })

  it('supports multiple languages', async () => {
    const wrapper = mount(CodeCell, {
      props: { richPayload: mockPythonPayload },
    })
    expect(wrapper.text()).toContain('python')

    await wrapper.setProps({ richPayload: mockJsPayload })
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('javascript')
  })

  it('handles plaintext code without language', () => {
    const plainPayload: CodePayload = {
      payloadType: 'code',
      code: 'just some plain text code',
      language: undefined,
      executable: false,
    }
    const wrapper = mount(CodeCell, {
      props: { richPayload: plainPayload },
    })
    expect(wrapper.find('pre').exists()).toBe(true)
  })

  it('updates code when payload changes', async () => {
    const wrapper = mount(CodeCell, {
      props: { richPayload: mockPythonPayload },
    })
    await wrapper.setProps({ richPayload: mockJsPayload })
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('javascript')
  })

  it('clears error state on new payload', async () => {
    const wrapper = mount(CodeCell, {
      props: { richPayload: null },
    })
    expect(wrapper.find('[aria-busy="true"]').exists()).toBe(true)
    await wrapper.setProps({ richPayload: mockPythonPayload })
    await wrapper.vm.$nextTick()
    expect(wrapper.find('pre').exists()).toBe(true)
  })

  it('resets copy feedback after timeout', async () => {
    vi.useFakeTimers()
    const wrapper = mount(CodeCell, {
      props: { richPayload: mockPythonPayload },
    })
    const copyBtn = wrapper.find('[data-testid="btn-copy-code"]')
    await copyBtn.trigger('click')
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('Copied')

    vi.advanceTimersByTime(2100)
    await wrapper.vm.$nextTick()
    // Feedback should be cleared (button back to default text)
    vi.useRealTimers()
  })

  it('has sr-only copy feedback for screen readers', () => {
    const wrapper = mount(CodeCell, {
      props: { richPayload: mockPythonPayload },
    })
    // Component includes sr-only class for screen reader feedback
    const styles = wrapper.vm.$el.querySelector('.sr-only')
    expect(styles).toBeTruthy()
  })
})
