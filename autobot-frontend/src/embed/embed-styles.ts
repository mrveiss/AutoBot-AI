/**
 * All widget styles are inlined into the Shadow DOM so they never
 * conflict with (or inherit from) the host page stylesheet.
 */
export const WIDGET_STYLES = `
/* ── Reset ──────────────────────────────────────────────────────────────── */
*, *::before, *::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

/* ── Custom properties (can be overridden per-instance) ────────────────── */
:host {
  --ab-primary: #6366f1;
  --ab-primary-dark: #4f46e5;
  --ab-bg: #ffffff;
  --ab-surface: #f9fafb;
  --ab-border: #e5e7eb;
  --ab-text: #111827;
  --ab-text-muted: #6b7280;
  --ab-user-bg: var(--ab-primary);
  --ab-user-text: #ffffff;
  --ab-bot-bg: #f3f4f6;
  --ab-bot-text: #111827;
  --ab-radius: 16px;
  --ab-panel-w: 360px;
  --ab-panel-h: 520px;
  --ab-z: 2147483647;
  --ab-shadow: 0 20px 60px rgba(0,0,0,0.18), 0 4px 12px rgba(0,0,0,0.10);
  --ab-fab-size: 56px;
  --ab-gap: 16px;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}

/* ── Dark theme ─────────────────────────────────────────────────────────── */
:host([data-theme="dark"]) {
  --ab-bg: #1e1e2e;
  --ab-surface: #181825;
  --ab-border: #313244;
  --ab-text: #cdd6f4;
  --ab-text-muted: #6c7086;
  --ab-bot-bg: #313244;
  --ab-bot-text: #cdd6f4;
  --ab-shadow: 0 20px 60px rgba(0,0,0,0.45), 0 4px 12px rgba(0,0,0,0.30);
}

/* ── Widget container ───────────────────────────────────────────────────── */
.ab-widget {
  position: fixed;
  bottom: var(--ab-gap);
  z-index: var(--ab-z);
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 12px;
}

.ab-pos-right { right: var(--ab-gap); align-items: flex-end; }
.ab-pos-left  { left: var(--ab-gap);  align-items: flex-start; }

/* ── FAB toggle ─────────────────────────────────────────────────────────── */
.ab-fab {
  width: var(--ab-fab-size);
  height: var(--ab-fab-size);
  border-radius: 50%;
  background: var(--ab-primary);
  color: #fff;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 14px rgba(0,0,0,0.25);
  transition: transform 0.2s ease, background 0.15s ease;
  flex-shrink: 0;
  order: 2;
}
.ab-fab:hover  { background: var(--ab-primary-dark); transform: scale(1.06); }
.ab-fab:active { transform: scale(0.96); }
.ab-fab svg    { width: 24px; height: 24px; }

/* ── Chat panel ─────────────────────────────────────────────────────────── */
.ab-panel {
  width: var(--ab-panel-w);
  height: var(--ab-panel-h);
  max-width: calc(100vw - 2 * var(--ab-gap));
  max-height: calc(100vh - var(--ab-fab-size) - 3 * var(--ab-gap));
  background: var(--ab-bg);
  border-radius: var(--ab-radius);
  box-shadow: var(--ab-shadow);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  order: 1;
  animation: ab-slide-up 0.22s cubic-bezier(0.34, 1.56, 0.64, 1);
}

@keyframes ab-slide-up {
  from { opacity: 0; transform: translateY(20px) scale(0.96); }
  to   { opacity: 1; transform: translateY(0)     scale(1); }
}

/* ── Header ─────────────────────────────────────────────────────────────── */
.ab-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  background: var(--ab-primary);
  color: #fff;
  flex-shrink: 0;
}
.ab-title  { font-weight: 600; font-size: 15px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ab-close  {
  background: transparent;
  border: none;
  color: rgba(255,255,255,0.85);
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
  padding: 2px 6px;
  border-radius: 6px;
  transition: background 0.15s;
}
.ab-close:hover { background: rgba(255,255,255,0.15); }

/* ── Messages ───────────────────────────────────────────────────────────── */
.ab-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  scroll-behavior: smooth;
}

.ab-messages::-webkit-scrollbar       { width: 4px; }
.ab-messages::-webkit-scrollbar-track { background: transparent; }
.ab-messages::-webkit-scrollbar-thumb { background: var(--ab-border); border-radius: 2px; }

.ab-empty {
  color: var(--ab-text-muted);
  font-size: 14px;
  text-align: center;
  margin: auto;
  padding: 24px 0;
}

.ab-msg {
  display: flex;
  max-width: 85%;
}
.ab-msg-user      { align-self: flex-end; }
.ab-msg-assistant { align-self: flex-start; }

.ab-bubble {
  padding: 9px 13px;
  border-radius: 14px;
  font-size: 14px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}
.ab-msg-user      .ab-bubble { background: var(--ab-user-bg); color: var(--ab-user-text); border-bottom-right-radius: 4px; }
.ab-msg-assistant .ab-bubble { background: var(--ab-bot-bg);  color: var(--ab-bot-text);  border-bottom-left-radius: 4px; }

/* Typing dots */
.ab-dots       { display: inline-flex; gap: 4px; align-items: center; height: 18px; }
.ab-dots span  { width: 7px; height: 7px; border-radius: 50%; background: var(--ab-text-muted); animation: ab-dot 1.2s infinite; }
.ab-dots span:nth-child(2) { animation-delay: 0.2s; }
.ab-dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes ab-dot {
  0%, 80%, 100% { transform: scale(0.7); opacity: 0.5; }
  40%           { transform: scale(1);   opacity: 1; }
}

/* ── Input row ──────────────────────────────────────────────────────────── */
.ab-input-row {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 10px 12px 12px;
  border-top: 1px solid var(--ab-border);
  background: var(--ab-bg);
  flex-shrink: 0;
}

.ab-input {
  flex: 1;
  resize: none;
  border: 1px solid var(--ab-border);
  border-radius: 10px;
  padding: 9px 12px;
  font-size: 14px;
  font-family: inherit;
  color: var(--ab-text);
  background: var(--ab-surface);
  outline: none;
  max-height: 120px;
  overflow-y: auto;
  transition: border-color 0.15s;
  line-height: 1.4;
}
.ab-input:focus     { border-color: var(--ab-primary); }
.ab-input::placeholder { color: var(--ab-text-muted); }

.ab-send {
  width: 38px;
  height: 38px;
  border-radius: 50%;
  background: var(--ab-primary);
  color: #fff;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background 0.15s, opacity 0.15s, transform 0.1s;
}
.ab-send:hover:not([disabled]) { background: var(--ab-primary-dark); transform: scale(1.05); }
.ab-send:disabled               { opacity: 0.45; cursor: not-allowed; }
.ab-send svg                    { width: 18px; height: 18px; }

/* ── Responsive (mobile ≤ 480 px) ───────────────────────────────────────── */
@media (max-width: 480px) {
  .ab-panel {
    width: calc(100vw - 2 * var(--ab-gap));
    height: calc(100vh - var(--ab-fab-size) - 40px);
    max-height: none;
    border-radius: 16px 16px 0 0;
    position: fixed;
    bottom: calc(var(--ab-fab-size) + 16px);
  }
  .ab-pos-right.ab-widget { right: 0; padding-right: var(--ab-gap); }
  .ab-pos-left.ab-widget  { left: 0;  padding-left:  var(--ab-gap); }
}
`
