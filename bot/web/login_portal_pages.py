"""Responsive HTML for the secure OTP / 2FA login portal."""

from __future__ import annotations

from html import escape
from typing import Literal

ResultKind = Literal["otp_ok", "otp_fail", "password_ok", "password_fail", "denied"]


def _base_styles() -> str:
    return """
:root {
  color-scheme: light dark;
  --bg: #f4f6f9;
  --surface: #ffffff;
  --text: #0f1419;
  --muted: #5c6670;
  --border: #e1e6eb;
  --accent: #2481cc;
  --accent-hover: #1a6eb3;
  --accent-soft: rgba(36, 129, 204, 0.12);
  --success: #0d9f6e;
  --error: #d63c3c;
  --shadow: 0 12px 40px rgba(15, 20, 25, 0.08);
  --radius: 16px;
  --tap: 48px;
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue",
    Arial, "Noto Sans", sans-serif, "Apple Color Emoji", "Segoe UI Emoji";
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0e1114;
    --surface: #17212b;
    --text: #f5f5f5;
    --muted: #94a3b0;
    --border: #2b3945;
    --accent: #3d9be9;
    --accent-hover: #5aadf2;
    --accent-soft: rgba(61, 155, 233, 0.15);
    --shadow: 0 16px 48px rgba(0, 0, 0, 0.45);
  }
}
*, *::before, *::after { box-sizing: border-box; }
html {
  -webkit-text-size-adjust: 100%;
  text-size-adjust: 100%;
}
body {
  margin: 0;
  min-height: 100dvh;
  min-height: 100vh;
  background: var(--bg);
  color: var(--text);
  line-height: 1.5;
  padding: max(16px, env(safe-area-inset-top))
           max(16px, env(safe-area-inset-right))
           max(24px, env(safe-area-inset-bottom))
           max(16px, env(safe-area-inset-left));
  display: flex;
  align-items: center;
  justify-content: center;
}
.wrap {
  width: min(440px, 100%);
}
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: clamp(20px, 5vw, 32px);
}
.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.logo {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  background: linear-gradient(145deg, var(--accent), #6bc2ff);
  display: grid;
  place-items: center;
  color: #fff;
  font-size: 22px;
  flex-shrink: 0;
}
h1 {
  font-size: clamp(1.25rem, 4vw, 1.5rem);
  font-weight: 700;
  margin: 0 0 4px;
  letter-spacing: -0.02em;
}
.lead {
  margin: 0 0 24px;
  color: var(--muted);
  font-size: 0.9375rem;
}
.section {
  margin-bottom: 28px;
}
.section:last-child { margin-bottom: 0; }
.section-title {
  font-size: 0.8125rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
  margin: 0 0 12px;
}
.otp-row {
  display: flex;
  gap: clamp(6px, 2vw, 10px);
  justify-content: center;
  margin-bottom: 16px;
}
.otp-cell {
  width: clamp(44px, 11vw, 52px);
  height: clamp(52px, 13vw, 56px);
  border: 2px solid var(--border);
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: clamp(1.25rem, 4vw, 1.5rem);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  background: var(--bg);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.otp-cell.filled { border-color: var(--accent); background: var(--accent-soft); }
.otp-cell.active {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}
.otp-input-wrap {
  position: relative;
  height: 0;
  overflow: hidden;
}
.otp-input-wrap input {
  position: absolute;
  opacity: 0;
  width: 1px;
  height: 1px;
  pointer-events: none;
}
.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  border: 0;
}
.field {
  margin-bottom: 14px;
}
.field label {
  display: block;
  font-size: 0.875rem;
  font-weight: 500;
  margin-bottom: 8px;
}
.input-shell {
  position: relative;
  display: flex;
  align-items: center;
}
input[type="password"],
input[type="text"].text-field {
  width: 100%;
  min-height: var(--tap);
  padding: 12px 48px 12px 14px;
  font-size: 16px;
  border: 2px solid var(--border);
  border-radius: 12px;
  background: var(--bg);
  color: var(--text);
}
input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}
.toggle-pw {
  position: absolute;
  right: 4px;
  top: 50%;
  transform: translateY(-50%);
  min-width: 44px;
  min-height: 44px;
  border: none;
  background: transparent;
  color: var(--accent);
  font-size: 0.8125rem;
  font-weight: 600;
  cursor: pointer;
  border-radius: 8px;
}
.btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-height: var(--tap);
  padding: 12px 20px;
  font-size: 1rem;
  font-weight: 600;
  border: none;
  border-radius: 12px;
  cursor: pointer;
  background: var(--accent);
  color: #fff;
  transition: background 0.15s, transform 0.1s;
}
.btn:hover { background: var(--accent-hover); }
.btn:active { transform: scale(0.98); }
.btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
  transform: none;
}
.btn-secondary {
  background: transparent;
  color: var(--accent);
  border: 2px solid var(--border);
}
.hint {
  font-size: 0.8125rem;
  color: var(--muted);
  margin: 12px 0 0;
}
.divider {
  height: 1px;
  background: var(--border);
  margin: 24px 0;
}
.note {
  font-size: 0.8125rem;
  color: var(--muted);
  padding: 12px 14px;
  background: var(--accent-soft);
  border-radius: 10px;
  margin-top: 20px;
}
.note strong { color: var(--text); }
.status-card {
  text-align: center;
  padding: 8px 0;
}
.status-icon {
  font-size: 3rem;
  line-height: 1;
  margin-bottom: 12px;
}
.status-card h1 { margin-bottom: 8px; }
.status-card .lead { margin-bottom: 0; }
.status-error .status-icon { color: var(--error); }
.status-success .status-icon { color: var(--success); }
"""


