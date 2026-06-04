import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import ShareSourceModal from './ShareSourceModal.vue';

const sampleSource = {
  id: 'src-001',
  name: 'AutoBot Backend',
  source_type: 'github' as const,
  repo: 'mrveiss/AutoBot-AI',
  branch: 'Dev_new_gui',
  access: 'private' as const,
  status: 'ready' as const,
};

const meta = {
  title: 'Components/Analytics/ShareSourceModal',
  component: ShareSourceModal,
  tags: ['autodocs'],
  argTypes: {
    visible: { control: 'boolean' },
    source: { control: 'object' },
  },
} as Meta<typeof ShareSourceModal>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {
    visible: true,
    source: sampleSource,
  },
};

export const LocalSource: Story = {
  args: {
    visible: true,
    source: {
      id: 'src-002',
      name: 'Local Dev',
      source_type: 'local',
      clone_path: '/opt/autobot',
      access: 'shared',
      status: 'configured',
    },
  },
};

export const Hidden: Story = {
  args: {
    visible: false,
    source: sampleSource,
  },
};

export const NoSource: Story = {
  args: {
    visible: true,
    source: null,
  },
};
