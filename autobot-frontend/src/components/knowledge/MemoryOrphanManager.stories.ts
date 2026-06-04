import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import MemoryOrphanManager from './MemoryOrphanManager.vue'

const meta = {
  title: 'Components/Knowledge/MemoryOrphanManager',
  component: MemoryOrphanManager,
  tags: ['autodocs'],
} as Meta<typeof MemoryOrphanManager>

export default meta
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>

export const Default: Story = {
  args: {},
}

export const Scanning: Story = {
  args: {},
}

export const WithOrphans: Story = {
  args: {},
}

export const Clean: Story = {
  args: {},
}
