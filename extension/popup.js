document.addEventListener('DOMContentLoaded', () => {
  const statusEl = document.getElementById('status');
  const portEl = document.getElementById('port');
  const tokenEl = document.getElementById('token');
  const saveBtn = document.getElementById('save');

  chrome.storage.local.get(['port', 'token', 'connected'], (res) => {
    if (res.port) portEl.value = res.port;
    if (res.token) tokenEl.value = res.token;
    updateStatus(res.connected);
  });

  function updateStatus(connected) {
    if (connected) {
      statusEl.textContent = '● Connected to Gesture Shorts';
      statusEl.className = 'status connected';
    } else {
      statusEl.textContent = '● Disconnected';
      statusEl.className = 'status disconnected';
    }
  }

  saveBtn.addEventListener('click', () => {
    const port = parseInt(portEl.value, 10) || 8765;
    const token = tokenEl.value.trim();
    chrome.storage.local.set({ port, token }, () => {
      saveBtn.textContent = 'Saved! Reconnecting...';
      setTimeout(() => {
        saveBtn.textContent = 'Save & Connect';
      }, 1500);
      chrome.runtime.sendMessage({ type: 'reconnect' });
    });
  });

  chrome.storage.onChanged.addListener((changes) => {
    if (changes.connected) {
      updateStatus(changes.connected.newValue);
    }
  });
});
