// AutoBot Console Error Filter
// Suppresses known harmless VNC environment errors

(function() {
    'use strict';
    
    // Store original console methods
    const originalError = console.error;
    const originalWarn = console.warn;
    
    // Known harmless error patterns to suppress
    const harmlessPatterns = [
        /NS_ERROR_NOT_IMPLEMENTED.*nsIAppStartup/,
        /Key event not available on some keyboard layouts/,
        /unexpected engine url type.*visualSearch/,
        /NotFoundError.*BrowserToolboxDevToolsProcess/
    ];
    
    // Filter function
    function shouldSuppress(message) {
        return harmlessPatterns.some(pattern => pattern.test(message));
    }
    
    // Override console.error
    console.error = function(...args) {
        const message = args.join(' ');
        if (!shouldSuppress(message)) {
            originalError.apply(console, args);
        }
    };
    
    // Override console.warn
    console.warn = function(...args) {
        const message = args.join(' ');
        if (!shouldSuppress(message)) {
            originalWarn.apply(console, args);
        }
    };
    
    console.log('AutoBot: Console error filtering enabled for VNC environment');
})();