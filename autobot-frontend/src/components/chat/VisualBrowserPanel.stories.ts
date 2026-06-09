// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import VisualBrowserPanel from './VisualBrowserPanel.vue';

const meta = {
  title: 'Components/Chat/VisualBrowserPanel',
  component: VisualBrowserPanel,
  tags: ['autodocs'],
  argTypes: {},
} as Meta<typeof VisualBrowserPanel>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

// VisualBrowserPanel manages all state internally (URL bar, screenshot,
// connection status). Stories show the visual shell; API and Playwright
// integration are not active in Storybook.

export const Default: Story = {
  args: {},
};