def _page_shell(title: str, body: str, extra_script: str = "") -> str:
    t = escape(title)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <meta name="theme-color" content="#2481cc" />
  <meta name="robots" content="noindex, nofollow" />
  <meta name="format-detection" content="telephone=no" />
  <title>{t}</title>
  <style>{_base_styles()}</style>
</head>
<body>
  <div class="wrap">
    {body}
  </div>
  {extra_script}
</body>
</html>"""


def render_login_page(user_id: int, token: str, *, focus_2fa: bool = False) -> str:
    safe_token = escape(token)
    otp_action = f"/login/{user_id}/otp"
    pw_action = f"/login/{user_id}/password"
    two_fa_hint = (
        '<p class="hint" id="twoFaHint">Telegram asked for your cloud password — enter it below.</p>'
        if focus_2fa
        else '<p class="hint">Only complete this section if Telegram prompted for two-factor authentication.</p>'
    )

    script = f"""
<script>
(function () {{
  const cells = document.querySelectorAll(".otp-cell");
  const proxy = document.getElementById("otpProxy");
  const hidden = document.getElementById("otpHidden");
  const submitOtp = document.getElementById("submitOtp");
  const maxLen = 8;

  function sync(code) {{
    const digits = code.replace(/\\D/g, "").slice(0, maxLen);
    hidden.value = digits;
    cells.forEach((el, i) => {{
      const ch = digits[i] || "";
      el.textContent = ch;
      el.classList.toggle("filled", !!ch);
      el.classList.toggle("active", i === digits.length && digits.length < maxLen);
    }});
    if (digits.length === 0) cells[0]?.classList.add("active");
    submitOtp.disabled = digits.length < 5;
  }}

  proxy.addEventListener("input", () => sync(proxy.value));
  proxy.addEventListener("focus", () => {{
    cells.forEach((el) => el.classList.remove("active"));
    const len = hidden.value.length;
    if (len < maxLen) cells[len]?.classList.add("active");
  }});
  cells.forEach((el) => {{
    el.addEventListener("click", () => proxy.focus());
  }});

  document.getElementById("otpForm").addEventListener("submit", () => {{
    hidden.value = hidden.value.replace(/\\D/g, "");
  }});

  const pw = document.getElementById("passwordField");
  const toggle = document.getElementById("togglePw");
  if (toggle && pw) {{
    toggle.addEventListener("click", () => {{
      const show = pw.type === "password";
      pw.type = show ? "text" : "password";
      toggle.textContent = show ? "Hide" : "Show";
      toggle.setAttribute("aria-pressed", show ? "true" : "false");
    }});
  }}

  {"document.getElementById('passwordField')?.focus();" if focus_2fa else "proxy.focus();"}
  sync(proxy.value || "");
}})();
</script>"""

    body = f"""
