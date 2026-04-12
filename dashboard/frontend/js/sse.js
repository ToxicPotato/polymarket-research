const statusDot  = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");

let retryDelay = 1000;

export function startSSE() {
  const es = new EventSource("/api/stream");

  es.onopen = () => {
    retryDelay = 1000;
    statusDot.className  = "status-dot live";
    statusText.textContent = "live";
  };

  es.onmessage = (evt) => {
    try {
      const payload = JSON.parse(evt.data);
      window.dispatchEvent(new CustomEvent(payload.type));
    } catch {
      // heartbeat comment lines are ignored (EventSource skips comment lines)
    }
  };

  es.onerror = () => {
    statusDot.className   = "status-dot error";
    statusText.textContent = `reconnecting in ${Math.round(retryDelay / 1000)}s…`;
    es.close();
    setTimeout(() => {
      retryDelay = Math.min(retryDelay * 2, 30_000);
      startSSE();
    }, retryDelay);
  };
}
