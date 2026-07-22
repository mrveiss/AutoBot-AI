// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
const { chromium } = require('playwright');
const express = require('express');
const { SessionStore } = require('./session-store');
const app = express();

app.use(express.json({ limit: '50mb' }));

// Minimal structured logger (no external dependencies)
const logger = {
  _fmt: (level, args) => {
    const msg = args.map(a => (typeof a === 'object' ? JSON.stringify(a) : String(a))).join(' ');
    return `${new Date().toISOString()} [${level}] ${msg}\n`;
  },
  info:  (...args) => process.stdout.write(logger._fmt('INFO ', args)),
  warn:  (...args) => process.stdout.write(logger._fmt('WARN ', args)),
  error: (...args) => process.stderr.write(logger._fmt('ERROR', args)),
  debug: (...args) => process.stdout.write(logger._fmt('DEBUG', args)),
};

let browser = null;

// --- Per-session browser contexts (#11539) ---
//
// One Chromium process, N isolated BrowserContexts — one per conversation
// session_id. Each context has its own cookie jar / localStorage / auth
// state so logging in to a site in conversation A never leaks into
// conversation B. A request without a session_id maps to
// SessionStore.DEFAULT_SESSION_ID, preserving today's single-session
// behavior for a lone caller.
//
// Idle contexts are garbage-collected — see SESSION_IDLE_TIMEOUT_MS /
// SESSION_GC_INTERVAL_MS below (env-var-driven, mirrors the idle-GC pattern
// in services/docker_task_workspace.py).
const SESSION_IDLE_TIMEOUT_MS = parseInt(process.env.BROWSER_SESSION_IDLE_TIMEOUT_MS || String(30 * 60 * 1000), 10);
const SESSION_GC_INTERVAL_MS = parseInt(process.env.BROWSER_SESSION_GC_INTERVAL_MS || String(5 * 60 * 1000), 10);

const sessionStore = new SessionStore({ idleTimeoutMs: SESSION_IDLE_TIMEOUT_MS });

function sessionIdFromRequest(req) {
  const raw = (req.body && req.body.session_id) || (req.query && req.query.session_id);
  return SessionStore.resolveSessionId(raw);
}

async function getSessionEntry(sessionId) {
  const b = await initBrowser();
  const entry = await sessionStore.getOrCreate(sessionId, async () => {
    const context = await b.newContext();
    logger.info('Created new browser context for session %s', sessionId);
    return { context, navPage: null, mcpPage: null };
  });
  return entry;
}

async function closeSessionEntry(entry, sessionId) {
  if (entry.navPage && !entry.navPage.isClosed()) {
    try {
      await entry.navPage.close();
    } catch (e) {
      logger.warn('Session cleanup: navPage close failed for %s: %s', sessionId, e.message);
    }
  }
  if (entry.mcpPage && !entry.mcpPage.isClosed()) {
    try {
      await entry.mcpPage.close();
    } catch (e) {
      logger.warn('Session cleanup: mcpPage close failed for %s: %s', sessionId, e.message);
    }
  }
  await entry.context.close();
}

async function gcIdleSessions() {
  const evicted = await sessionStore.gcIdle(closeSessionEntry, (sessionId, err) => {
    logger.error('Session GC: failed to close context for %s: %s', sessionId, err.message);
  });
  if (evicted.length) {
    logger.info('Session GC: evicted %d idle browser context(s): %s', evicted.length, evicted.join(', '));
  }
  return evicted;
}

async function closeAllSessions() {
  for (const sessionId of sessionStore.ids()) {
    const entry = sessionStore.peek(sessionId);
    sessionStore.delete(sessionId);
    if (entry) {
      try {
        await closeSessionEntry(entry, sessionId);
      } catch (e) {
        logger.warn('Shutdown: failed to close session %s: %s', sessionId, e.message);
      }
    }
  }
}

