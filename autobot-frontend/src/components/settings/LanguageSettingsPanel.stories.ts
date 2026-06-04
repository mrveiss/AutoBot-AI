import type { Meta } from '@storybook/vue3';
import LanguageSettingsPanel from './LanguageSettingsPanel.vue';
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<any>;

const meta = {
  title: 'Components/Settings/LanguageSettingsPanel',
  component: LanguageSettingsPanel,
  tags: ['autodocs'],
  argTypes: {},
} as Meta<typeof LanguageSettingsPanel>;

export default meta;

// LanguageSettingsPanel has no external props; it reads from usePreferences /
// useAvailableLanguages composables on mount.

export const Default: Story = {
  name: 'Default',
  render: () => ({
    components: { LanguageSettingsPanel },
    template: `<LanguageSettingsPanel />`,
  }),
};

export const InCard: Story = {
  name: 'In Settings Card',
  render: () => ({
    components: { LanguageSettingsPanel },
    template: `
      <div style="max-width:560px;padding:24px;background:var(--bg-primary,#0f0f23)">
        <LanguageSettingsPanel />
      </div>
    `,
  }),
};

export const SuccessStatus: Story = {
  name: 'After Successful Change (render)',
  render: () => ({
    components: { LanguageSettingsPanel },
    template: `
      <div style="max-width:560px">
        <p style="color:#94a3b8;margin-bottom:12px;font-size:14px">
          Select a language from the dropdown to see the success status message.
        </p>
        <LanguageSettingsPanel />
      </div>
    `,
  }),
};

export const NarrowViewport: Story = {
  name: 'Narrow Viewport (mobile)',
  render: () => ({
    components: { LanguageSettingsPanel },
    template: `
      <div style="max-width:360px">
        <LanguageSettingsPanel />
      </div>
    `,
  }),
};
