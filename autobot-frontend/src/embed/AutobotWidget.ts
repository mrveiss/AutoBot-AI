/**
 * AutobotWidget — Custom Element wrapping the chat app in a Shadow DOM.
 *
 * Observed attributes → props forwarded into the Vue app:
 *   data-api-url       Base URL of the AutoBot backend (required)
 *   data-org-id        Organisation / tenant ID
 *   data-theme         "light" (default) | "dark"
 *   data-position      "bottom-right" (default) | "bottom-left"
 *   data-title         Widget header title
 *   data-placeholder   Input placeholder text
 *   data-primary-color CSS colour for the accent / button
 *   data-button-label  Accessible label for the open/close toggle
 */

import { createApp, defineComponent, ref, computed, h, nextTick, getCurrentInstance, onUnmounted } from 'vue'
import type { App } from 'vue'
import { WIDGET_STYLES } from './embed-styles'

export interface WidgetConfig {
  apiUrl: string
  orgId: string
  theme: 'light' | 'dark'
  position: 'bottom-right' | 'bottom-left'
  title: string
  placeholder: string
  primaryColor: string
  buttonLabel: string
}

const DEFAULT_CONFIG: WidgetConfig = {
  apiUrl: '',
  orgId: '',
  theme: 'light',
  position: 'bottom-right',
  title: 'AutoBot Chat',
  placeholder: 'Ask me anything…',
  primaryColor: '#6366f1',
  buttonLabel: 'Open AutoBot chat',
}

export class AutobotWidget extends HTMLElement {
  static observedAttributes = [
    'data-api-url',
    'data-org-id',
    'data-theme',
    'data-position',
    'data-title',
    'data-placeholder',
    'data-primary-color',
    'data-button-label',
  ]

  private _shadow: ShadowRoot
  private _app: App | null = null
  private _config: WidgetConfig = { ...DEFAULT_CONFIG }

  constructor() {
    super()
    this._shadow = this.attachShadow({ mode: 'open' })
  }

  connectedCallback(): void {
    this._readAttributes()
    this._mount()
  }

  disconnectedCallback(): void {
    this._app?.unmount()
    this._app = null
  }

  attributeChangedCallback(name: string, _old: string | null, next: string | null): void {
    this._readAttributes()
    // If already mounted, re-mount with updated config
    if (this._app) {
      this._app.unmount()
      this._app = null
      this._mount()
    }
  }

  private _readAttributes(): void {
    const get = (attr: string): string | null => this.getAttribute(attr)
    this._config = {
      apiUrl: get('data-api-url') ?? DEFAULT_CONFIG.apiUrl,
      orgId: get('data-org-id') ?? DEFAULT_CONFIG.orgId,
      theme: (get('data-theme') as WidgetConfig['theme']) ?? DEFAULT_CONFIG.theme,
      position: (get('data-position') as WidgetConfig['position']) ?? DEFAULT_CONFIG.position,
      title: get('data-title') ?? DEFAULT_CONFIG.title,
      placeholder: get('data-placeholder') ?? DEFAULT_CONFIG.placeholder,
      primaryColor: get('data-primary-color') ?? DEFAULT_CONFIG.primaryColor,
      buttonLabel: get('data-button-label') ?? DEFAULT_CONFIG.buttonLabel,
    }
  }

  private _mount(): void {
    // Inject styles into shadow root
    const style = document.createElement('style')
    style.textContent = WIDGET_STYLES
    this._shadow.appendChild(style)

    // Mount point
    const mountPoint = document.createElement('div')
    mountPoint.setAttribute('id', 'autobot-root')
    this._shadow.appendChild(mountPoint)

    const config = { ...this._config }
    this._app = createApp(EmbedChatApp, { config })
    this._app.mount(mountPoint)
  }
}

// ---------------------------------------------------------------------------
// Inline Vue component — no .vue SFC to avoid external compilation dependency
// ---------------------------------------------------------------------------