const sessionGcTimer = setInterval(() => {
  gcIdleSessions().catch((e) => logger.error('Session GC error:', e.message));
}, SESSION_GC_INTERVAL_MS);
if (typeof sessionGcTimer.unref === 'function') sessionGcTimer.unref();

// --- End per-session browser contexts (#11539) ---

async function initBrowser() {
  try {
    if (!browser || !browser.isConnected()) {
      logger.info('Launching Chromium browser...');

      // Check if we should run in headless or headed mode
      const headlessMode = process.env.HEADLESS !== 'false';
      logger.info(`Browser mode: ${headlessMode ? 'headless' : 'headed (visible)'}`);

      const launchOptions = {
        headless: headlessMode,
        args: [
          '--no-sandbox',
          '--disable-dev-shm-usage',
          '--disable-web-security',
          '--disable-features=VizDisplayCompositor',
          '--disable-background-timer-throttling',
          '--disable-backgrounding-occluded-windows',
          '--disable-renderer-backgrounding',
          '--ignore-certificate-errors',
          '--remote-debugging-port=9222',
          '--remote-debugging-address=0.0.0.0',
        ]
      };

      // Add headed mode specific options
      if (!headlessMode) {
        launchOptions.args.push(
          '--start-maximized',
          '--disable-infobars',
          '--disable-extensions'
        );
        // Set slower execution for visibility
        launchOptions.slowMo = 500; // 500ms delay between actions
      }

      browser = await chromium.launch(launchOptions);
      logger.info('Browser launched successfully');
    }
    return browser;
  } catch (error) {
    logger.error('Failed to launch browser:', error.message || error);
    if (error.stack) {
      logger.error('Browser launch stack:', error.stack);
    }
    throw error;
  }
}

app.get('/health', (req, res) => {
  res.json({
    status: 'healthy',
    timestamp: new Date().toISOString(),
    browser_connected: browser ? browser.isConnected() : false
  });
});

// --- Persistent navigation page helpers (#1130, per-session since #11539) ---

async function ensureNavPage(sessionId) {
  const entry = await getSessionEntry(sessionId);
  if (!entry.navPage || entry.navPage.isClosed()) {
    entry.navPage = await entry.context.newPage();
    await entry.navPage.setExtraHTTPHeaders({
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    });
    logger.info('Created new navPage for session %s', sessionId);
  }
  sessionStore.touch(sessionId);
  return entry.navPage;
}

async function captureNavScreenshot(page) {
  const buf = await page.screenshot({ type: 'png' });
  return buf.toString('base64');
}

// Anti-detection: random offset +/-2-5px, biased slightly upper-left (#1416)
function applyJitter(x, y) {
  const jitter = () => {
    const sign = Math.random() < 0.6 ? -1 : 1;
    return sign * (2 + Math.random() * 3);
  };
  return { x: x + jitter(), y: y + jitter() };
}

// Standard response for all interaction endpoints (#1416)
async function navInteractionResponse(page) {
  const screenshot = await captureNavScreenshot(page);
  const vp = page.viewportSize() || { width: 1280, height: 720 };
  return {
    success: true,
    screenshot,
    url: page.url(),
    title: await page.title(),
    viewportWidth: vp.width,
    viewportHeight: vp.height,
  };
}

app.get('/status', async (req, res) => {
  try {
    const sessionId = sessionIdFromRequest(req);
    const connected = browser && browser.isConnected();
    const entry = sessionStore.peek(sessionId);
    const navPage = entry ? entry.navPage : null;
    const pageOpen = navPage && !navPage.isClosed();
    const currentUrl = pageOpen ? navPage.url() : null;
    res.json({
      status: connected ? 'connected' : 'disconnected',
      browser_connected: connected,
      page_open: pageOpen,
      current_url: currentUrl,
      session_id: sessionId,
    });
  } catch (e) {
    res.status(500).json({ status: 'error', browser_connected: false, page_open: false, error: e.message });
  }
});

