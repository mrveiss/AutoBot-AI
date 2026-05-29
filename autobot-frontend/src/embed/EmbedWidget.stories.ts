import type { Meta } from '@storybook/html'
import { AutobotWidget } from './AutobotWidget'

if (!customElements.get('autobot-widget')) {
  customElements.define('autobot-widget', AutobotWidget)
}

const meta = {
  title: 'Embed/AutobotWidget',
  tags: ['autodocs'],
  argTypes: {
    apiUrl:       { control: 'text',   description: 'AutoBot backend URL' },
    orgId:        { control: 'text',   description: 'Organisation ID' },
    theme:        { control: { type: 'select' }, options: ['light', 'dark'] },
    position:     { control: { type: 'select' }, options: ['bottom-right', 'bottom-left'] },
    title:        { control: 'text' },
    placeholder:  { control: 'text' },
    primaryColor: { control: 'color' },
    buttonLabel:  { control: 'text' },
  },
  args: {
    apiUrl: 'http://localhost:8001',
    orgId: 'demo',
    theme: 'light',
    position: 'bottom-right',
    title: 'AutoBot Chat',
    placeholder: 'Ask me anything…',
    primaryColor: '#6366f1',
    buttonLabel: 'Open AutoBot chat',
  },
  render: (args: Record<string, string>) => {
    const el = document.createElement('autobot-widget')
    el.setAttribute('data-api-url',      args.apiUrl ?? '')
    el.setAttribute('data-org-id',       args.orgId ?? '')
    el.setAttribute('data-theme',        args.theme ?? 'light')
    el.setAttribute('data-position',     args.position ?? 'bottom-right')
    el.setAttribute('data-title',        args.title ?? 'AutoBot Chat')
    el.setAttribute('data-placeholder',  args.placeholder ?? '')
    el.setAttribute('data-primary-color', args.primaryColor ?? '#6366f1')
    el.setAttribute('data-button-label', args.buttonLabel ?? 'Open AutoBot chat')
    return el
  },
} as Meta

export default meta

export const Default = {}

export const BottomLeft = {
  args: { position: 'bottom-left' },
}

export const CustomColor = {
  args: { primaryColor: '#059669', title: 'Support Chat' },
}
