import type { Meta } from '@storybook/vue3';
import FunctionCallGraph from './FunctionCallGraph.vue';

const meta = {
  title: 'Components/Charts/FunctionCallGraph',
  component: FunctionCallGraph,
  tags: ['autodocs'],
  argTypes: {
    title: {
      control: 'text',
      description: 'Chart title',
    },
    subtitle: {
      control: 'text',
      description: 'Chart subtitle',
    },
    height: {
      control: 'number',
      description: 'Graph container height in pixels',
    },
    loading: {
      control: 'boolean',
      description: 'Show loading state',
    },
    error: {
      control: 'text',
      description: 'Error message to display',
    },
  },
} as Meta<typeof FunctionCallGraph>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<any>;

const sampleData = {
  nodes: [
    { id: 'app.main', name: 'main', full_name: 'app.main', module: 'app', file: 'app/main.py', line: 1, is_async: false },
    { id: 'app.startup', name: 'startup', full_name: 'app.startup', module: 'app', file: 'app/main.py', line: 15, is_async: true },
    { id: 'db.connect', name: 'connect', full_name: 'db.connect', module: 'db', file: 'db/client.py', line: 8, is_async: true },
    { id: 'db.query', name: 'query', full_name: 'db.query', module: 'db', file: 'db/client.py', line: 42, is_async: true },
    { id: 'api.router', name: 'router', full_name: 'api.router', module: 'api', file: 'api/routes.py', line: 5, is_async: false },
    { id: 'api.handler', name: 'handler', full_name: 'api.handler', module: 'api', file: 'api/routes.py', line: 20, is_async: true },
  ],
  edges: [
    { from: 'app.main', to: 'app.startup', resolved: true, count: 1 },
    { from: 'app.startup', to: 'db.connect', resolved: true, count: 1 },
    { from: 'app.startup', to: 'api.router', resolved: true, count: 1 },
    { from: 'api.router', to: 'api.handler', resolved: true, count: 3 },
    { from: 'api.handler', to: 'db.query', resolved: true, count: 5 },
  ],
};

const sampleSummary = {
  total_functions: 6,
  connected_functions: 6,
  orphaned_functions: 0,
  total_call_relationships: 5,
  resolved_calls: 5,
  unresolved_calls: 0,
  top_callers: [
    { function: 'api.handler', calls: 5 },
    { function: 'app.startup', calls: 2 },
  ],
  most_called: [
    { function: 'db.query', calls: 5 },
    { function: 'api.handler', calls: 3 },
  ],
};

export const Default: Story = {
  args: {
    data: sampleData,
    summary: sampleSummary,
    orphanedFunctions: [],
    title: 'Function Call Graph',
    subtitle: 'Application call relationships',
    height: 600,
  },
};

export const WithOrphanedFunctions: Story = {
  args: {
    data: sampleData,
    summary: { ...sampleSummary, orphaned_functions: 2 },
    orphanedFunctions: [
      {
        id: 'utils.helper',
        name: 'helper',
        full_name: 'utils.helper',
        module: 'utils',
        class: null,
        file: 'utils/helpers.py',
        line: 12,
        is_async: false,
      },
      {
        id: 'utils.unused',
        name: 'unused',
        full_name: 'utils.unused',
        module: 'utils',
        class: null,
        file: 'utils/helpers.py',
        line: 30,
        is_async: false,
      },
    ],
    title: 'Function Call Graph (with Orphans)',
    height: 600,
  },
};

export const LoadingState: Story = {
  args: {
    data: { nodes: [], edges: [] },
    loading: true,
    height: 600,
  },
};

export const ErrorState: Story = {
  args: {
    data: { nodes: [], edges: [] },
    error: 'Failed to load call graph data.',
    height: 600,
  },
};

export const NoData: Story = {
  args: {
    data: { nodes: [], edges: [] },
    title: 'Empty Call Graph',
    height: 600,
  },
};