app.post('/navigate', async (req, res) => {
  const { url } = req.body;
  const sessionId = sessionIdFromRequest(req);
  if (!url) return res.status(400).json({ success: false, error: 'url required' });
  try {
    const page = await ensureNavPage(sessionId);
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
    res.json(await navInteractionResponse(page));
  } catch (e) {
    logger.error('navigate error:', e.message);
    res.status(500).json({ success: false, error: e.message });
  }
});

app.post('/screenshot', async (req, res) => {
  const sessionId = sessionIdFromRequest(req);
  try {
    const page = await ensureNavPage(sessionId);
    res.json(await navInteractionResponse(page));
  } catch (e) {
    logger.error('screenshot error:', e.message);
    res.status(500).json({ success: false, error: e.message });
  }
});

app.post('/back', async (req, res) => {
  const sessionId = sessionIdFromRequest(req);
  try {
    const page = await ensureNavPage(sessionId);
    await page.goBack({ waitUntil: 'domcontentloaded', timeout: 15000 });
    res.json(await navInteractionResponse(page));
  } catch (e) {
    logger.error('back error:', e.message);
    res.status(500).json({ success: false, error: e.message });
  }
});

app.post('/forward', async (req, res) => {
  const sessionId = sessionIdFromRequest(req);
  try {
    const page = await ensureNavPage(sessionId);
    await page.goForward({ waitUntil: 'domcontentloaded', timeout: 15000 });
    res.json(await navInteractionResponse(page));
  } catch (e) {
    logger.error('forward error:', e.message);
    res.status(500).json({ success: false, error: e.message });
  }
});

app.post('/reload', async (req, res) => {
  const sessionId = sessionIdFromRequest(req);
  try {
    const page = await ensureNavPage(sessionId);
    await page.reload({ waitUntil: 'domcontentloaded', timeout: 15000 });
    res.json(await navInteractionResponse(page));
  } catch (e) {
    logger.error('reload error:', e.message);
    res.status(500).json({ success: false, error: e.message });
  }
});

// --- End persistent navigation page endpoints ---

// --- Interactive browser control endpoints (#1416) ---

app.post('/click', async (req, res) => {
  const { x, y } = req.body;
  const sessionId = sessionIdFromRequest(req);
  if (typeof x !== 'number' || typeof y !== 'number') {
    return res.status(400).json({ success: false, error: 'x and y coordinates required' });
  }
  try {
    const page = await ensureNavPage(sessionId);
    const jittered = applyJitter(x, y);
    logger.info('Click at:', { original: { x, y }, jittered });
    await page.mouse.click(jittered.x, jittered.y);
    await page.waitForTimeout(300);
    res.json(await navInteractionResponse(page));
  } catch (e) {
    logger.error('click error:', e.message);
    res.status(500).json({ success: false, error: e.message });
  }
});

app.post('/scroll', async (req, res) => {
  const { deltaX = 0, deltaY = 0 } = req.body;
  const sessionId = sessionIdFromRequest(req);
  if (typeof deltaX !== 'number' || typeof deltaY !== 'number') {
    return res.status(400).json({ success: false, error: 'deltaX and deltaY must be numbers' });
  }
  try {
    const page = await ensureNavPage(sessionId);
    logger.info('Scroll:', { deltaX, deltaY });
    await page.mouse.wheel(deltaX, deltaY);
    await page.waitForTimeout(200);
    res.json(await navInteractionResponse(page));
  } catch (e) {
    logger.error('scroll error:', e.message);
    res.status(500).json({ success: false, error: e.message });
  }
});

app.post('/type', async (req, res) => {
  const { text } = req.body;
  const sessionId = sessionIdFromRequest(req);
  if (!text || typeof text !== 'string') {
    return res.status(400).json({ success: false, error: 'text string required' });
  }
  try {
    const page = await ensureNavPage(sessionId);
    logger.info('Type:', text.substring(0, 50));
    await page.keyboard.type(text, { delay: 30 + Math.random() * 40 });
    await page.waitForTimeout(200);
    res.json(await navInteractionResponse(page));
  } catch (e) {
    logger.error('type error:', e.message);
    res.status(500).json({ success: false, error: e.message });
  }
});

