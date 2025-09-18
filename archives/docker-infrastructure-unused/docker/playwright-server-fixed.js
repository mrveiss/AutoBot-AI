const express = require('express');
const { chromium } = require('playwright');
const cors = require('cors');

const app = express();
app.use(cors());
app.use(express.json());

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
                    '--disable-extensions',
                    '--disable-plugins',
                    '--disable-background-timer-throttling',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-renderer-backgrounding'
                ]
            });
            console.log('Browser launched successfully');
        }
        
        if (!page) {
            page = await browser.newPage();
            await page.setViewportSize({ width: 1200, height: 600 });
            console.log('Page created successfully');
        }
    } catch (error) {
        console.error('Error initializing browser:', error);
    }
}

// Health check endpoint
app.get('/health', (req, res) => {
    res.json({
        status: 'ok',
        browser: browser !== null,
        page: page !== null,
        timestamp: new Date().toISOString()
    });
});

// Navigate to URL
app.post('/navigate', async (req, res) => {
    try {
        await initBrowser();
        if (!page) {
            return res.status(500).json({ error: 'Browser not initialized' });
        }
        
        const { url } = req.body;
        if (!url) {
            return res.status(400).json({ error: 'URL is required' });
        }
        
        console.log(`Navigating to: ${url}`);
        await page.goto(url, { waitUntil: 'networkidle' });
        
        const currentUrl = page.url();
        const title = await page.title();
        
        res.json({
            success: true,
            url: currentUrl,
            title: title
        });
    } catch (error) {
        console.error('Navigation error:', error);
        res.status(500).json({ 
            error: error.message,
            success: false 
        });
    }
});

// Go back
app.post('/back', async (req, res) => {
    try {
        await initBrowser();
        if (!page) {
            return res.status(500).json({ error: 'Browser not initialized' });
        }
        
        await page.goBack({ waitUntil: 'networkidle' });
        
        const currentUrl = page.url();
        const title = await page.title();
        
        res.json({
            success: true,
            url: currentUrl,
            title: title
        });
    } catch (error) {
        console.error('Back navigation error:', error);
        res.status(500).json({ 
            error: error.message,
            success: false 
        });
    }
});

// Go forward
app.post('/forward', async (req, res) => {
    try {
        await initBrowser();
        if (!page) {
            return res.status(500).json({ error: 'Browser not initialized' });
        }
        
        await page.goForward({ waitUntil: 'networkidle' });
        
        const currentUrl = page.url();
        const title = await page.title();
        
        res.json({
            success: true,
            url: currentUrl,
            title: title
        });
    } catch (error) {
        console.error('Forward navigation error:', error);
        res.status(500).json({ 
            error: error.message,
            success: false 
        });
    }
});

// Reload page
app.post('/reload', async (req, res) => {
    try {
        await initBrowser();
        if (!page) {
            return res.status(500).json({ error: 'Browser not initialized' });
        }
        
        await page.reload({ waitUntil: 'networkidle' });
        
        const currentUrl = page.url();
        const title = await page.title();
        
        res.json({
            success: true,
            url: currentUrl,
            title: title
        });
    } catch (error) {
        console.error('Reload error:', error);
        res.status(500).json({ 
            error: error.message,
            success: false 
        });
    }
});

// Get page info
app.get('/page-info', async (req, res) => {
    try {
        await initBrowser();
        if (!page) {
            return res.status(500).json({ error: 'Browser not initialized' });
        }
        
        const currentUrl = page.url();
        const title = await page.title();
        
        res.json({
            url: currentUrl,
            title: title,
            canGoBack: true, // Simplified for now
            canGoForward: true // Simplified for now
        });
    } catch (error) {
        console.error('Page info error:', error);
        res.status(500).json({ 
            error: error.message 
        });
    }
});

const PORT = process.env.PORT || 3001;

app.listen(PORT, '0.0.0.0', async () => {
    console.log(`Playwright server running on port ${PORT}`);
    console.log('Initializing browser...');
    await initBrowser();
    console.log('Server ready!');
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