// Firefox VNC Environment Optimization
// This profile configuration reduces console errors in VNC environment

// Disable problematic search engines
user_pref("browser.search.suggest.enabled", false);
user_pref("browser.urlbar.suggest.searches", false);

// Disable system integration features that cause nsIAppStartup errors
user_pref("browser.startup.homepage_override.mstone", "ignore");
user_pref("toolkit.startup.max_resumed_crashes", -1);

// Optimize DevTools for VNC environment
user_pref("devtools.toolbox.host", "window");
user_pref("devtools.chrome.enabled", false);
user_pref("devtools.debugger.remote-enabled", false);

// Disable features requiring system access
user_pref("security.sandbox.content.level", 0);
user_pref("browser.tabs.remote.autostart", false);

// Optimize for headless/VNC environment
user_pref("general.useragent.override", "Mozilla/5.0 (X11; Linux x86_64; VNC) Firefox/Latest AutoBot");
user_pref("browser.sessionstore.enabled", false);