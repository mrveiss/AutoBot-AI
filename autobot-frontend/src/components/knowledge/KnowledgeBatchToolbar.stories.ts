import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import KnowledgeBatchToolbar from './KnowledgeBatchToolbar.vue'

const meta = {
  title: 'Components/Knowledge/KnowledgeBatchToolbar',
  component: KnowledgeBatchToolbar,
  tags: ['autodocs'],
  argTypes: {
    hasSelection: { control: 'boolean' },
    selectionCount: { control: 'number' },
    canVectorize: { control: 'boolean' },
    isVectorizing: { control: 'boolean' },
  },
} as Meta<typeof KnowledgeBatchToolbar>

export default meta
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>

export const Default: Story = {
  args: {
    hasSelection: true,
    selectionCount: 3,
    canVectorize: true,
    isVectorizing: false,
  },
}

export const Vectorizing: Story = {
  args: {
    hasSelection: true,
    selectionCount: 3,
    canVectorize: true,
    isVectorizing: true,
  },
}

export const CannotVectorize: Story = {
  args: {
    hasSelection: true,
    selectionCount: 2,
    canVectorize: false,
    isVectorizing: false,
  },
}

export const Hidden: Story = {
  args: {
    hasSelection: false,
    selectionCount: 0,
    canVectorize: false,
    isVectorizing: false,
  },
}
