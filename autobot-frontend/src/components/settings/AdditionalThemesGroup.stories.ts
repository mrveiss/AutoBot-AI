// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import AdditionalThemesGroup from './AdditionalThemesGroup.vue'

const meta = {
  title: 'Components/Settings/AdditionalThemesGroup',
  component: AdditionalThemesGroup,
  parameters: {
    layout: 'padded',
    docs: {
      description: {
        component:
          'SLM-deployed themes from the installed-theme registry, each badged Deployed via SLM, with a link to the SLM console.',
      },
    },
  },
} as Meta<typeof AdditionalThemesGroup>

export default meta
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>

export const Default: Story = {
  args: {},
  parameters: {
    docs: { description: { story: 'Shows the empty state when nothing is deployed.' } },
  },
  render: (args: Record<string, unknown>) => ({
    components: { AdditionalThemesGroup },
    setup() {
      return { args }
    },
    template: `<div class="max-w-3xl"><AdditionalThemesGroup v-bind="args" /></div>`,
  }),
}
