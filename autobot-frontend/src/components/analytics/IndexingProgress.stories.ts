import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import IndexingProgress from './IndexingProgress.vue';

const meta = {
  title: 'Components/Analytics/IndexingProgress',
  component: IndexingProgress,
  tags: ['autodocs'],
  argTypes: {
    analyzing: { control: 'boolean' },
    analyzingCodeSmells: { control: 'boolean' },
    progressPercent: { control: { type: 'range', min: 0, max: 100 } },
    progressStatus: { control: 'text' },
    currentJobId: { control: 'text' },
    codeSmellsProgressTitle: { control: 'text' },
  },
} as Meta<typeof IndexingProgress>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {
    analyzing: true,
    currentJobId: 'job-abc12345',
    progressPercent: 55,
    progressStatus: 'Indexing Python files...',
    jobPhases: {
      phase_list: [
        { id: 'parse', name: 'Parse', status: 'completed' },
        { id: 'index', name: 'Index', status: 'running' },
        { id: 'store', name: 'Store', status: 'pending' },
      ],
    },
    jobBatches: { total_batches: 8, completed_batches: 4 },
    jobStats: {
      files_scanned: 88,
      problems_found: 5,
      functions_found: 220,
      classes_found: 30,
      items_stored: 880,
    },
    analyzingCodeSmells: false,
    codeSmellsProgressTitle: '',
  },
};

export const CodeSmellsAnalysis: Story = {
  args: {
    analyzing: false,
    currentJobId: null,
    progressPercent: 0,
    progressStatus: '',
    jobPhases: null,
    jobBatches: null,
    jobStats: null,
    analyzingCodeSmells: true,
    codeSmellsProgressTitle: 'Analyzing anti-patterns...',
  },
};

export const NoBatches: Story = {
  args: {
    analyzing: true,
    currentJobId: 'job-xyz98765',
    progressPercent: 20,
    progressStatus: 'Starting scan...',
    jobPhases: null,
    jobBatches: null,
    jobStats: null,
    analyzingCodeSmells: false,
    codeSmellsProgressTitle: '',
  },
};

export const Idle: Story = {
  args: {
    analyzing: false,
    currentJobId: null,
    progressPercent: 0,
    progressStatus: '',
    jobPhases: null,
    jobBatches: null,
    jobStats: null,
    analyzingCodeSmells: false,
    codeSmellsProgressTitle: '',
  },
};
