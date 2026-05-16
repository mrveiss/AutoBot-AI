import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import ProblemsReportSection from './ProblemsReportSection.vue';

const sampleProblems = [
  {
    severity: 'critical',
    description: 'Unhandled exception in request handler',
    file_path: 'autobot-backend/api/chat.py',
    line_number: 88,
    suggestion: 'Add proper error handling',
    type: 'exception',
  },
  {
    severity: 'high',
    message: 'Blocking synchronous call in async context',
    file_path: 'autobot-backend/agents/base.py',
    line_number: 42,
    suggestion: 'Use asyncio.run_in_executor',
    problem_type: 'async_violation',
  },
  {
    severity: 'medium',
    description: 'Missing type annotation',
    file_path: 'autobot-backend/utils/helpers.py',
    line: 15,
    suggestion: 'Add return type annotation',
    category: 'typing',
  },
  {
    severity: 'low',
    description: 'Unused import',
    file_path: 'autobot-frontend/src/views/Dashboard.vue',
    line_number: 3,
    suggestion: 'Remove unused import',
    type: 'import',
  },
];

const meta = {
  title: 'Components/Analytics/ProblemsReportSection',
  component: ProblemsReportSection,
  tags: ['autodocs'],
  argTypes: {
    problems: { control: 'object' },
  },
} as Meta<typeof ProblemsReportSection>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {
    problems: sampleProblems,
  },
};

export const Empty: Story = {
  args: {
    problems: [],
  },
};

export const CriticalOnly: Story = {
  args: {
    problems: sampleProblems.filter(p => p.severity === 'critical'),
  },
};

export const LargeDataset: Story = {
  args: {
    problems: Array.from({ length: 40 }, (_, i) => ({
      severity: ['critical', 'high', 'medium', 'low'][i % 4],
      description: `Problem description ${i + 1}`,
      file_path: `module_${i % 5}/file_${i}.py`,
      line_number: (i + 1) * 5,
      suggestion: 'Fix this issue',
      type: ['exception', 'async_violation', 'typing', 'import'][i % 4],
    })),
  },
};
