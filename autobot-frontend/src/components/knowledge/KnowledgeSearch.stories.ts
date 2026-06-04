import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import KnowledgeSearch from './KnowledgeSearch.vue'

const meta = {
  title: 'Components/Knowledge/KnowledgeSearch',
  component: KnowledgeSearch,
  tags: ['autodocs'],
} as Meta<typeof KnowledgeSearch>

export default meta
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>

export const Default: Story = {
  args: {},
}

export const TraditionalMode: Story = {
  args: {},
}

export const RAGMode: Story = {
  args: {},
}

export const WithResults: Story = {
  args: {},
}

export const Loading: Story = {
  args: {},
}
