(() => {
  const messagesEl = document.getElementById("messages");
  const form = document.getElementById("chat-form");
  const input = document.getElementById("input");
  const sendBtn = document.getElementById("send");
  const sessionEl = document.getElementById("session-id");
  const statusEl = document.getElementById("status");

  const storageKey = "nlm_session_id";
  let sessionId = localStorage.getItem(storageKey) || crypto.randomUUID().replace(/-/g, "");
  localStorage.setItem(storageKey, sessionId);
  sessionEl.textContent = sessionId;

  let es = null;
  let currentBotEl = null;
  let statusNoteEl = null;

  function setStatus(text) {
    statusEl.textContent = text;
  }

  function appendMessage(role, text) {
    const div = document.createElement("div");
    div.className = `msg ${role}`;
    div.innerHTML = `<span class="role">${role}</span>`;
    const body = document.createElement("div");
    body.className = "body";
    body.textContent = text;
    div.appendChild(body);
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return body;
  }

  function ensureBotBubble() {
    if (!currentBotEl) currentBotEl = appendMessage("assistant", "");
    return currentBotEl;
  }

  function showRetryNotice(message) {
    setStatus(message || "限流重试中…");
    const bot = ensureBotBubble();
    if (!statusNoteEl || !statusNoteEl.isConnected) {
      statusNoteEl = document.createElement("div");
      statusNoteEl.className = "retry-note";
      statusNoteEl.style.cssText =
        "margin-top:8px;padding:8px 10px;border-radius:8px;" +
        "background:rgba(61,155,253,0.12);border:1px solid rgba(61,155,253,0.28);" +
        "color:#9bb0c9;font-size:13px;";
      bot.parentElement.appendChild(statusNoteEl);
    }
    statusNoteEl.textContent = "⏳ " + (message || "模型限流，正在自动重试…");
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function clearRetryNotice() {
    if (statusNoteEl && statusNoteEl.isConnected) statusNoteEl.remove();
    statusNoteEl = null;
  }

  function ensureSSE() {
    if (es && es.readyState !== EventSource.CLOSED) return;
    es = new EventSource(`/api/chat/stream?session_id=${encodeURIComponent(sessionId)}`);
    es.onopen = () => setStatus("streaming connected");
    es.onerror = () => setStatus("sse reconnecting…");
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        const type = data.event_type;
        const payload = data.payload || {};
        if (type === "task.started") {
          clearRetryNotice();
          currentBotEl = appendMessage("assistant", "");
          setStatus("thinking…");
        } else if (type === "task.status") {
          showRetryNotice(payload.message || "处理中…");
        } else if (type === "task.delta") {
          clearRetryNotice();
          ensureBotBubble();
          currentBotEl.textContent += payload.delta || "";
          messagesEl.scrollTop = messagesEl.scrollHeight;
          setStatus("streaming…");
        } else if (type === "task.completed") {
          clearRetryNotice();
          ensureBotBubble();
          if (payload.content) currentBotEl.textContent = payload.content;
          currentBotEl = null;
          setStatus("ready");
          sendBtn.disabled = false;
        } else if (type === "task.failed") {
          clearRetryNotice();
          const err = payload.error || "unknown";
          appendMessage("assistant", err.includes("限流") || err.includes("429")
            ? `⚠️ ${err}`
            : `错误：${err}`);
          currentBotEl = null;
          setStatus("error");
          sendBtn.disabled = false;
        }
      } catch (_) {
        /* ignore */
      }
    };
  }

  ensureSSE();

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const content = input.value.trim();
    if (!content) return;
    ensureSSE();
    appendMessage("user", content);
    input.value = "";
    sendBtn.disabled = true;
    setStatus("sending…");
    try {
      const resp = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content, session_id: sessionId, stream: true }),
      });
      const json = await resp.json();
      if (!json.ok) {
        appendMessage("assistant", json.error?.message || "请求失败");
        sendBtn.disabled = false;
        setStatus("error");
        return;
      }
      if (json.data?.session_id && json.data.session_id !== sessionId) {
        sessionId = json.data.session_id;
        localStorage.setItem(storageKey, sessionId);
        sessionEl.textContent = sessionId;
        if (es) es.close();
        ensureSSE();
      }
      setStatus("queued");
    } catch (err) {
      appendMessage("assistant", String(err));
      sendBtn.disabled = false;
      setStatus("error");
    }
  });

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      form.requestSubmit();
    }
  });
})();
