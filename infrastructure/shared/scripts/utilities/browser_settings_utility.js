from src.constants import NetworkConstants, ServiceURLs


// AutoBot Settings Fix Script
// Run this in your browser console (F12 -> Console)

console.log('🔧 AutoBot Settings Fix Script');

// Function to reset settings to defaults
function resetSettings() {
    const defaultSettings = {
        message_display: {
            show_thoughts: true,
            show_json: false,
            show_utility: false,
            show_planning: true,
            show_debug: false
        },
        chat: {
            auto_scroll: true,
            max_messages: 100,
            default_welcome_message: "Hello! How can I assist you today?"
        },
        backend: {
            use_phi2: false,
            api_endpoint: ServiceURLs.BACKEND_LOCAL,
            ollama_endpoint: ServiceURLs.OLLAMA_LOCAL,
            ollama_model: 'deepseek-r1:14b',
            streaming: false
        },
        ui: {
            theme: 'light',
            font_size: 'medium'
        }
    };

    localStorage.setItem('chat_settings', JSON.stringify(defaultSettings));
    console.log('✅ Settings reset to defaults');
    return defaultSettings;
}

// Function to check current settings
function checkSettings() {
    const settings = localStorage.getItem('chat_settings');
    if (settings) {
        try {
            const parsed = JSON.parse(settings);
            console.log('📋 Current settings:', parsed);
            return parsed;
        } catch (e) {
            console.error('❌ Invalid settings in localStorage:', e);
            return null;
        }
    } else {
        console.log('⚠️ No settings found in localStorage');
        return null;
    }
}

// Function to fix common issues
function fixCommonIssues() {
    const settings = checkSettings();

    if (!settings) {
        console.log('🔄 No valid settings found, resetting...');
        resetSettings();
    } else {
        // Ensure backend endpoint is correct
        if (settings.backend && settings.backend.api_endpoint !== ServiceURLs.BACKEND_LOCAL) {
            console.log('🔧 Fixing backend endpoint...');
            settings.backend.api_endpoint = ServiceURLs.BACKEND_LOCAL;
            localStorage.setItem('chat_settings', JSON.stringify(settings));
        }

        console.log('✅ Settings validated and fixed');
    }

    // Reload the page to apply changes
    if (confirm('Settings have been fixed. Reload the page to apply changes?')) {
        location.reload();
    }
}

// Run diagnostics
console.log('🔍 Running diagnostics...');
checkSettings();

// Provide options
console.log('\n📋 Available commands:');
console.log('  resetSettings()     - Reset all settings to defaults');
console.log('  checkSettings()     - View current settings');
console.log('  fixCommonIssues()  - Fix common configuration issues');
console.log('\nRun any command to proceed.');

// Auto-fix if settings are missing
if (!localStorage.getItem('chat_settings')) {
    console.log('\n⚠️ No settings found, auto-fixing...');
    fixCommonIssues();
}
