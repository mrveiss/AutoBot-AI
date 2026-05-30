import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { AutobotWidget } from '../AutobotWidget'

// Register custom element once per test suite
if (!customElements.get('autobot-widget')) {
  customElements.define('autobot-widget', AutobotWidget)
}

function mount(attrs: Record<string, string> = {}): AutobotWidget {
  const el = document.createElement('autobot-widget') as AutobotWidget
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v)
  document.body.appendChild(el)
  return el
}

function unmount(el: HTMLElement) {
  document.body.removeChild(el)
}

describe('AutobotWidget', () => {
  let el: AutobotWidget

  afterEach(() => {
    if (el && el.parentNode) unmount(el)
  })

  it('registers as a custom element', () => {
    expect(customElements.get('autobot-widget')).toBe(AutobotWidget)
  })

  it('attaches a shadow root on connect', () => {
    el = mount({ 'data-api-url': 'http://localhost:8001' })
    expect(el.shadowRoot).not.toBeNull()
  })

  it('renders the FAB button inside the shadow root', () => {
    el = mount({ 'data-api-url': 'http://localhost:8001', 'data-button-label': 'Open chat' })
    const fab = el.shadowRoot!.querySelector('.ab-fab')
    expect(fab).not.toBeNull()
    expect((fab as HTMLButtonElement).getAttribute('aria-label')).toBe('Open chat')
  })

  it('does not render the panel by default (closed state)', () => {
    el = mount({ 'data-api-url': 'http://localhost:8001' })
    const panel = el.shadowRoot!.querySelector('.ab-panel')
    expect(panel).toBeNull()
  })

  it('applies bottom-left position class when data-position=bottom-left', () => {
    el = mount({ 'data-api-url': 'http://localhost:8001', 'data-position': 'bottom-left' })
    const root = el.shadowRoot!.querySelector('.ab-widget')
    expect(root?.classList.contains('ab-pos-left')).toBe(true)
  })

  it('applies bottom-right position class by default', () => {
    el = mount({ 'data-api-url': 'http://localhost:8001' })
    const root = el.shadowRoot!.querySelector('.ab-widget')
    expect(root?.classList.contains('ab-pos-right')).toBe(true)
  })

  it('re-mounts with updated config on attributeChangedCallback', () => {
    el = mount({ 'data-api-url': 'http://localhost:8001', 'data-title': 'Before' })
    el.setAttribute('data-title', 'After')
    // After attribute change the shadow DOM is replaced; we just verify no throw
    expect(el.shadowRoot).not.toBeNull()
  })

  it('injects widget styles into the shadow DOM', () => {
    el = mount({ 'data-api-url': 'http://localhost:8001' })
    const styleEl = el.shadowRoot!.querySelector('style')
    expect(styleEl).not.toBeNull()
    expect(styleEl!.textContent).toContain('ab-widget')
  })

  it('disconnects cleanly (no error on unmount)', () => {
    el = mount({ 'data-api-url': 'http://localhost:8001' })
    expect(() => unmount(el)).not.toThrow()
  })

  it('injects dark theme CSS when data-theme=dark (GH#9100)', () => {
    el = mount({ 'data-api-url': 'http://localhost:8001', 'data-theme': 'dark' })
    const styleEl = el.shadowRoot!.querySelector('style')
    expect(styleEl!.textContent).toContain(':host([data-theme="dark"])')
    expect(styleEl!.textContent).toContain('--ab-bg')
  })

  it('unmounts without throw when AbortController is present (GH#9101)', () => {
    vi.stubGlobal('AbortController', vi.fn(() => ({ abort: vi.fn(), signal: {} as AbortSignal })))
    el = mount({ 'data-api-url': 'http://localhost:8001' })
    expect(() => unmount(el)).not.toThrow()
    vi.unstubAllGlobals()
  })
})

describe('embed-entry auto-inject', () => {
  it('does not double-register the custom element', async () => {
    // Second import of embed-entry must not throw due to double defineCustomElements
    const before = customElements.get('autobot-widget')
    await import('../embed-entry')
    expect(customElements.get('autobot-widget')).toBe(before)
  })
})
