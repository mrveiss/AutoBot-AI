// Test WebSocket connection through Vite proxy
const WebSocket = require('ws');

const ws = new WebSocket('ws://localhost:5173/ws');

ws.on('open', function open() {
  console.log('✅ WebSocket connected via Vite proxy');
});

ws.on('message', function message(data) {
  console.log('📨 Received:', data.toString());
});

ws.on('error', function error(err) {
  console.log('❌ WebSocket error:', err.message);
});

ws.on('close', function close() {
  console.log('🔌 WebSocket closed');
});

// Keep alive for a few seconds
setTimeout(() => {
  ws.close();
}, 3000);
