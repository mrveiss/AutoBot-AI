import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import KnowledgeAdvanced from './KnowledgeAdvanced.vue'

const meta = {
  title: 'Components/Knowledge/KnowledgeAdvanced',
  component: KnowledgeAdvanced,
  tags: ['autodocs'],
} as Meta<typeof KnowledgeAdvanced>

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
