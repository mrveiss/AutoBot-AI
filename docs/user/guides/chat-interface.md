# Chat Interface Guide

The AI Assistant is AutoBot's primary workspace. This guide covers every
feature of the chat interface so you can get the most out of your
conversations.

## Accessing the Chat

Click **AI Assistant** in the navigation bar, or navigate to `/chat`. The
interface is divided into three areas:

- **Sidebar** (left) -- lists your conversation sessions.
- **Conversation area** (center) -- displays messages between you and AutoBot.
- **Input area** (bottom) -- where you type and send messages.

<!-- Screenshot: Full chat interface with sidebar, conversation, and input -->

## Conversations and Sessions

Every conversation is stored as a **session**. Sessions are listed in the
sidebar, with the most recent at the top.

| Action | How |
|--------|-----|
| Start a new session | Click **New Chat** at the top of the sidebar |
| Switch sessions | Click any session in the sidebar |
| Delete a session | Open the session, then click the trash icon in the header |
| Export a session | Click the download icon in the header |

Sessions are saved automatically as you type. You never need to manually save.

## Sending Messages

1. Click the input area at the bottom of the screen.
2. Type your message.
3. Press **Enter** to send.

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Enter` | Send message |
| `Shift + Enter` | New line (without sending) |

## Attaching Files

You can include files with your messages so AutoBot can analyze, summarize, or
reference them.

1. Click the **paperclip icon** in the input area.
2. Select one or more files from your computer.
3. Attached files appear above the input area with their name and size.
4. Type an instruction (for example, "Summarize this PDF") and press **Enter**.

To remove a single file, click the **X** next to its name. To remove all
files, click **Clear All**.

If an upload fails, a **Retry** button will appear next to the file. Click it
to try again.

<!-- Screenshot: Input area with attached files -->

## File Upload Progress

When files are uploading, a progress bar shows:

- The file name and current status.
- A percentage or byte counter.
- An estimated time remaining.

Wait for the upload to finish before sending your message.

## Voice Conversations

AutoBot supports voice input and output. Look for the **microphone icon** in
the chat interface:

1. Click the microphone icon to start speaking.
2. AutoBot will transcribe your speech and process it as a message.
3. If voice output is enabled, AutoBot will read its response aloud.

Voice settings can be configured in **Preferences** (`/preferences`) under the
**Voice** tab.

<!-- Screenshot: Voice conversation panel -->

## Citations and Sources

When AutoBot references information from your knowledge base, it includes
**citations** -- small indicators that show which document the information
came from. Click a citation to view the source document.

## Vision Analysis

If you attach an image, AutoBot can analyze its contents. After attaching an
image, ask a question such as:

```
What does this screenshot show?
```

AutoBot will describe the image, identify UI elements, or extract text
depending on your question.

<!-- Screenshot: Vision analysis of an attached image -->

## Sharing Conversations

To share a conversation with a colleague:

1. Open the conversation you want to share.
2. Look for the **Share** option in the session actions.
3. A shareable link or export will be generated.

## Connection Status

The chat header shows a real-time connection indicator:

| Indicator | Meaning |
|-----------|---------|
| Green check | Connected |
| Yellow spinner | Reconnecting |
| Red exclamation | Disconnected |

If you see a red indicator, check your network connection. AutoBot will
automatically attempt to reconnect.

## Tips

- Be specific in your questions for better answers. Instead of "Tell me about
  the project," try "Summarize the Q3 budget from the uploaded report."
- Use the knowledge base to give AutoBot context it would not otherwise have.
- You can ask AutoBot to perform actions across the platform, such as
  searching knowledge, running workflows, or explaining analytics.

## Related Guides

- [Quick Start: Your First Conversation](../quick-start-chat.md)
- [Working with Agents](working-with-agents.md)
- [Knowledge Management](knowledge-management.md)
