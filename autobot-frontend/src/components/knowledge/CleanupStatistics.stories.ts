import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import CleanupStatistics from './CleanupStatistics.vue'

const meta = {
  title: 'Components/Knowledge/CleanupStatistics',
  component: CleanupStatistics,
  tags: ['autodocs'],
} as Meta<typeof CleanupStatistics>

export default meta
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>

export const Default: Story = {
  args: {},
}

export const Loading: Story = {
  args: {},
}

export const WithResults: Story = {
  args: {},
}

export const Clean: Story = {
  args: {},
}
