import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import KnowledgeMainCategories from './KnowledgeMainCategories.vue'

const meta = {
  title: 'Components/Knowledge/KnowledgeMainCategories',
  component: KnowledgeMainCategories,
  tags: ['autodocs'],
  argTypes: {
    categories: { control: 'object' },
    populationStates: { control: 'object' },
    kbConnected: { control: 'boolean' },
    kbFetchError: { control: 'boolean' },
  },
} as Meta<typeof KnowledgeMainCategories>

export default meta
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>

const sampleCategories = [
  { id: 'system', name: 'System Knowledge', description: 'System commands and configurations', icon: 'fas fa-cogs', color: '#3b82f6', count: 150 },
  { id: 'user-knowledge', name: 'User Knowledge', description: 'Personal knowledge entries', icon: 'fas fa-user', color: '#10b981', count: 42 },
  { id: 'docs', name: 'Documentation', description: 'Project documentation', icon: 'fas fa-book', color: '#f59e0b', count: 78 },
]

export const Default: Story = {
  args: {
    categories: sampleCategories,
    populationStates: {},
    kbConnected: true,
    kbFetchError: false,
  },
}

export const Populating: Story = {
  args: {
    categories: sampleCategories,
    populationStates: {
      system: { isPopulating: true, progress: 45 },
    },
    kbConnected: true,
    kbFetchError: false,
  },
}

export const Disconnected: Story = {
  args: {
    categories: sampleCategories,
    populationStates: {},
    kbConnected: false,
    kbFetchError: false,
  },
}

export const FetchError: Story = {
  args: {
    categories: [],
    populationStates: {},
    kbConnected: true,
    kbFetchError: true,
  },
}

export const EmptyKB: Story = {
  args: {
    categories: [
      { id: 'system', name: 'System Knowledge', description: 'System commands', icon: 'fas fa-cogs', color: '#3b82f6', count: 0 },
      { id: 'user-knowledge', name: 'User Knowledge', description: 'Personal knowledge', icon: 'fas fa-user', color: '#10b981', count: 0 },
    ],
    populationStates: {},
    kbConnected: true,
    kbFetchError: false,
  },
}
