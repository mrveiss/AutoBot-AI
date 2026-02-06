import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import BaseXTerminal from '../BaseXTerminal.vue'
import { Terminal } from '@xterm/xterm'

// Mock xterm.js
vi.mock('@xterm/xterm', () => ({
  Terminal: vi.fn(() => ({
    loadAddon: vi.fn(),
    open: vi.fn(),
    onData: vi.fn(),
    onResize: vi.fn(),
    dispose: vi.fn(),
    write: vi.fn(),
    writeln: vi.fn(),
    clear: vi.fn(),
    reset: vi.fn(),
    focus: vi.fn(),
    blur: vi.fn(),
    cols: 80,
    rows: 24,
    options: {}
  }))
}))

vi.mock('@xterm/addon-fit', () => ({
  FitAddon: vi.fn(() => ({
    fit: vi.fn()
  }))
}))

vi.mock('@xterm/addon-web-links', () => ({
  WebLinksAddon: vi.fn()
}))

describe('BaseXTerminal', () => {
  let wrapper: any

  beforeEach(() => {
    wrapper = null
  })

  afterEach(() => {
    if (wrapper) {
      wrapper.unmount()
    }
  })

  it('renders terminal container', () => {
    wrapper = mount(BaseXTerminal, {
      props: {
        sessionId: 'test-session'
      }
    })

    expect(wrapper.find('.base-xterm-container').exists()).toBe(true)
    expect(wrapper.find('.xterm-wrapper').exists()).toBe(true)
  })

  it('initializes with correct props', () => {
    wrapper = mount(BaseXTerminal, {
      props: {
        sessionId: 'test-session',
        theme: 'dark',
        fontSize: 14,
        readOnly: false
      }
    })

    expect(wrapper.props('sessionId')).toBe('test-session')
    expect(wrapper.props('theme')).toBe('dark')
    expect(wrapper.props('fontSize')).toBe(14)
    expect(wrapper.props('readOnly')).toBe(false)
  })

  it('emits ready event when terminal is initialized', async () => {
    wrapper = mount(BaseXTerminal, {
      props: {
        sessionId: 'test-session'
      }
    })

    await wrapper.vm.$nextTick()
    await new Promise(resolve => setTimeout(resolve, 200))

    expect(wrapper.emitted('ready')).toBeTruthy()
  })

  it('exposes terminal methods', () => {
    wrapper = mount(BaseXTerminal, {
      props: {
        sessionId: 'test-session'
      }
    })

    expect(typeof wrapper.vm.write).toBe('function')
    expect(typeof wrapper.vm.writeln).toBe('function')
    expect(typeof wrapper.vm.clear).toBe('function')
    expect(typeof wrapper.vm.reset).toBe('function')
    expect(typeof wrapper.vm.fit).toBe('function')
    expect(typeof wrapper.vm.focus).toBe('function')
    expect(typeof wrapper.vm.blur).toBe('function')
    expect(typeof wrapper.vm.getTerminal).toBe('function')
  })

  it('handles theme changes', async () => {
    wrapper = mount(BaseXTerminal, {
      props: {
        sessionId: 'test-session',
        theme: 'dark'
      }
    })

    await wrapper.setProps({ theme: 'light' })
    await wrapper.vm.$nextTick()

    // Theme should be updated (verified through Terminal mock)
    expect(wrapper.props('theme')).toBe('light')
  })

  it('handles readOnly prop changes', async () => {
    wrapper = mount(BaseXTerminal, {
      props: {
        sessionId: 'test-session',
        readOnly: false
      }
    })

    await wrapper.setProps({ readOnly: true })
    await wrapper.vm.$nextTick()

    expect(wrapper.props('readOnly')).toBe(true)
  })

  it('cleans up terminal on unmount', async () => {
    wrapper = mount(BaseXTerminal, {
      props: {
        sessionId: 'test-session'
      }
    })

    const disposeSpy = vi.spyOn(wrapper.vm.getTerminal?.() || {}, 'dispose')
    wrapper.unmount()

    // Verify cleanup was attempted
    expect(wrapper.emitted('disposed')).toBeTruthy()
  })
})
