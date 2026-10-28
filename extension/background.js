// Background service worker for Gesture Shorts WebSocket bridge

let ws = null;
let reconnectTimer = null;

function connect() {
  chrome.storage.local.get(['token', 'port'], (res) => {
    const port = res.port || 8765;
    const token = res.token || '';

    if (ws) {
      try {
        ws.close();
      } catch (e) {}
    }

    try {
      ws = new WebSocket(`ws://127.0.0.1:${port}`);
    } catch (e) {
      scheduleReconnect();
      return;
    }

    ws.onopen = () => {
      chrome.storage.local.set({ connected: true });
      if (token) {
        ws.send(JSON.stringify({ type: 'auth', token: token }));
      }
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'action') {
          // Forward action to active video tab
          chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
            if (tabs[0] && tabs[0].id) {
              chrome.tabs.sendMessage(tabs[0].id, { action: msg.action }, (response) => {
                if (response && ws && ws.readyState === WebSocket.OPEN) {
                  ws.send(
                    JSON.stringify({
                      type: 'status',
                      playing: response.playing,
                      muted: response.muted,
                    })
                  );
                }
              });
            }
          });
        }
      } catch (e) {}
    };

    ws.onclose = () => {
      chrome.storage.local.set({ connected: false });
      scheduleReconnect();
    };

    ws.onerror = () => {
      try {
        ws.close();
      } catch (e) {}
    };
  });
}

function scheduleReconnect() {
  if (reconnectTimer) clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(connect, 3000);
}

// Forward state reports from content scripts to Python bridge
chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === 'status' && ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(msg));
  }
});

chrome.runtime.onInstalled.addListener(connect);
chrome.runtime.onStartup.addListener(connect);
connect();
