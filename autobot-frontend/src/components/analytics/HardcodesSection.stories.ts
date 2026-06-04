import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import HardcodesSection from './HardcodesSection.vue';

const sampleHardcodes = [
  {
    type: 'url',
    file: 'autobot-backend/config.py',
    line: 14,
    value: 'http://localhost:8001',
    variable_name: 'BACKEND_URL',
    severity: 'high',
    suggested_env_var: 'AUTOBOT_BACKEND_URL',
  },
  {
    type: 'port',
    file: 'autobot-backend/main.py',
    line: 55,
    value: '8080',
    variable_name: null,
    severity: 'medium',
    suggested_env_var: 'AUTOBOT_PORT',
  },
  {
    type: 'magic_number',
    file: 'autobot-backend/cache.py',
    line: 30,
    value: '3600',
    variable_name: 'ttl',
    severity: 'low',
    suggested_env_var: 'CACHE_TTL_SECONDS',
  },
];

const meta = {
  title: 'Components/Analytics/HardcodesSection',
  component: HardcodesSection,
  tags: ['autodocs'],
  argTypes: {
    hardcodes: { control: 'object' },
    loading: { control: 'boolean' },
  },
} as Meta<typeof HardcodesSection>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {
    hardcodes: sampleHardcodes,
    loading: false,
  },
};

export const Loading: Story = {
  args: {
    hardcodes: [],
    loading: true,
  },
};

export const Empty: Story = {
  args: {
    hardcodes: [],
    loading: false,
  },
};

export const HighSeverityOnly: Story = {
  args: {
    hardcodes: sampleHardcodes.filter(h => h.severity === 'high'),
    loading: false,
  },
};
