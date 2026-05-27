import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import BaseXTerminal from '../BaseXTerminal.vue'

// Track the most recently created Terminal mock instance so tests can inspect it
let lastTerminalInstance: Record<string, any> | null = null

// Factory that creates a fresh Terminal mock instance.
// Must be a regular function (not arrow) so it can be used as a constructor with `new`.
function createTerminalMock(this: Record<string, any>) {
  this.loadAddon = vi.fn()
  this.open = vi.fn()
  this.onData = vi.fn()
  this.onResize = vi.fn()
  this.dispose = vi.fn()
  this.write = vi.fn()
  this.writeln = vi.fn()
  this.clear = vi.fn()
  this.reset = vi.fn()
  this.focus = vi.fn()
  this.blur = vi.fn()
  this.cols = 80
  this.rows = 24
  this.options = {}
  // eslint-disable-next-line @typescript-eslint/no-this-alias
  lastTerminalInstance = this
}

// Import the mocked Terminal constructor so we can re-apply the implementation
// after vitest's mockReset clears it between tests.
import { Terminal } from '@xterm/xterm'

// Mock xterm.js — the factory returns a constructor that captures each instance.
// Must use regular function for `new` compatibility.
vi.mock('@xterm/xterm', () => ({
  Terminal: vi.fn().mockImplementation(createTerminalMock)
}))

vi.mock('@xterm/addon-fit', () => ({
  FitAddon: vi.fn(function (this: Record<string, any>) {
    this.fit = vi.fn()
  })
}))

vi.mock('@xterm/addon-web-links', () => ({
  WebLinksAddon: vi.fn()
}))

describe('BaseXTerminal', () => {
  let wrapper: any

  beforeEach(() => {
    wrapper = null
    lastTerminalInstance = null
    // vitest.config has mockReset: true which clears mockImplementation between
    // tests. Re-apply the Terminal constructor implementation so every test gets
    // a proper mock instance when the component calls `new Terminal(...)`.
    vi.mocked(Terminal).mockImplementation(createTerminalMock as any)
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

    // onMounted calls initTerminal() which is async — it awaits nextTick
    // internally, so we need to flush both the microtask queue and the
    // macrotask queue (setTimeout used in onMounted for initial fit).
    await nextTick()
    await nextTick()
    // Allow the setTimeout(100) in onMounted to fire
    await new Promise(resolve => setTimeout(resolve, 200))

    expect(wrapper.emitted('ready')).toBeTruthy()
    expect(wrapper.emitted('ready')![0]).toBeDefined()
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

    // Wait for initTerminal to complete so terminal.value is set
    await nextTick()
    await nextTick()

    await wrapper.setProps({ theme: 'light' })
    await nextTick()

    // Theme should be updated (verified through Terminal mock)
    expect(wrapper.props('theme')).toBe('light')
    // The component's watcher sets terminal.options.theme
    expect(lastTerminalInstance).not.toBeNull()
    expect(lastTerminalInstance!.options.theme).toBeDefined()
  })

  it('handles readOnly prop changes', async () => {
    wrapper = mount(BaseXTerminal, {
      props: {
        sessionId: 'test-session',
        readOnly: false
      }
    })

    // Wait for initTerminal to complete so terminal.value is set
    await nextTick()
    await nextTick()

    await wrapper.setProps({ readOnly: true })
    await nextTick()

    expect(wrapper.props('readOnly')).toBe(true)
    // The component's watcher sets terminal.options.disableStdin
    expect(lastTerminalInstance).not.toBeNull()
    expect(lastTerminalInstance!.options.disableStdin).toBe(true)
  })

  it('cleans up terminal on unmount', async () => {
    wrapper = mount(BaseXTerminal, {
      props: {
        sessionId: 'test-session'
      }
    })

    // Wait for initTerminal to complete so the terminal instance is created
    await nextTick()
    await nextTick()

    // Capture the mock terminal instance that was created during mount.
    // We must grab the reference BEFORE unmount because the component
    // sets terminal.value = undefined during disposal.
    const terminalMock = lastTerminalInstance
    expect(terminalMock).not.toBeNull()

    wrapper.unmount()
    // Prevent afterEach from calling unmount again on an already-unmounted wrapper
    wrapper = null

    // Verify dispose was called on the terminal mock
    expect(terminalMock!.dispose).toHaveBeenCalled()
  })
})
