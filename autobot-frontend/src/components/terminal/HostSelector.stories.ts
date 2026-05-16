import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import HostSelector from './HostSelector.vue';

const sampleHosts = [
  { id: 'main', name: 'Main Server', ip: '172.16.168.20', description: 'Primary AutoBot backend server' },
  { id: 'frontend', name: 'Frontend VM', ip: '172.16.168.21', description: 'Vue 3 frontend development VM' },
  { id: 'ai-stack', name: 'AI Stack', ip: '172.16.168.22', description: 'LLM inference and AI processing VM' },
];

const meta = {
  title: 'Components/Terminal/HostSelector',
  component: HostSelector,
  tags: ['autodocs'],
  argTypes: {
    modelValue: {
      control: 'text',
      description: 'Currently selected host ID (v-model)',
    },
    hosts: {
      control: 'object',
      description: 'List of available host configurations',
    },
    disabled: {
      control: 'boolean',
      description: 'Disable the host selector',
    },
    showDescription: {
      control: 'boolean',
      description: 'Show the description of the selected host below the selector',
    },
  },
} as Meta<typeof HostSelector>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {
    modelValue: 'main',
    hosts: sampleHosts,
    disabled: false,
    showDescription: true,
  },
};

export const WithoutDescription: Story = {
  args: {
    modelValue: 'frontend',
    hosts: sampleHosts,
    disabled: false,
    showDescription: false,
  },
};

export const Disabled: Story = {
  args: {
    modelValue: 'ai-stack',
    hosts: sampleHosts,
    disabled: true,
    showDescription: true,
  },
};

export const SingleHost: Story = {
  args: {
    modelValue: 'main',
    hosts: [sampleHosts[0]],
    disabled: false,
    showDescription: true,
  },
};

export const ManyHosts: Story = {
  args: {
    modelValue: 'main',
    hosts: [
      ...sampleHosts,
      { id: 'db', name: 'Database VM', ip: '172.16.168.23', description: 'PostgreSQL and Redis server' },
      { id: 'monitoring', name: 'Monitoring', ip: '172.16.168.24', description: 'Grafana and Prometheus' },
      { id: 'backup', name: 'Backup Server', ip: '192.0.2.100', description: 'Automated backup storage' },
    ],
    disabled: false,
    showDescription: true,
  },
};
