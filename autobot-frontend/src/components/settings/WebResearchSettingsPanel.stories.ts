// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import WebResearchSettingsPanel from './WebResearchSettingsPanel.vue';
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<any>;

const meta = {
  title: 'Components/Settings/WebResearchSettingsPanel',
  component: WebResearchSettingsPanel,
  tags: ['autodocs'],
  argTypes: {},
} as Meta<typeof WebResearchSettingsPanel>;

export default meta;

// WebResearchSettingsPanel has no external props; all state is managed by
// useWebResearchStore (Pinia). Stories render the full form at its default
// store state.

export const Default: Story = {
  name: 'Default',
  render: () => ({
    components: { WebResearchSettingsPanel },
    template: `<WebResearchSettingsPanel />`,
  }),
};

export const InCard: Story = {
  name: 'In Settings Card',
  render: () => ({
    components: { WebResearchSettingsPanel },
    template: `
      <div style="max-width:680px;padding:24px;background:var(--bg-primary,#0f0f23)">
        <WebResearchSettingsPanel />
      </div>
    `,
  }),
};

export const EnabledState: Story = {
  name: 'Enabled – Research Active',
  render: () => ({
    components: { WebResearchSettingsPanel },
    template: `
      <div style="max-width:680px">
        <p style="color:#94a3b8;font-size:13px;margin-bottom:12px">
          Toggle the "Enable Web Research" switch to see the active state.
        </p>
        <WebResearchSettingsPanel />
      </div>
    `,
  }),
};

export const NarrowViewport: Story = {
  name: 'Narrow Viewport (mobile)',
  render: () => ({
    components: { WebResearchSettingsPanel },
    template: `
      <div style="max-width:400px">
        <WebResearchSettingsPanel />
      </div>
    `,
  }),
};

export const ResetInteraction: Story = {
  name: 'Reset Button Interaction',
  render: () => ({
    components: { WebResearchSettingsPanel },
    template: `
      <div style="max-width:680px">
        <p style="color:#94a3b8;font-size:13px;margin-bottom:12px">
          Modify any field then click Reset to revert all settings to defaults.
        </p>
        <WebResearchSettingsPanel />
      </div>
    `,
  }),
};
