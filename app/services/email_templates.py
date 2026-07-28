"""HTML bodies for transactional email.

Email clients strip <style> unpredictably, so every rule that matters is
inlined; the <style> block only carries the dark-mode and small-screen
overrides, which cannot be expressed inline. Colours mirror the frontend
tokens in `globals.css` (ink #18181b for primary, emerald #009966 for the
brand accent), converted to hex because email clients predate oklch().

The declarations are hoisted into constants purely so the markup below stays
inside the line limit.
"""

from app.core.config import settings

# Reply-to on every transactional email, and the address in the footer —
# `EMAIL_FROM` is a sending identity only, nobody reads it. Static because it
# is tied to the domain, not to the deployment.
SUPPORT_ADDRESS = "support@waverify.app"
# Absolute: email clients cannot resolve relative paths, and FRONTEND_URL
# points at localhost in development where the image would not load.
LOGO_URL = "https://waverify.app/brand/tile-512.png"

_INK = "#18181b"
_EMERALD = "#009966"
_MUTED = "#71717a"
_BORDER = "#e4e4e7"
_CANVAS = "#fafafa"
_FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
_MONO = "ui-monospace,SFMono-Regular,Menlo,monospace"

_STYLE = f"""
  a {{ color: {_EMERALD}; }}
  @media (prefers-color-scheme: dark) {{
    .canvas {{ background-color: #0a0a0b !important; }}
    /* border-top-color has to be restated: the shorthand above wins otherwise
       and the emerald accent rule disappears. */
    .card {{ background-color: #18181b !important; border-color: #27272a !important;
             border-top-color: {_EMERALD} !important; }}
    .heading, .wordmark {{ color: #fafafa !important; }}
    .body {{ color: #a1a1aa !important; }}
    .muted, .footer, .footer a {{ color: #8b8b95 !important; }}
    .fallback {{ background-color: #202024 !important; border-color: #2e2e33 !important; }}
    .cta {{ background-color: #fafafa !important; }}
    .cta a {{ color: #18181b !important; }}
  }}
  @media only screen and (max-width: 600px) {{
    .card {{ padding: 28px 22px !important; }}
  }}
"""

_S_PREHEADER = f"display:none;font-size:1px;color:{_CANVAS};max-height:0;overflow:hidden;"
_S_WRAP = f"max-width:560px;width:100%;font-family:{_FONT};"
_S_LOGO = "vertical-align:middle;border:0;border-radius:9px;"
_S_WORDMARK = (
    "vertical-align:middle;padding-left:10px;font-size:17px;font-weight:600;"
    f"letter-spacing:-0.02em;color:{_INK};"
)
_S_CARD = (
    f"background-color:#ffffff;border:1px solid {_BORDER};border-top:3px solid {_EMERALD};"
    "border-radius:12px;padding:36px 32px;"
)
_S_HEADING = (
    "margin:0 0 12px;font-size:20px;line-height:1.35;font-weight:600;"
    f"letter-spacing:-0.02em;color:{_INK};"
)
_S_BODY = "margin:0 0 28px;font-size:15px;line-height:1.6;color:#52525b;"
_S_CTA_CELL = f"border-radius:8px;background-color:{_INK};"
_S_CTA_LINK = (
    "display:inline-block;padding:12px 22px;font-size:15px;font-weight:500;"
    "color:#ffffff;text-decoration:none;border-radius:8px;"
)
_S_NOTE = f"margin:28px 0 8px;font-size:13px;line-height:1.5;color:{_MUTED};"
_S_CLOSING = f"margin:24px 0 0;font-size:13px;line-height:1.5;color:{_MUTED};"
_S_FALLBACK = (
    f"margin:0;padding:10px 12px;background-color:{_CANVAS};border:1px solid {_BORDER};"
    f"border-radius:8px;font-family:{_MONO};font-size:12px;line-height:1.5;word-break:break-all;"
)
_S_FOOTER = f"padding:20px 4px 0;font-size:12px;line-height:1.6;color:{_MUTED};"


def render_email(
    *,
    preheader: str,
    heading: str,
    intro: str,
    cta_label: str,
    cta_url: str,
    expiry_note: str,
    closing: str,
) -> str:
    """Render one transactional email.

    `preheader` is the grey line inboxes show next to the subject; it is kept
    out of the visible body by a hidden span.
    """
    return f"""\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<meta name="supported-color-schemes" content="light dark">
<title>{heading}</title>
<style>{_STYLE}</style>
</head>
<body class="canvas" style="margin:0;padding:0;background-color:{_CANVAS};">
<span style="{_S_PREHEADER}">{preheader}</span>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
       class="canvas" style="background-color:{_CANVAS};">
  <tr>
    <td align="center" style="padding:40px 16px;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
             style="{_S_WRAP}">

        <tr>
          <td style="padding-bottom:20px;">
            <a href="{settings.FRONTEND_URL}" style="text-decoration:none;">
              <img src="{LOGO_URL}" width="36" height="36" alt=""
                   style="{_S_LOGO}">
              <span class="wordmark" style="{_S_WORDMARK}">WAVerify</span>
            </a>
          </td>
        </tr>

        <tr>
          <td class="card" style="{_S_CARD}">
            <h1 class="heading" style="{_S_HEADING}">{heading}</h1>

            <p class="body" style="{_S_BODY}">{intro}</p>

            <table role="presentation" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td class="cta" style="{_S_CTA_CELL}">
                  <a href="{cta_url}" style="{_S_CTA_LINK}">{cta_label}</a>
                </td>
              </tr>
            </table>

            <p class="muted" style="{_S_NOTE}">
              {expiry_note} If the button does not work, paste this link into your browser:
            </p>
            <p class="fallback" style="{_S_FALLBACK}">
              <a href="{cta_url}" style="color:{_EMERALD};text-decoration:none;">{cta_url}</a>
            </p>

            <p class="muted" style="{_S_CLOSING}">{closing}</p>
          </td>
        </tr>

        <tr>
          <td class="footer" style="{_S_FOOTER}">
            Sent by WAVerify &middot;
            <a href="mailto:{SUPPORT_ADDRESS}"
               style="color:{_MUTED};text-decoration:underline;"
               >{SUPPORT_ADDRESS}</a><br>
            You received this because this address was used to sign up for WAVerify.
          </td>
        </tr>

      </table>
    </td>
  </tr>
</table>
</body>
</html>
"""