app.post('/hover', async (req, res) => {
  const { x, y } = req.body;
  const sessionId = sessionIdFromRequest(req);
  if (typeof x !== 'number' || typeof y !== 'number') {
    return res.status(400).json({ success: false, error: 'x and y coordinates required' });
  }
  try {
    const page = await ensureNavPage(sessionId);
    const jittered = applyJitter(x, y);
    logger.info('Hover at:', { original: { x, y }, jittered });
    await page.mouse.move(jittered.x, jittered.y);
    await page.waitForTimeout(200);
    res.json(await navInteractionResponse(page));
  } catch (e) {
    logger.error('hover error:', e.message);
    res.status(500).json({ success: false, error: e.message });
  }
});

// --- End interactive browser control endpoints (#1416) ---


app.post('/search', async (req, res) => {
  logger.info('Received search request:', req.body);
  const { query, search_engine = 'duckduckgo' } = req.body;

  if (!query) {
    return res.status(400).json({
      success: false,
      error: 'Query parameter is required'
    });
  }

  // Declared outside the try so the finally block can always close it,
  // even if browser.newPage()/goto() throws before the inner try runs.
  let page = null;
  try {
    const browser = await initBrowser();
    page = await browser.newPage();

    await page.setExtraHTTPHeaders({
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    });

    const searchUrls = {
      duckduckgo: 'https://duckduckgo.com/?q=' + encodeURIComponent(query)
    };

    const searchUrl = searchUrls[search_engine] || searchUrls.duckduckgo;
    logger.info('Navigating to:', searchUrl);

    await page.goto(searchUrl, {
      waitUntil: 'domcontentloaded',
      timeout: 15000
    });

    await page.waitForTimeout(3000);

    let results = [];

    try {
      const resultSelectors = [
        '[data-testid="result"]',
        '.result'
      ];

      let elements = [];
      for (const selector of resultSelectors) {
        try {
          await page.waitForSelector(selector, { timeout: 5000 });
          elements = await page.$$(selector);
          if (elements.length > 0) {
            logger.info('Found results with selector:', selector);
            break;
          }
        } catch (e) {
          continue;
        }
      }

      for (const element of elements.slice(0, 5)) {
        try {
          const titleElement = await element.$('h2 a, h3 a, .result__title a');
          if (titleElement) {
            const title = await titleElement.textContent();
            const url = await titleElement.getAttribute('href');
            const snippet = '';

            if (url && title && title.trim()) {
              results.push({
                title: title.trim(),
                url: url.startsWith('http') ? url : 'https://duckduckgo.com' + url,
                snippet: snippet.trim(),
                source: 'DuckDuckGo'
              });
            }
          }
        } catch (e) {
          logger.error('Error extracting result:', e.message);
        }
      }
    } catch (e) {
      logger.error('Error with search:', e.message);
    }

    res.json({
      success: true,
      query: query,
      search_engine: search_engine,
      results: results.slice(0, 5)
    });

  } catch (error) {
    logger.error('Search error:', error);
    res.status(500).json({
      success: false,
      error: error.message
    });
  } finally {
    if (page && !page.isClosed()) {
      try {
        await page.close();
      } catch (e) {
        logger.warn('Search: page close failed: %s', e.message);
      }
    }
  }
});

