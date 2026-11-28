// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import { ref } from 'vue'
import BasePagination from './BasePagination.vue'

const meta = {
  title: 'Kit/BasePagination',
  component: BasePagination,
  argTypes: {
    totalPages: { control: 'number', description: 'Total pages, when known' },
    hasNext: { control: 'boolean', description: 'Another page exists (cursor paging)' },
    showFirstLast: { control: 'boolean' },
    disabled: { control: 'boolean' },
  },
} as Meta<typeof BasePagination>

export default meta
type Story = StoryObj<Record<string, unknown>>

const labels = { previous: 'Previous', next: 'Next', first: 'First', last: 'Last' }
const render = (args: Record<string, unknown>) => ({
  components: { BasePagination },
  setup: () => ({ args, page: ref(2), labels }),
  template: `<BasePagination v-model:page="page" v-bind="args" :labels="labels" label="Results pages">
    <template #summary>Page {{ page }}<template v-if="args.totalPages"> of {{ args.totalPages }}</template></template>
  </BasePagination>`,
})

export const KnownTotal: Story = { args: { totalPages: 7 }, render }
export const FirstAndLast: Story = { args: { totalPages: 7, showFirstLast: true }, render }
export const CursorPaging: Story = { args: { hasNext: true }, render }
