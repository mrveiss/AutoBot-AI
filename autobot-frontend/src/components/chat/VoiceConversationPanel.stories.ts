import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import VoiceConversationPanel from './VoiceConversationPanel.vue';

const meta = {
  title: 'Components/Chat/VoiceConversationPanel',
  component: VoiceConversationPanel,
  tags: ['autodocs'],
  argTypes: {},
} as Meta<typeof VoiceConversationPanel>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

// VoiceConversationPanel derives all state from the useVoiceConversation
// composable (state, mode, bubbles, audioLevel, etc.).  Stories document the
// component shell and serve as a baseline for visual regression; full
// interactive behaviour requires a mocked composable in the test environment.

export const Default: Story = {
  args: {},
};