interface Message {
  id: number
  role: 'user' | 'assistant'
  content: string
  pending?: boolean
}

const EmbedChatApp = defineComponent({
  name: 'EmbedChatApp',
  props: {
    config: {
      type: Object as () => WidgetConfig,
      required: true,
    },
  },
  setup(props) {
    const open = ref(false)
    const input = ref('')
    const messages = ref<Message[]>([])
    const loading = ref(false)
    const errorMsg = ref('')
    let nextId = 1
    let abortController: AbortController | null = null

    onUnmounted(() => {
      abortController?.abort()
      abortController = null
    })

    // Dynamically computed CSS custom properties
    const cssVars = computed(() => ({
      '--ab-primary': props.config.primaryColor,
      '--ab-primary-dark': darken(props.config.primaryColor, 15),
    }))

    function toggleOpen() {
      open.value = !open.value
    }

    async function sendMessage(): Promise<void> {
      const text = input.value.trim()
      if (!text || loading.value) return

      errorMsg.value = ''
      messages.value.push({ id: nextId++, role: 'user', content: text })
      input.value = ''

      const placeholder: Message = { id: nextId++, role: 'assistant', content: '', pending: true }
      messages.value.push(placeholder)
      loading.value = true

      await nextTick()
      scrollToBottom()

      abortController = new AbortController()
      try {
        const apiBase = props.config.apiUrl.replace(/\/$/, '')
        const endpoint = `${apiBase}/api/chats/embed/message`
        const resp = await fetch(endpoint, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(props.config.orgId ? { 'X-Org-Id': props.config.orgId } : {}),
          },
          body: JSON.stringify({ message: text }),
          signal: abortController.signal,
        })

        if (!resp.ok) {
          throw new Error(`HTTP ${resp.status}`)
        }

        const contentType = resp.headers.get('Content-Type') ?? ''

        if (contentType.includes('text/event-stream')) {
          // SSE streaming response
          const reader = resp.body?.getReader()
          const decoder = new TextDecoder()
          if (reader) {
            let buf = ''
            while (true) {
              const { done, value } = await reader.read()
              if (done) break
              buf += decoder.decode(value, { stream: true })
              const lines = buf.split('\n')
              buf = lines.pop() ?? ''
              for (const line of lines) {
                if (line.startsWith('data: ')) {
                  const chunk = line.slice(6).trim()
                  if (chunk === '[DONE]') continue
                  try {
                    const parsed = JSON.parse(chunk)
                    const delta = parsed?.content ?? parsed?.delta ?? parsed?.text ?? ''
                    placeholder.content += delta
                    await nextTick()
                    scrollToBottom()
                  } catch {
                    // non-JSON chunk — treat as raw text
                    placeholder.content += chunk
                    await nextTick()
                    scrollToBottom()
                  }
                }
              }
            }
          }
        } else {
          // Plain JSON response
          const data = await resp.json()
          placeholder.content = data?.content ?? data?.message ?? data?.response ?? JSON.stringify(data)
        }

        placeholder.pending = false
      } catch (err: unknown) {
        if (err instanceof Error && err.name === 'AbortError') {
          // Component unmounted mid-stream — discard silently
          placeholder.pending = false
          return
        }
        placeholder.content = 'Sorry, something went wrong. Please try again.'
        placeholder.pending = false
        errorMsg.value = err instanceof Error ? err.message : String(err)
      } finally {
        abortController = null
        loading.value = false
        await nextTick()
        scrollToBottom()
      }
    }

    function onKeydown(e: KeyboardEvent): void {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        void sendMessage()
      }
    }

    // scrollToBottom queries the shadow DOM using the stable class name.
    // Vue template refs inside render() require a specific typing ceremony; querying
    // by class is simpler and safe because the shadow root is isolated.
    function scrollToBottom(): void {
      const mountPoint = getCurrentInstance()?.vnode?.el as HTMLElement | null | undefined
      const shadowRoot = mountPoint?.getRootNode()
      if (shadowRoot instanceof ShadowRoot) {
        const el = shadowRoot.querySelector<HTMLElement>('.ab-messages-list')
        if (el) el.scrollTop = el.scrollHeight
      }
    }

    return {
      open,
      input,
      messages,
      loading,
      errorMsg,
      cssVars,
      toggleOpen,
      sendMessage,
      onKeydown,
    }
  },
  render() {
    const { config, open, input, messages, loading, cssVars, toggleOpen, sendMessage, onKeydown } = this

    const posClass = config.position === 'bottom-left' ? 'ab-pos-left' : 'ab-pos-right'

    return h('div', { class: `ab-widget ${posClass}`, style: cssVars }, [
      // Floating action button
      h('button', {
        class: 'ab-fab',
        onClick: toggleOpen,
        'aria-label': config.buttonLabel,
        'aria-expanded': open,
        'aria-haspopup': 'dialog',
      }, [
        open
          ? h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2', 'aria-hidden': 'true' }, [
              h('path', { 'stroke-linecap': 'round', 'stroke-linejoin': 'round', d: 'M6 18L18 6M6 6l12 12' }),
            ])
          : h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2', 'aria-hidden': 'true' }, [
              h('path', { 'stroke-linecap': 'round', 'stroke-linejoin': 'round', d: 'M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z' }),
            ]),
      ]),

      // Chat panel
      open
        ? h('div', {
            class: 'ab-panel',
            role: 'dialog',
            'aria-modal': 'true',
            'aria-label': config.title,
          }, [
            // Header
            h('div', { class: 'ab-header' }, [
              h('span', { class: 'ab-title' }, config.title),
              h('button', {
                class: 'ab-close',
                onClick: toggleOpen,
                'aria-label': 'Close chat',
              }, '✕'),
            ]),

            // Messages — 'ab-messages-list' is a stable class so scrollToBottom can query it
            h('div', { class: 'ab-messages ab-messages-list' },
              messages.length === 0
                ? [h('div', { class: 'ab-empty' }, 'How can I help you today?')]
                : messages.map(msg =>
                    h('div', {
                      key: msg.id,
                      class: `ab-msg ab-msg-${msg.role}${msg.pending ? ' ab-pending' : ''}`,
                    }, [
                      h('div', { class: 'ab-bubble' }, [
                        msg.pending && !msg.content
                          ? h('span', { class: 'ab-dots' }, [
                              h('span'), h('span'), h('span'),
                            ])
                          : msg.content,
                      ]),
                    ])
                  )
            ),

            // Input row
            h('div', { class: 'ab-input-row' }, [
              h('textarea', {
                class: 'ab-input',
                value: input,
                rows: 1,
                placeholder: config.placeholder,
                'aria-label': config.placeholder,
                onInput: (e: Event) => {
                  this.input = (e.target as HTMLTextAreaElement).value
                },
                onKeydown,
              }),
              h('button', {
                class: 'ab-send',
                onClick: sendMessage,
                disabled: loading || !input.trim(),
                'aria-label': 'Send message',
              }, [
                h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2', 'aria-hidden': 'true' }, [
                  h('path', { 'stroke-linecap': 'round', 'stroke-linejoin': 'round', d: 'M12 19l9 2-9-18-9 18 9-2zm0 0v-8' }),
                ]),
              ]),
            ]),
          ])
        : null,
    ])
  },
})

// Simple hex darkener for button hover states
function darken(hex: string, amount: number): string {
  const clean = hex.replace('#', '')
  if (clean.length !== 6) return hex
  const num = parseInt(clean, 16)
  const r = Math.max(0, (num >> 16) - amount)
  const g = Math.max(0, ((num >> 8) & 0xff) - amount)
  const b = Math.max(0, (num & 0xff) - amount)
  return `#${((r << 16) | (g << 8) | b).toString(16).padStart(6, '0')}`
}