// Add comprehensive message testing endpoint
app.post('/send-test-message', async (req, res) => {
  logger.info('Received message test request:', req.body);
  try {
    const { frontend_url = 'http://localhost:5173', message = 'what network scanning tools do we have available?' } = req.body;

    const browser = await initBrowser();
    const page = await browser.newPage();

    logger.info('Navigating to frontend:', frontend_url);
    await page.goto(frontend_url, { waitUntil: 'networkidle', timeout: 30000 });

    // Wait for Vue.js app to fully load
    await page.waitForTimeout(3000);

    const results = {
      success: true,
      frontend_url,
      message_sent: message,
      timestamp: new Date().toISOString(),
      steps: []
    };

    // Step 1: Navigate to AI Assistant
    logger.info('Clicking AI ASSISTANT navigation...');
    try {
      const aiAssistantButton = page.getByText('AI ASSISTANT');
      await aiAssistantButton.click();
      await page.waitForTimeout(2000);

      results.steps.push({
        step: 'Navigate to AI Assistant',
        status: 'SUCCESS',
        details: 'AI Assistant section opened'
      });
    } catch (error) {
      results.steps.push({
        step: 'Navigate to AI Assistant',
        status: 'FAILED',
        details: error.message
      });
    }

    // Step 2: Find message input
    logger.info('Looking for message input field...');
    try {
      const messageInput = page.locator('textarea[placeholder*="message"], textarea[placeholder*="Type"], textarea').first();

      if (await messageInput.count() > 0) {
        logger.info('Message input found');

        // Step 3: Type the test message
        logger.info(`Typing message: "${message}"`);
        await messageInput.fill(message);
        await page.waitForTimeout(1000);

        results.steps.push({
          step: 'Type message',
          status: 'SUCCESS',
          details: `Message typed: "${message}"`
        });

        // Step 4: Send the message
        logger.info('Looking for send button...');
        const sendSelectors = [
          'text=Send',
          'button[type="submit"]',
          '.send-button',
          '.btn:has-text("Send")',
          'button:has-text("Send")'
        ];

        let messageSent = false;
        for (const selector of sendSelectors) {
          try {
            const sendBtn = page.locator(selector);
            if (await sendBtn.count() > 0) {
              logger.info(`Clicking send button: ${selector}`);
              await sendBtn.click();
              messageSent = true;
              break;
            }
          } catch (e) {
            continue;
          }
        }

        if (messageSent) {
          await page.waitForTimeout(3000); // Wait for response

          results.steps.push({
            step: 'Send message',
            status: 'SUCCESS',
            details: 'Message sent successfully'
          });

          // Step 5: Check for workflow response
          logger.info('Waiting for workflow response...');
          await page.waitForTimeout(5000);

          // Look for workflow indicators
          const workflowIndicators = [
            '.workflow-progress',
            '.workflow-step',
            '[data-testid="workflow"]',
            'text=workflow',
            'text=step',
            'text=approval'
          ];

          let workflowDetected = false;
          const workflowDetails = [];

          for (const indicator of workflowIndicators) {
            try {
              const elements = await page.locator(indicator).count();
              if (elements > 0) {
                workflowDetected = true;
                workflowDetails.push(`Found ${elements} elements matching "${indicator}"`);
              }
            } catch (e) {
              continue;
            }
          }

          results.steps.push({
            step: 'Check workflow response',
            status: workflowDetected ? 'SUCCESS' : 'PENDING',
            details: workflowDetected ? workflowDetails.join(', ') : 'Workflow may still be processing'
          });

        } else {
          results.steps.push({
            step: 'Send message',
            status: 'FAILED',
            details: 'Send button not found'
          });
        }

      } else {
        results.steps.push({
          step: 'Find message input',
          status: 'FAILED',
          details: 'Message input field not found'
        });
      }

    } catch (error) {
      results.steps.push({
        step: 'Find message input',
        status: 'FAILED',
        details: error.message
      });
    }

    // Take screenshot for debugging
    try {
      const screenshot = await page.screenshot({ fullPage: true, type: 'png' });
      results.screenshot_size = screenshot.length;
      results.has_screenshot = true;
      logger.info(`Screenshot captured: ${screenshot.length} bytes`);
    } catch (error) {
      results.screenshot_error = error.message;
    }

    await page.close();

    logger.info('Message test completed');
    res.json(results);

  } catch (error) {
    logger.error('Message test error:', error);
    res.status(500).json({
      success: false,
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Add frontend testing endpoint
app.post('/test-frontend', async (req, res) => {
  logger.info('Received frontend test request:', req.body);
  try {
    const { frontend_url = 'http://localhost:5173' } = req.body;

    const browser = await initBrowser();
    const page = await browser.newPage();

    logger.info('Navigating to frontend:', frontend_url);
    await page.goto(frontend_url, { waitUntil: 'networkidle', timeout: 30000 });

    // Wait for Vue.js app to fully load
    await page.waitForTimeout(5000);

    // Wait for Vue app to be mounted
    try {
      await page.waitForSelector('#app', { timeout: 10000 });
      logger.info('Vue app container found');
    } catch (e) {
      logger.warn('Vue app container not found');
    }

    const results = {
      success: true,
      frontend_url,
      timestamp: new Date().toISOString(),
      tests: []
    };

    // Test 1: Check if page loaded
    const title = await page.title();
    results.tests.push({
      name: 'Page Load',
      status: title ? 'PASS' : 'FAIL',
      details: `Title: ${title}`
    });

    // Test 2: Check for main navigation
    const navItems = ['DASHBOARD', 'AI ASSISTANT', 'VOICE INTERFACE', 'KNOWLEDGE BASE', 'TERMINAL', 'FILE MANAGER', 'SYSTEM MONITOR', 'SETTINGS'];
    for (const navItem of navItems) {
      try {
        const element = await page.getByText(navItem).first();
        const isVisible = await element.isVisible();
        results.tests.push({
          name: `Navigation: ${navItem}`,
          status: isVisible ? 'PASS' : 'FAIL',
          details: isVisible ? 'Navigation item found' : 'Navigation item not visible'
        });

        if (isVisible) {
          await element.click();
          await page.waitForTimeout(1000);
          logger.info(`Clicked ${navItem}`);
        }
      } catch (error) {
        results.tests.push({
          name: `Navigation: ${navItem}`,
          status: 'FAIL',
          details: error.message
        });
      }
    }

    // Test 3: Check AI Assistant functionality
    try {
      logger.info('Navigating to AI Assistant...');
      const aiAssistantButton = page.getByText('AI ASSISTANT');
      await aiAssistantButton.click();
      await page.waitForTimeout(5000);

      logger.info('Current URL after AI Assistant click:', page.url());

      // Wait for ChatInterface component to load
      logger.info('Waiting for chat interface to load...');
      await page.waitForTimeout(3000);

      // Debug: Check what's actually in the DOM
      const chatSection = page.locator('[key="chat"], .chat-interface, [data-testid="chat"]');
      const chatSectionCount = await chatSection.count();
      logger.info(`Chat sections found: ${chatSectionCount}`);

      if (chatSectionCount > 0) {
        const chatSectionHTML = await chatSection.first().innerHTML();
        logger.info('Chat section HTML preview:', chatSectionHTML.substring(0, 200) + '...');
      }

      // Look for chat interface elements with multiple selectors
      const messageSelectors = [
        'textarea[placeholder*="message"]',
        'input[placeholder*="message"]',
        'textarea[placeholder*="Type"]',
        'input[placeholder*="Type"]',
        '.chat-input textarea',
        '.message-input textarea',
        'textarea',
        'input[type="text"]'
      ];

      let hasMessageInput = false;
      let messageInputDetails = 'No message input found';

      for (const selector of messageSelectors) {
        try {
          const inputs = await page.locator(selector).count();
          if (inputs > 0) {
            hasMessageInput = true;
            messageInputDetails = `Message input found with selector: ${selector}`;
            break;
          }
        } catch (e) {
          continue;
        }
      }

      results.tests.push({
        name: 'Chat Interface',
        status: hasMessageInput ? 'PASS' : 'FAIL',
        details: messageInputDetails
      });

      // Test Reload System button with multiple selectors
      const reloadSelectors = [
        'text=Reload System',
        'text=Reload',
        '[data-testid="reload-button"]',
        'button:has-text("Reload")',
        '.reload-button',
        '.btn:has-text("Reload")'
      ];

      let hasReloadButton = false;
      let reloadButtonDetails = 'No reload button found';

      for (const selector of reloadSelectors) {
        try {
          const buttons = await page.locator(selector).count();
          if (buttons > 0) {
            hasReloadButton = true;
            reloadButtonDetails = `Reload button found with selector: ${selector}`;
            break;
          }
        } catch (e) {
          continue;
        }
      }

      results.tests.push({
        name: 'Reload System Button',
        status: hasReloadButton ? 'PASS' : 'FAIL',
        details: reloadButtonDetails
      });

      // Test sending a message if input is found
      if (hasMessageInput) {
        try {
          const textarea = page.locator('textarea').first();
          await textarea.fill('Test message from Playwright');
          await page.waitForTimeout(1000);

          // Look for send button
          const sendSelectors = ['text=Send', 'button[type="submit"]', '.send-button', '.btn:has-text("Send")'];
          let messageSent = false;

          for (const selector of sendSelectors) {
            try {
              const sendBtn = page.locator(selector);
              if (await sendBtn.count() > 0) {
                await sendBtn.click();
                messageSent = true;
                break;
              }
            } catch (e) {
              continue;
            }
          }

          results.tests.push({
            name: 'Message Sending',
            status: messageSent ? 'PASS' : 'FAIL',
            details: messageSent ? 'Test message sent successfully' : 'Send button not found'
          });
        } catch (error) {
          results.tests.push({
            name: 'Message Sending',
            status: 'FAIL',
            details: error.message
          });
        }
      }

    } catch (error) {
      results.tests.push({
        name: 'AI Assistant Navigation',
        status: 'FAIL',
        details: error.message
      });
    }

    // Capture page HTML for debugging
    try {
      // Wait a bit more to ensure all elements are loaded
      await page.waitForTimeout(2000);

      // Extract key elements for debugging
      const allButtons = await page.locator('button').all();
      const buttonTexts = [];
      for (const button of allButtons) {
        try {
          const text = await button.textContent();
          if (text && text.trim()) {
            buttonTexts.push(text.trim());
          }
        } catch (e) {
          continue;
        }
      }

      // Look for all form elements
      const textareas = await page.locator('textarea').count();
      const inputs = await page.locator('input').count();
      const forms = await page.locator('form').count();

      // Get current page structure
      const navItems = await page.locator('nav a, .nav a, [role="navigation"] a, .sidebar a').all();
      const navTexts = [];
      for (const nav of navItems) {
        try {
          const text = await nav.textContent();
          if (text && text.trim()) {
            navTexts.push(text.trim());
          }
        } catch (e) {
          continue;
        }
      }

      results.debug_info = {
        page_title: await page.title(),
        url: page.url(),
        textareas: textareas,
        inputs: inputs,
        forms: forms,
        button_texts: buttonTexts.slice(0, 15),
        navigation_texts: navTexts.slice(0, 10),
        body_classes: await page.locator('body').getAttribute('class') || '',
        app_element: await page.locator('#app').count(),
        vue_components: await page.locator('[data-v-]').count()
      };
    } catch (error) {
      results.debug_error = error.message;
    }

    // Take screenshot for debugging
    try {
      const screenshot = await page.screenshot({ fullPage: true, type: 'png' });
      // Save screenshot to results but truncated for response size
      results.screenshot_size = screenshot.length;
      results.has_screenshot = true;
    } catch (error) {
      results.screenshot_error = error.message;
    }

    await page.close();

    const passCount = results.tests.filter(t => t.status === 'PASS').length;
    const totalTests = results.tests.length;

    results.summary = {
      total_tests: totalTests,
      passed: passCount,
      failed: totalTests - passCount,
      success_rate: `${Math.round((passCount / totalTests) * 100)}%`
    };

    logger.info('Frontend testing completed:', results.summary);
    res.json(results);

  } catch (error) {
    logger.error('Frontend test error:', error);
    res.status(500).json({
      success: false,
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// =============================================================================
// MCP automation dispatcher – browser_mcp.py sends POST /automation with
// { action, params, session_id } payload to control the MCP browser page
// dedicated to that conversation/session (#11539 — was one shared page for
// every conversation).
// =============================================================================

async function ensureMcpPage(sessionId) {
  const entry = await getSessionEntry(sessionId);
  if (!entry.mcpPage || entry.mcpPage.isClosed()) {
    entry.mcpPage = await entry.context.newPage();
    logger.info('MCP automation page created for session %s', sessionId);
  }
  sessionStore.touch(sessionId);
  return entry.mcpPage;
}

app.post('/automation', async (req, res) => {
  const { action, params = {} } = req.body;
  const sessionId = sessionIdFromRequest(req);
  if (!action) {
    return res.status(400).json({ success: false, error: 'action is required' });
  }
  logger.info('Automation action:', action, 'session:', sessionId);
  try {
    const page = await ensureMcpPage(sessionId);
    let result = {};
    switch (action) {
      case 'navigate': {
        const timeout = params.timeout || 30000;
        const waitUntil = params.wait_until || 'domcontentloaded';
        await page.goto(params.url, { waitUntil, timeout });
        result = { title: await page.title(), url: page.url() };
        break;
      }
      case 'click': {
        await page.click(params.selector, { timeout: params.timeout || 10000 });
        result = { success: true };
        break;
      }
      case 'fill': {
        await page.fill(params.selector, params.value, { timeout: params.timeout || 10000 });
        result = { success: true };
        break;
      }
      case 'screenshot': {
        const opts = { type: 'png', fullPage: params.full_page || false };
        if (params.selector) {
          const el = await page.$(params.selector);
          const buf = el ? await el.screenshot(opts) : await page.screenshot(opts);
          result = { image: buf.toString('base64') };
        } else {
          result = { image: (await page.screenshot(opts)).toString('base64') };
        }
        break;
      }
      case 'evaluate': {
        const evalResult = await page.evaluate(params.script);
        result = { result: evalResult };
        break;
      }
      case 'wait_for_selector': {
        await page.waitForSelector(params.selector, {
          timeout: params.timeout || 10000,
          state: params.state || 'visible',
        });
        result = { success: true };
        break;
      }
      case 'get_text': {
        result = { text: await page.textContent(params.selector) };
        break;
      }
      case 'get_attribute': {
        result = { value: await page.getAttribute(params.selector, params.attribute) };
        break;
      }
      case 'select': {
        await page.selectOption(params.selector, params.value);
        result = { success: true };
        break;
      }
      case 'hover': {
        await page.hover(params.selector);
        result = { success: true };
        break;
      }
      default:
        return res.status(400).json({ success: false, error: `Unknown action: ${action}` });
    }
    res.json({ success: true, action, result, session_id: sessionId, timestamp: new Date().toISOString() });
  } catch (error) {
    logger.error('Automation error:', action, error);
    res.status(500).json({ success: false, error: error.message, action });
  }
});

const port = parseInt(process.env.PLAYWRIGHT_PORT || '9001', 10);
app.listen(port, '0.0.0.0', async () => {
  logger.info('Playwright service listening on port ' + port);

  try {
    await initBrowser();
    logger.info('Browser pre-initialized and ready');
  } catch (error) {
    logger.error('Failed to pre-initialize browser:', error);
  }
});

// Graceful shutdown
process.on('SIGTERM', async () => {
  logger.info('Shutting down gracefully...');
  clearInterval(sessionGcTimer);
  await closeAllSessions();
  if (browser) {
    await browser.close();
    logger.info('Browser closed');
  }
  process.exit(0);
});

process.on('SIGINT', async () => {
  logger.info('Received SIGINT, shutting down...');
  clearInterval(sessionGcTimer);
  await closeAllSessions();
  if (browser) {
    await browser.close();
    logger.info('Browser closed');
  }
  process.exit(0);
});
