from src.constants import NetworkConstants, ServiceURLs

// Frontend API Connection Fix Script
// Run this in your browser console (F12 -> Console) to fix API timeouts

console.log('🔧 AutoBot Frontend API Fix Script');
console.log('==================================');

// 1. Clear all storage
function clearAllStorage() {
    console.log('🧹 Clearing browser storage...');

    // Clear localStorage
    localStorage.clear();

    // Clear sessionStorage
    sessionStorage.clear();

    // Clear IndexedDB (if any)
    if ('indexedDB' in window) {
        indexedDB.databases().then(databases => {
            databases.forEach(db => {
                indexedDB.deleteDatabase(db.name);
            });
        });
    }

    console.log('✅ Storage cleared');
}

// 2. Reset default settings
function resetDefaultSettings() {
    console.log('⚙️ Setting default configuration...');

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
    console.log('✅ Default settings restored');

    return defaultSettings;
}

// 3. Test API connectivity
async function testApiConnectivity() {
    console.log('🌐 Testing API connectivity...');

    const endpoints = [
        '/api/system/health',
        '/api/settings/',
        '/api/workflow/workflows',
        '/api/knowledge_base/stats'
    ];

    const baseUrl = ServiceURLs.BACKEND_LOCAL;
    const results = {};

    for (const endpoint of endpoints) {
        try {
            console.log(`  Testing ${endpoint}...`);

            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 5000);

            const response = await fetch(`${baseUrl}${endpoint}`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                },
                signal: controller.signal
            });

            clearTimeout(timeoutId);

            if (response.ok) {
                const data = await response.json();
                results[endpoint] = { success: true, data: data };
                console.log(`    ✅ ${endpoint} - OK`);
            } else {
                results[endpoint] = { success: false, error: `HTTP ${response.status}` };
                console.log(`    ❌ ${endpoint} - ${response.status}`);
            }
        } catch (error) {
            results[endpoint] = { success: false, error: error.message };
            console.log(`    ❌ ${endpoint} - ${error.message}`);
        }
    }

    return results;
}

// 4. Fix API client settings
function fixApiClientSettings() {
    console.log('🔧 Fixing API client configuration...');

    // Reset any cached API instances if they exist
    if (window.apiClient) {
        window.apiClient.setTimeout(10000); // 10 second timeout
        window.apiClient.setBaseUrl(ServiceURLs.BACKEND_LOCAL);
        console.log('  ✅ Updated existing apiClient');
    }

    // Set environment overrides
    if (window.localStorage) {
        localStorage.setItem('autobot_api_base_url', ServiceURLs.BACKEND_LOCAL);
        localStorage.setItem('autobot_api_timeout', '10000');
        console.log('  ✅ Set API configuration overrides');
    }
}

// 5. Force reload Vue components (if possible)
function triggerComponentReload() {
    console.log('🔄 Triggering component reload...');

    // Dispatch custom events to trigger reloads
    const events = [
        'settings-reload',
        'api-reconnect',
        'workflow-refresh',
        'knowledge-refresh'
    ];

    events.forEach(eventName => {
        const event = new CustomEvent(eventName, { detail: { source: 'fix-script' } });
        window.dispatchEvent(event);
        document.dispatchEvent(event);
    });

    console.log('  ✅ Reload events dispatched');
}

// 6. Network diagnostic
async function networkDiagnostic() {
    console.log('🔍 Running network diagnostic...');

    try {
        // Test basic connectivity
        const start = performance.now();
        const response = await fetch('ServiceURLs.BACKEND_LOCAL/api/system/health', {
            method: 'GET',
            cache: 'no-cache'
        });
        const end = performance.now();

        const latency = Math.round(end - start);
        console.log(`  📊 Latency: ${latency}ms`);

        if (response.ok) {
            const health = await response.json();
            console.log(`  ✅ Backend status: ${health.status}`);
            console.log(`  🔗 LLM status: ${health.llm_status ? 'Connected' : 'Disconnected'}`);
            console.log(`  📊 Redis status: ${health.redis_status}`);
        }

        return { success: true, latency: latency };
    } catch (error) {
        console.log(`  ❌ Network error: ${error.message}`);
        return { success: false, error: error.message };
    }
}

// Main fix function
async function fixFrontendApiIssues() {
    console.log('\n🚀 Starting comprehensive frontend API fix...\n');

    // Step 1: Clear storage
    clearAllStorage();

    // Step 2: Reset settings
    resetDefaultSettings();

    // Step 3: Fix API client
    fixApiClientSettings();

    // Step 4: Network diagnostic
    const networkResult = await networkDiagnostic();

    // Step 5: Test endpoints
    const apiResults = await testApiConnectivity();

    // Step 6: Trigger reload
    triggerComponentReload();

    // Summary
    console.log('\n📊 FIX SUMMARY');
    console.log('================');

    const successfulEndpoints = Object.values(apiResults).filter(r => r.success).length;
    const totalEndpoints = Object.keys(apiResults).length;

    console.log(`✅ Storage: Cleared`);
    console.log(`✅ Settings: Reset to defaults`);
    console.log(`✅ API Client: Reconfigured`);
    console.log(`${networkResult.success ? '✅' : '❌'} Network: ${networkResult.success ? 'OK' : 'Failed'}`);
    console.log(`📊 Endpoints: ${successfulEndpoints}/${totalEndpoints} working`);

    if (successfulEndpoints === totalEndpoints && networkResult.success) {
        console.log('\n🎉 All issues fixed! Reload the page to see changes.');

        if (confirm('All API issues have been resolved. Reload the page now?')) {
            window.location.reload();
        }
    } else {
        console.log('\n⚠️ Some issues remain. Check the backend server status.');
        console.log('💡 Try: ./run_agent.sh to restart the backend');
    }

    return {
        storage_cleared: true,
        settings_reset: true,
        api_configured: true,
        network_ok: networkResult.success,
        endpoints_working: successfulEndpoints,
        total_endpoints: totalEndpoints
    };
}

// Utility functions for manual use
window.autobotFix = {
    clearStorage: clearAllStorage,
    resetSettings: resetDefaultSettings,
    testApi: testApiConnectivity,
    fixAll: fixFrontendApiIssues,
    diagnostic: networkDiagnostic
};

console.log('\n📋 Available commands:');
console.log('  autobotFix.fixAll()      - Run complete fix');
console.log('  autobotFix.clearStorage() - Clear browser storage');
console.log('  autobotFix.resetSettings() - Reset to default settings');
console.log('  autobotFix.testApi()     - Test API endpoints');
console.log('  autobotFix.diagnostic()  - Run network diagnostic');

console.log('\n🎯 Quick fix: Run autobotFix.fixAll() to resolve all issues');

// Auto-run if issues detected
if (!localStorage.getItem('chat_settings')) {
    console.log('\n⚠️ No settings found, auto-running fix...');
    fixFrontendApiIssues();
}
