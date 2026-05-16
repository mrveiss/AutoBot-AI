import type { Meta } from '@storybook/vue3';
import VoiceSettingsPanel from './VoiceSettingsPanel.vue';
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<any>;

const meta = {
  title: 'Components/Settings/VoiceSettingsPanel',
  component: VoiceSettingsPanel,
  tags: ['autodocs'],
  argTypes: {},
} as Meta<typeof VoiceSettingsPanel>;

export default meta;

// VoiceSettingsPanel has no external props; it fetches voice profiles via
// useVoiceProfiles composable on mount.

export const Default: Story = {
  name: 'Default (fetches voices on mount)',
  render: () => ({
    components: { VoiceSettingsPanel },
    template: `<VoiceSettingsPanel />`,
  }),
};

export const InCard: Story = {
  name: 'In Settings Card',
  render: () => ({
    components: { VoiceSettingsPanel },
    template: `
      <div style="max-width:520px;padding:20px;background:var(--bg-secondary,#1a1a2e);border-radius:8px">
        <VoiceSettingsPanel />
      </div>
    `,
  }),
};

export const WithAddDialogHint: Story = {
  name: 'Add Voice Dialog Hint',
  render: () => ({
    components: { VoiceSettingsPanel },
    template: `
      <div style="max-width:520px;padding:20px">
        <p style="color:#94a3b8;font-size:13px;margin-bottom:12px">
          Click "Add Voice Profile" to open the voice creation dialog.
        </p>
        <VoiceSettingsPanel />
      </div>
    `,
  }),
};

export const NarrowViewport: Story = {
  name: 'Narrow Viewport (mobile)',
  render: () => ({
    components: { VoiceSettingsPanel },
    template: `
      <div style="max-width:360px;padding:12px">
        <VoiceSettingsPanel />
      </div>
    `,
  }),
};

export const LoadingState: Story = {
  name: 'Loading State (render)',
  render: () => ({
    components: { VoiceSettingsPanel },
    template: `
      <div style="max-width:520px">
        <p style="color:#94a3b8;font-size:13px;margin-bottom:8px">
          Loading spinner visible before voices are fetched.
        </p>
        <VoiceSettingsPanel />
      </div>
    `,
  }),
};