<div class="card">
  <div class="brand">
    <div class="logo" aria-hidden="true">🔒</div>
    <div>
      <h1>Secure login</h1>
      <p class="lead">Submit your Telegram verification code and 2FA password here — never in the bot chat.</p>
    </div>
  </div>

  <section class="section" aria-labelledby="otp-heading">
    <h2 class="section-title" id="otp-heading">Step 1 · Verification code</h2>
    <form id="otpForm" method="post" action="{otp_action}" autocomplete="on">
      <input type="hidden" name="token" value="{safe_token}" />
      <div class="otp-row" role="group" aria-label="One-time code digits">
        <div class="otp-cell" data-idx="0"></div>
        <div class="otp-cell" data-idx="1"></div>
        <div class="otp-cell" data-idx="2"></div>
        <div class="otp-cell" data-idx="3"></div>
        <div class="otp-cell" data-idx="4"></div>
      </div>
      <div class="otp-input-wrap">
        <label class="visually-hidden" for="otpProxy">Login code from Telegram</label>
        <input
          id="otpProxy"
          type="text"
          inputmode="numeric"
          pattern="[0-9]*"
          autocomplete="one-time-code"
          enterkeyhint="done"
          maxlength="8"
          aria-describedby="otpHelp"
        />
      </div>
      <input type="hidden" name="otp" id="otpHidden" value="" required />
      <p class="hint" id="otpHelp">Open Telegram → check the login notification or SMS. Paste works on mobile and desktop.</p>
      <button type="submit" class="btn" id="submitOtp" disabled>Submit code</button>
    </form>
  </section>

  <div class="divider" role="separator"></div>

  <section class="section" aria-labelledby="twofa-heading">
    <h2 class="section-title" id="twofa-heading">Step 2 · Two-factor password</h2>
    {two_fa_hint}
    <form method="post" action="{pw_action}" autocomplete="on">
      <input type="hidden" name="token" value="{safe_token}" />
      <div class="field">
        <label for="passwordField">Cloud password</label>
        <div class="input-shell">
          <input
            id="passwordField"
            class="text-field"
            type="password"
            name="password"
            autocomplete="current-password"
            enterkeyhint="go"
            minlength="1"
            required
          />
          <button type="button" class="toggle-pw" id="togglePw" aria-pressed="false">Show</button>
        </div>
      </div>
      <button type="submit" class="btn btn-secondary">Submit 2FA password</button>
    </form>
  </section>

  <p class="note"><strong>Privacy:</strong> Codes are sent only to this bot session over HTTPS. Close this tab after Telegram confirms login.</p>
</div>"""

    return _page_shell("Secure login", body, script)


def render_result_page(kind: ResultKind) -> str:
    messages = {
        "otp_ok": (
            "Code received",
            "Your verification code was submitted. Return to Telegram and wait for confirmation.",
            "success",
            "✓",
        ),
        "otp_fail": (
            "Unable to submit code",
            "This login link may have expired. Start again from the bot with /account.",
            "error",
            "✕",
        ),
        "password_ok": (
            "2FA received",
            "Your password was submitted. Return to Telegram to finish signing in.",
            "success",
            "✓",
        ),
        "password_fail": (
            "Unable to submit 2FA",
            "No active login session was found. Request a new link from the bot.",
            "error",
            "✕",
        ),
        "denied": (
            "Invalid or expired link",
            "Open the secure login URL from your latest Telegram message, or restart login from the bot.",
            "error",
            "🔐",
        ),
    }
    title, lead, status, icon = messages[kind]
    body = f"""
<div class="card status-card status-{status}">
  <div class="status-icon" aria-hidden="true">{icon}</div>
  <h1>{escape(title)}</h1>
  <p class="lead">{escape(lead)}</p>
</div>"""
    return _page_shell(title, body)