import type { Meta } from '@storybook/vue3';
import ChatInput from './ChatInput.vue';

const meta = {
  title: 'Components/Chat/ChatInput',
  component: ChatInput,
  tags: ['autodocs'],
} as Meta<typeof ChatInput>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<any>;

export const Default: Story = {
  render: () => ({
    components: { ChatInput },
    template: `<div style="padding:16px; background:#1e1e2e;"><ChatInput /></div>`,
  }),
};

export const WithAttachedFiles: Story = {
  render: () => ({
    components: { ChatInput },
    template: `<div style="padding:16px; background:#1e1e2e;"><ChatInput /></div>`,
  }),
};
