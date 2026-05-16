import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import GraphRAGQuery from './GraphRAGQuery.vue'

const meta = {
  title: 'Components/Knowledge/GraphRAGQuery',
  component: GraphRAGQuery,
  tags: ['autodocs'],
} as Meta<typeof GraphRAGQuery>

export default meta
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>

export const Default: Story = {
  args: {},
}

export const Searching: Story = {
  args: {},
}

export const WithResults: Story = {
  args: {},
}

export const NoResults: Story = {
  args: {},
}
