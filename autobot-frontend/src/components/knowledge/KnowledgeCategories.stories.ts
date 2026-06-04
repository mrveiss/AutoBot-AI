import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import KnowledgeCategories from './KnowledgeCategories.vue'

const meta = {
  title: 'Components/Knowledge/KnowledgeCategories',
  component: KnowledgeCategories,
  tags: ['autodocs'],
} as Meta<typeof KnowledgeCategories>

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
