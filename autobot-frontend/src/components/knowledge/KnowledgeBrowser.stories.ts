import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import KnowledgeBrowser from './KnowledgeBrowser.vue'

const meta = {
  title: 'Components/Knowledge/KnowledgeBrowser',
  component: KnowledgeBrowser,
  tags: ['autodocs'],
} as Meta<typeof KnowledgeBrowser>

export default meta
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>

export const Default: Story = {
  args: {},
}

export const Loading: Story = {
  args: {},
}

export const Empty: Story = {
  args: {},
}
