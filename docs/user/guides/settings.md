# Settings and Preferences Guide

AutoBot lets you personalize your experience through the **Preferences** page.
This guide walks through every available setting.

## Accessing Preferences

Click **Preferences** in the navigation bar, or navigate to `/preferences`.
The Preferences page has three tabs:

- **Appearance**
- **Language**
- **Voice**

<!-- Screenshot: Preferences page with three tabs -->

## Appearance

The Appearance tab controls how AutoBot looks.

### Theme

Choose between visual themes to suit your environment:

- **Dark** -- dark background with light text. Easier on the eyes in low-light
  settings.
- **Light** -- light background with dark text. Better in bright environments.
- **System** -- automatically matches your operating system's theme setting.

<!-- Screenshot: Theme selection options -->

### Font Size

Adjust the text size throughout the interface. Options typically range from
small to large. Choose whichever is most comfortable to read.

### Color Accents

Some themes allow you to customize accent colors (the highlight color used for
buttons, links, and active elements). Pick a color that you find visually
appealing.

### Layout Density

Control how much spacing appears between elements:

- **Compact** -- less whitespace, more content visible at once.
- **Comfortable** -- balanced spacing (default).
- **Spacious** -- more whitespace, easier to scan.

## Language

The Language tab controls the interface language.

1. Open the **Language** tab.
2. Select your preferred language from the dropdown list.
3. The interface will update immediately. All labels, buttons, and system
   messages will appear in the selected language.

Note: AI responses are generated in the language you write in, regardless of
the interface language. If you write a message in Spanish, AutoBot will
typically respond in Spanish.

<!-- Screenshot: Language selection dropdown -->

## Voice

The Voice tab controls speech-related features.

### Voice Input

Enable or disable the microphone for voice input in the chat:

1. Toggle **Voice Input** on.
2. Grant your browser permission to access the microphone when prompted.
3. A microphone icon will appear in the chat input area.

### Voice Output

Enable or disable AutoBot reading responses aloud:

1. Toggle **Voice Output** on.
2. Choose a voice from the available options (varies by browser and operating
   system).
3. Adjust the speaking rate if available.

### Voice Language

Select the language for speech recognition. This should match the language you
intend to speak. It does not need to match the interface language.

<!-- Screenshot: Voice settings panel -->

## Secrets Manager

The **Secrets Manager** (`/secrets`) stores API keys and credentials that
AutoBot uses when connecting to external services on your behalf. This is
separate from the Preferences page but is related to your personal
configuration.

1. Navigate to `/secrets` from the navigation bar.
2. Click **Add Secret** to store a new credential.
3. Provide a name, the secret value, and an optional description.
4. Secrets are encrypted and stored securely. Only you and authorized agents
   can access them.

<!-- Screenshot: Secrets Manager with an example entry -->

## Plugins

The **Plugin Manager** (`/plugins`) lets you extend AutoBot's capabilities:

1. Navigate to `/plugins` from the navigation bar.
2. Browse available plugins.
3. Click **Install** to add a plugin to your instance.
4. Configure the plugin's settings as needed.

Plugins can add new agent types, connectors, UI features, or integrations
with external tools.

<!-- Screenshot: Plugin Manager browse page -->

## Tips

- If the interface feels too dark or too bright, switch the theme to match
  your lighting.
- Increasing the font size can reduce eye strain during long sessions.
- Enable voice input for a hands-free experience when you are away from the
  keyboard.
- Review your secrets periodically and remove any that are no longer needed.

## Related Guides

- [Chat Interface](chat-interface.md) -- voice settings affect the chat
  experience
- [Knowledge Management](knowledge-management.md) -- connectors may use
  secrets you configure here
- [Getting Started](../getting-started.md) -- return to the setup overview
