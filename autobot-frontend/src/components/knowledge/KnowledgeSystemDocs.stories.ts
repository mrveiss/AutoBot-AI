import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import KnowledgeSystemDocs from './KnowledgeSystemDocs.vue'

const meta = {
  title: 'Components/Knowledge/KnowledgeSystemDocs',
  component: KnowledgeSystemDocs,
  tags: ['autodocs'],
} as Meta<typeof KnowledgeSystemDocs>

export default meta
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>

export const Default: Story = {
  args: {},
}

export const Loading: Story = {
  args: {},
}

export const WithDocumentSelected: Story = {
  args: {},
}

export const Empty: Story = {
  args: {},
}
