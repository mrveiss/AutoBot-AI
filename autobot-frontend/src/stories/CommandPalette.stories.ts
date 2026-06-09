// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3'
import { ref } from 'vue'
import CommandPalette from '@/components/CommandPalette.vue'

const meta = {
  title: 'Components/CommandPalette',
  component: CommandPalette,
  parameters: {
    docs: {
      description: {
        component:
          'Global command palette opened by Ctrl/Cmd+K. Supports keyboard navigation (↑↓ arrows, Enter to execute, Escape to close).'
      }
    }
  }
} satisfies Meta<typeof CommandPalette>

export default meta

export const OpenByDefault = {
  render: () => ({
    components: { CommandPalette },
    setup() {
      const paletteRef = ref<InstanceType<typeof CommandPalette> | null>(null)
      // Open automatically so reviewers can see it without pressing Ctrl+K
      setTimeout(() => paletteRef.value?.open(), 100)
      return { paletteRef }
    },
    template: `
      <div style="height: 400px; background: var(--autobot-bg-primary, #1a1a2e); border-radius: 8px; overflow: hidden;">
        <p style="padding: 16px; color: var(--autobot-text-secondary, #888); font-size: 14px;">
          Press <kbd>Ctrl/Cmd+K</kbd> to open the command palette (auto-opened below).
        </p>
        <CommandPalette ref="paletteRef" />
      </div>
    `
  })
}

export const WithSearchQuery = {
  render: () => ({
    components: { CommandPalette },
    setup() {
      const paletteRef = ref<InstanceType<typeof CommandPalette> | null>(null)
      setTimeout(() => {
        paletteRef.value?.open()
      }, 100)
      return { paletteRef }
    },
    template: `
      <div style="height: 400px; background: var(--autobot-bg-primary, #1a1a2e); border-radius: 8px; overflow: hidden;">
        <CommandPalette ref="paletteRef" />
      </div>
    `
  })
}
