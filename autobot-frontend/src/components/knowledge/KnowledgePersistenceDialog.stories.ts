import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import KnowledgePersistenceDialog from './KnowledgePersistenceDialog.vue'

const meta = {
  title: 'Components/Knowledge/KnowledgePersistenceDialog',
  component: KnowledgePersistenceDialog,
  tags: ['autodocs'],
} as Meta<typeof KnowledgePersistenceDialog>

export default meta
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>

export const Default: Story = {
  args: {},
}

export const WithItems: Story = {
  args: {},
}

export const Loading: Story = {
  args: {},
}
