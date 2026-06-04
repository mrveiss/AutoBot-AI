import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import ReasoningTrace from './ReasoningTrace.vue';

const meta = {
  title: 'Components/Chat/ReasoningTrace',
  component: ReasoningTrace,
  tags: ['autodocs'],
  argTypes: {
    entries: {
      control: 'object',
      description: 'Array of TraceEntry objects representing reasoning steps',
    },
    isActive: {
      control: 'boolean',
      description: 'Whether the agent is currently reasoning (shows spinner)',
    },
  },
} as Meta<typeof ReasoningTrace>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

const sampleEntries = [
  { id: '1', kind: 'step_start', label: 'Starting task: analyze user request', durationMs: null },
  { id: '2', kind: 'plan', label: 'Plan: search KB, then summarize', durationMs: 12 },
  { id: '3', kind: 'tool_call', label: 'search_knowledge_base', detail: '{ "query": "nginx configuration" }', durationMs: null },
  { id: '4', kind: 'tool_result', label: 'search_knowledge_base result', detail: 'Found 3 relevant documents', durationMs: 340, success: true },
  { id: '5', kind: 'llm_chunk', label: 'Based on the documentation...', durationMs: null },
  { id: '6', kind: 'step_complete', label: 'Task completed successfully', durationMs: 1240 },
];

export const Default: Story = {
  args: {
    entries: sampleEntries,
    isActive: false,
  },
};

export const Active: Story = {
  args: {
    entries: sampleEntries.slice(0, 3),
    isActive: true,
  },
};

export const WithToolFailure: Story = {
  args: {
    entries: [
      { id: '1', kind: 'step_start', label: 'Starting web search', durationMs: null },
      { id: '2', kind: 'tool_call', label: 'web_search', detail: '{ "query": "latest news" }', durationMs: null },
      { id: '3', kind: 'tool_result', label: 'web_search failed', detail: 'Connection timeout', durationMs: 5000, success: false },
    ],
    isActive: false,
  },
};

export const Empty: Story = {
  args: {
    entries: [],
    isActive: false,
  },
};
