import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import TerminalWindow from './TerminalWindow.vue';

const meta = {
  title: 'Components/Terminal/TerminalWindow',
  component: TerminalWindow,
  tags: ['autodocs'],
  // TerminalWindow is a self-contained orchestrator component that manages its
  // own internal state via composables (useTerminalService, useTabCompletion,
  // useI18n, useRoute, useRouter).  Stories use render functions with container
  // sizing to showcase the full layout in different viewport contexts.
  argTypes: {},
} as Meta<typeof TerminalWindow>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

// NOTE: TerminalWindow uses WebSocket, Vue Router, and i18n.  In Storybook
// these are provided by the global decorators configured in .storybook/preview.ts.
// The terminal will render in disconnected state since there is no live backend.

export const Default: Story = {
  render: () => ({
    components: { TerminalWindow },
    template: `
      <div style="width: 900px; height: 600px; display: flex; flex-direction: column;">
        <TerminalWindow />
      </div>
    `,
  }),
};

export const NarrowViewport: Story = {
  render: () => ({
    components: { TerminalWindow },
    template: `
      <div style="width: 500px; height: 400px; display: flex; flex-direction: column;">
        <TerminalWindow />
      </div>
    `,
  }),
};

export const FullScreen: Story = {
  render: () => ({
    components: { TerminalWindow },
    template: `
      <div style="width: 100vw; height: 100vh; display: flex; flex-direction: column;">
        <TerminalWindow />
      </div>
    `,
  }),
};

export const EmbeddedInPanel: Story = {
  render: () => ({
    components: { TerminalWindow },
    template: `
      <div style="display: flex; gap: 16px; padding: 16px; background: #0f172a; height: 600px;">
        <div style="flex: 1; background: #1e293b; border-radius: 8px; padding: 12px;">
          <p style="color: #94a3b8; font-size: 14px; margin: 0 0 8px 0;">Side panel content</p>
        </div>
        <div style="flex: 2; display: flex; flex-direction: column;">
          <TerminalWindow />
        </div>
      </div>
    `,
  }),
};
