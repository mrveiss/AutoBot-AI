const express = require('express');
const { chromium } = require('playwright');

const app = express();
app.use(express.json());

// Simple CORS middleware instead of cors package
app.use((req, res, next) => {
    res.header('Access-Control-Allow-Origin', '*');
    res.header('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS');
    res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization, Content-Length, X-Requested-With');
    
    if (req.method === 'OPTIONS') {
        res.sendStatus(200);
    } else {
        next();
    }
});

let browser = null;
let page = null;

// Initialize browser
async function initBrowser() {
    try {
        if (!browser) {
            browser = await chromium.launch({
                headless: false,
                args: [
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--remote-debugging-port=9222',
                    '--disable-extensions'
                ]
            });
            console.log('Browser launched successfully');
        }
        
        if (!page) {
            page = await browser.newPage();
            await page.setViewportSize({ width: 1200, height: 600 });
            console.log('Page created successfully');
        }
        
        return true;
    } catch (error) {
        console.error('Error initializing browser:', error.message);
        return false;
    }
}

// Health check endpoint
app.get('/health', async (req, res) => {
    const browserReady = await initBrowser();
    res.json({
        status: browserReady ? 'ok' : 'error',
        browser: browser !== null,
        page: page !== null,
        timestamp: new Date().toISOString()
    });
});

// Navigate to URL
app.post('/navigate', async (req, res) => {
    try {
        const ready = await initBrowser();
        if (!ready || !page) {
            return res.status(500).json({ error: 'Browser not initialized' });
        }
        
        const { url } = req.body;
        if (!url) {
            return res.status(400).json({ error: 'URL is required' });
        }
        
        console.log(`Navigating to: ${url}`);
        await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 15000 });
        
        const currentUrl = page.url();
        const title = await page.title();
        
        res.json({
            success: true,
            url: currentUrl,
            title: title
        });
    } catch (error) {
        console.error('Navigation error:', error.message);
        res.status(500).json({ 
            error: error.message,
            success: false 
        });
    }
});

// Go back
app.post('/back', async (req, res) => {
    try {
        const ready = await initBrowser();
        if (!ready || !page) {
            return res.status(500).json({ error: 'Browser not initialized' });
        }
        
        await page.goBack({ waitUntil: 'domcontentloaded', timeout: 10000 });
        
        const currentUrl = page.url();
        const title = await page.title();
        
        res.json({
            success: true,
            url: currentUrl,
            title: title
        });
    } catch (error) {
        console.error('Back navigation error:', error.message);
        res.status(500).json({ 
            error: error.message,
            success: false 
        });
    }
});

// Go forward
app.post('/forward', async (req, res) => {
    try {
        const ready = await initBrowser();
        if (!ready || !page) {
            return res.status(500).json({ error: 'Browser not initialized' });
        }
        
        await page.goForward({ waitUntil: 'domcontentloaded', timeout: 10000 });
        
        const currentUrl = page.url();
        const title = await page.title();
        
        res.json({
            success: true,
            url: currentUrl,
            title: title
        });
    } catch (error) {
        console.error('Forward navigation error:', error.message);
        res.status(500).json({ 
            error: error.message,
            success: false 
        });
    }
});

// Reload page
app.post('/reload', async (req, res) => {
    try {
        const ready = await initBrowser();
        if (!ready || !page) {
            return res.status(500).json({ error: 'Browser not initialized' });
        }
        
        await page.reload({ waitUntil: 'domcontentloaded', timeout: 10000 });
        
        const currentUrl = page.url();
        const title = await page.title();
        
        res.json({
            success: true,
            url: currentUrl,
            title: title
        });
    } catch (error) {
        console.error('Reload error:', error.message);
        res.status(500).json({ 
            error: error.message,
            success: false 
        });
    }
});

// Get page info
app.get('/page-info', async (req, res) => {
    try {
        const ready = await initBrowser();
        if (!ready || !page) {
            return res.status(500).json({ error: 'Browser not initialized' });
        }
        
        const currentUrl = page.url();
        const title = await page.title();
        
        res.json({
            url: currentUrl,
            title: title,
            canGoBack: true,
            canGoForward: true
        });
    } catch (error) {
        console.error('Page info error:', error.message);
        res.status(500).json({ 
            error: error.message 
        });
    }
});

const PORT = 3000;

app.listen(PORT, '0.0.0.0', () => {
    console.log(`Playwright server running on port ${PORT}`);
    console.log('Server ready! Browser will initialize on first request.');
});

// Cleanup on exit
process.on('SIGINT', async () => {
    console.log('Shutting down...');
    if (browser) {
        await browser.close();
    }
    process.exit(0);
});

process.on('SIGTERM', async () => {
    console.log('Shutting down...');
    if (browser) {
        await browser.close();
    }
    process.exit(0);
});