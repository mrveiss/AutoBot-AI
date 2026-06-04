import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import KnowledgeGraph3D from './KnowledgeGraph3D.vue'

const meta = {
  title: 'Components/Knowledge/KnowledgeGraph3D',
  component: KnowledgeGraph3D,
  tags: ['autodocs'],
  argTypes: {
    entities: { control: 'object' },
    edges: { control: 'object' },
  },
} as Meta<typeof KnowledgeGraph3D>

export default meta
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>

export const Empty: Story = {
  args: {
    entities: [],
    edges: [],
  },
}

export const WithEntities: Story = {
  args: {
    entities: [
      { id: 'e1', name: 'AutoBot', type: 'system', observations: ['AI-powered automation platform'] },
      { id: 'e2', name: 'Redis', type: 'technology', observations: ['In-memory data store'] },
      { id: 'e3', name: 'FastAPI', type: 'technology', observations: ['Python web framework'] },
    ],
    edges: [
      { from: 'e1', to: 'e2', type: 'uses' },
      { from: 'e1', to: 'e3', type: 'uses' },
    ],
  },
}

export const LargeGraph: Story = {
  args: {
    entities: Array.from({ length: 20 }, (_, i) => ({
      id: `entity-${i}`,
      name: `Entity ${i}`,
      type: i % 3 === 0 ? 'system' : i % 3 === 1 ? 'technology' : 'concept',
      observations: [`Observation for entity ${i}`],
    })),
    edges: Array.from({ length: 15 }, (_, i) => ({
      from: `entity-${i % 10}`,
      to: `entity-${(i + 3) % 20}`,
      type: 'relates_to',
    })),
  },
}
