// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import VoiceConversationOverlay from './VoiceConversationOverlay.vue';

const meta = {
  title: 'Components/Chat/VoiceConversationOverlay',
  component: VoiceConversationOverlay,
  tags: ['autodocs'],
  argTypes: {},
} as Meta<typeof VoiceConversationOverlay>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

// VoiceConversationOverlay relies entirely on the useVoiceConversation composable
// for its state (isActive, bubbles, mode, etc.).  The overlay only renders when
// voiceConversation.isActive is true, so it will appear empty in Storybook
// without a mocked composable.  Stories below document the component and act as
// a visual regression anchor once the composable is stubbed in the test setup.

export const Default: Story = {
  args: {},
};
