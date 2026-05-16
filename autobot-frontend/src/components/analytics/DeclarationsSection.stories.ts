import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import DeclarationsSection from './DeclarationsSection.vue';

const sampleDeclarations = [
  {
    name: 'get_redis_client',
    file_path: 'autobot-backend/utils/redis.py',
    line_number: 12,
    is_exported: true,
    declaration_type: 'function',
  },
  {
    name: 'ChatController',
    file_path: 'autobot-frontend/src/controllers/ChatController.ts',
    line_number: 5,
    is_exported: true,
    declaration_type: 'class',
  },
  {
    name: 'API_BASE_URL',
    file_path: 'autobot-frontend/src/config/ssot-config.ts',
    line_number: 3,
    is_exported: true,
    declaration_type: 'variable',
  },
  {
    name: 'MessageType',
    file_path: 'autobot-backend/schemas/common.py',
    line_number: 22,
    is_exported: false,
    declaration_type: 'type',
  },
];

const meta = {
  title: 'Components/Analytics/DeclarationsSection',
  component: DeclarationsSection,
  tags: ['autodocs'],
  argTypes: {
    declarations: { control: 'object' },
    loading: { control: 'boolean' },
  },
} as Meta<typeof DeclarationsSection>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {
    declarations: sampleDeclarations,
    loading: false,
  },
};

export const Loading: Story = {
  args: {
    declarations: [],
    loading: true,
  },
};

export const Empty: Story = {
  args: {
    declarations: [],
    loading: false,
  },
};

export const LargeDataset: Story = {
  args: {
    declarations: Array.from({ length: 50 }, (_, i) => ({
      name: `function_${i}`,
      file_path: `module_${i % 5}/file.py`,
      line_number: (i + 1) * 10,
      is_exported: i % 3 === 0,
      declaration_type: ['function', 'class', 'variable', 'type'][i % 4],
    })),
    loading: false,
  },
};
