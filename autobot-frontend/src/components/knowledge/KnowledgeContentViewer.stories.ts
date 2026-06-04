import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import KnowledgeContentViewer from './KnowledgeContentViewer.vue'

const meta = {
  title: 'Components/Knowledge/KnowledgeContentViewer',
  component: KnowledgeContentViewer,
  tags: ['autodocs'],
  argTypes: {
    selectedFile: { control: 'object' },
    content: { control: 'text' },
    isLoading: { control: 'boolean' },
    error: { control: 'text' },
  },
} as Meta<typeof KnowledgeContentViewer>

export default meta
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>

export const NoFileSelected: Story = {
  args: {
    selectedFile: null,
    content: '',
    isLoading: false,
    error: null,
  },
}

export const Loading: Story = {
  args: {
    selectedFile: { id: 'file-1', name: 'README.md', type: 'markdown', size: 2048, date: '2026-05-01' },
    content: '',
    isLoading: true,
    error: null,
  },
}

export const WithContent: Story = {
  args: {
    selectedFile: { id: 'file-1', name: 'README.md', type: 'markdown', size: 2048, date: '2026-05-01' },
    content: '# AutoBot Documentation\n\nThis is the AutoBot knowledge base README file.\n\n## Getting Started\n\nFollow the setup instructions below.',
    isLoading: false,
    error: null,
  },
}

export const WithError: Story = {
  args: {
    selectedFile: { id: 'file-1', name: 'config.json', type: 'json', size: 512, date: '2026-05-01' },
    content: '',
    isLoading: false,
    error: 'Failed to load file content. The file may be corrupted or inaccessible.',
  },
}
