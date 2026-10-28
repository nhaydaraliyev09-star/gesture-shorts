// Content script: directly controls HTML5 <video> elements on Shorts, TikTok, and Reels

function getActiveVideo() {
  const videos = Array.from(document.querySelectorAll('video'));
  if (videos.length === 0) return null;
  // Pick the visible video currently in the viewport
  return videos.find((v) => {
    const rect = v.getBoundingClientRect();
    return (
      rect.width > 0 &&
      rect.height > 0 &&
      rect.top < window.innerHeight &&
      rect.bottom > 0
    );
  }) || videos[0];
}

function sendState() {
  const video = getActiveVideo();
  if (!video) return;
  chrome.runtime.sendMessage({
    type: 'status',
    playing: !video.paused,
    muted: video.muted,
  });
}

// Hook video events to continuously report true playback state
setInterval(() => {
  const video = getActiveVideo();
  if (video && !video._gsHooked) {
    video._gsHooked = true;
    ['play', 'pause', 'volumechange'].forEach((evt) => {
      video.addEventListener(evt, sendState);
    });
  }
}, 1000);

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  const video = getActiveVideo();
  if (!video) {
    sendResponse({ success: false, error: 'No video element found' });
    return;
  }

  if (msg.action === 'toggle_play') {
    if (video.paused) {
      video.play().catch(() => {});
    } else {
      video.pause();
    }
  } else if (msg.action === 'mute') {
    video.muted = !video.muted;
  } else if (msg.action === 'next') {
    const nextBtn = document.querySelector(
      '#navigation-button-down button, [aria-label*="Next"], button[aria-label="Next video"]'
    );
    if (nextBtn) {
      nextBtn.click();
    } else {
      window.scrollBy({ top: window.innerHeight * 0.85, behavior: 'smooth' });
    }
  } else if (msg.action === 'previous') {
    const prevBtn = document.querySelector(
      '#navigation-button-up button, [aria-label*="Previous"], button[aria-label="Previous video"]'
    );
    if (prevBtn) {
      prevBtn.click();
    } else {
      window.scrollBy({ top: -window.innerHeight * 0.85, behavior: 'smooth' });
    }
  }

  sendState();
  sendResponse({ success: true, playing: !video.paused, muted: video.muted });
});
