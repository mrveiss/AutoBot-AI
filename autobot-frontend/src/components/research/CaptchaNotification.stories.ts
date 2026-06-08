// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import CaptchaNotification from './CaptchaNotification.vue';

const meta = {
  title: 'UI/Singletons/CaptchaNotification',
  component: CaptchaNotification,
  argTypes: {},
} as Meta<typeof CaptchaNotification>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  render: () => ({
    components: { CaptchaNotification },
    template: `
      <div>
        <p class="mb-4 text-sm text-gray-600">
          CaptchaNotification is a singleton component that displays human-in-the-loop CAPTCHA solving prompts.
          It is driven by the <code>useCaptchaStatus()</code> composable and manages state internally.
          When a CAPTCHA is detected during research tasks, this notification appears in the bottom-right corner.
        </p>
        <CaptchaNotification />
      </div>
    `,
  }),
};

export const InContext: Story = {
  render: () => ({
    components: { CaptchaNotification },
    template: `
      <div class="border rounded overflow-hidden bg-white" style="min-height: 400px;">
        <div class="p-6 border-b bg-gray-50">
          <h3 class="font-semibold text-lg mb-2">Research Task View</h3>
          <p class="text-sm text-gray-600">
            When research encounters a CAPTCHA barrier, the notification appears as a floating card.
            Users can open a VNC connection, mark it as solved, or skip the source.
          </p>
        </div>
        <div class="p-6">
          <p class="text-sm text-gray-500 mb-4">
            Research content would render here. The CAPTCHA notification is positioned fixed in the bottom-right corner.
          </p>
          <CaptchaNotification />
        </div>
      </div>
    `,
  }),
};

export const StackingBehavior: Story = {
  render: () => ({
    components: { CaptchaNotification },
    template: `
      <div class="border rounded overflow-hidden bg-white" style="min-height: 500px;">
        <div class="p-6 border-b bg-gray-50">
          <h3 class="font-semibold text-lg mb-2">Multiple CAPTCHAs</h3>
          <p class="text-sm text-gray-600">
            If multiple research tasks encounter CAPTCHAs simultaneously,
            only the most recent notification displays (singleton behavior prevents stacking).
          </p>
        </div>
        <div class="p-6">
          <ul class="text-sm text-gray-600 space-y-2">
            <li>• First CAPTCHA: Shows notification</li>
            <li>• Second CAPTCHA: Updates notification content (replaces first)</li>
            <li>• Third CAPTCHA: Updates notification content (replaces second)</li>
          </ul>
          <CaptchaNotification />
        </div>
      </div>
    `,
  }),
};
