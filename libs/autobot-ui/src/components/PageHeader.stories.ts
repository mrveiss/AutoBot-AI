// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import PageHeader from './PageHeader.vue'
import Breadcrumb from './Breadcrumb.vue'
import BaseButton from './BaseButton.vue'

const meta = {
  title: 'Kit/PageHeader',
  component: PageHeader,
  argTypes: {
    level: { control: { type: 'select' }, options: [1, 2, 3] },
    size: { control: { type: 'select' }, options: ['sm', 'md', 'lg', 'xl'] },
  },
} as Meta<typeof PageHeader>

export default meta
type Story = StoryObj<Record<string, unknown>>

const trail = [
  { label: 'Portfolios', to: '#portfolios' },
  { label: 'Platform', to: '#platform' },
  { label: 'Release 2' },
]

export const TitleOnly: Story = { args: { title: 'Code analytics' } }

export const TitleAndSubtitle: Story = {
  args: { title: 'Release planning', subtitle: '3 programs, 12 projects' },
}

export const WithActions: Story = {
  args: { title: 'Files', subtitle: '/home/project' },
  render: (args) => ({
    components: { PageHeader, BaseButton },
    setup: () => ({ args }),
    template: `<PageHeader v-bind="args">
      <template #actions>
        <BaseButton variant="outline" size="sm">New folder</BaseButton>
        <BaseButton size="sm">Upload</BaseButton>
      </template>
    </PageHeader>`,
  }),
}

export const WithBreadcrumb: Story = {
  args: { title: 'Release 2' },
  render: (args) => ({
    components: { PageHeader, Breadcrumb },
    setup: () => ({ args, trail }),
    template: `<PageHeader v-bind="args">
      <template #breadcrumb><Breadcrumb :items="trail" label="Breadcrumb" /></template>
    </PageHeader>`,
  }),
}

export const WithToolbar: Story = {
  args: { title: 'Knowledge' },
  render: (args) => ({
    components: { PageHeader },
    setup: () => ({ args }),
    template: `<PageHeader v-bind="args"><input type="search" placeholder="Search" /></PageHeader>`,
  }),
}
