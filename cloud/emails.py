"""Transactional + operational email via SMTP (e.g. Namecheap Private Email).

If SMTP isn't configured (local dev), messages are printed to the server log so
the magic-link flow and alerts still work without a real mailbox.
"""
import asyncio
import smtplib
import ssl
from email.message import EmailMessage

from .config import settings


def _send_sync(to: str, subject: str, html: str):
    msg = EmailMessage()
    msg["From"] = settings.email_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content("This message requires an HTML-capable email client.")
    msg.add_alternative(html, subtype="html")

    if settings.smtp_port == 465:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port,
                              context=ssl.create_default_context(), timeout=20) as s:
            s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)


async def send_email(to: str, subject: str, html: str):
    """Send an email (async wrapper). Logs instead of sending if SMTP is unset."""
    if not settings.smtp_configured:
        print(f"✉️  [DEV email → {to}] {subject}")
        return
    try:
        await asyncio.to_thread(_send_sync, to, subject, html)
    except Exception as e:
        print(f"⚠️  Failed to send email to {to}: {e}")


async def send_magic_link_email(email: str, link: str):
    if not settings.smtp_configured:
        print(f"✉️  [DEV magic link] {email} -> {link}")
        return
    html = f"""
      <div style="font-family:system-ui,sans-serif;max-width:480px;margin:0 auto">
        <h2>Sign in to OpenShorts</h2>
        <p>Click the button below to sign in. This link expires in 15 minutes.</p>
        <p><a href="{link}" style="display:inline-block;background:#111;color:#fff;
           padding:12px 20px;border-radius:8px;text-decoration:none">Sign in</a></p>
        <p style="color:#666;font-size:13px">If you didn't request this, ignore this email.</p>
      </div>
    """
    await send_email(email, "Your OpenShorts sign-in link", html)


GITHUB_REPO_URL = "https://github.com/mutonby/openshorts"


async def send_clips_ready_email(email: str, job_title: str, clip_count: int,
                                 dashboard_url: str):
    """Job-completion notice: lets the user close the tab during processing."""
    title = (job_title or "Your video").strip()
    html = f"""
      <div style="font-family:system-ui,sans-serif;max-width:480px;margin:0 auto">
        <h2>Your clips are ready 🎬</h2>
        <p><strong>{title}</strong> produced {clip_count} viral-ready
           clip{'s' if clip_count != 1 else ''}. They're waiting in your dashboard.</p>
        <p><a href="{dashboard_url}" style="display:inline-block;background:#111;color:#fff;
           padding:12px 20px;border-radius:8px;text-decoration:none">View my clips</a></p>
        <p style="color:#666;font-size:13px">Enjoying OpenShorts? A
           <a href="{GITHUB_REPO_URL}" style="color:#666">star on GitHub</a> helps a lot ⭐</p>
      </div>
    """
    await send_email(email, f"Your clips are ready — {title}", html)


async def send_autopilot_clips_email(email: str, video_title: str, clip_count: int,
                                     scheduled_count: int, dashboard_url: str):
    """Autopilot finished clipping a new channel video on its own.

    This is the email that makes Autopilot visible: the user did nothing, and
    this is where they find out the work got done anyway.
    """
    import html as _html
    title = _html.escape((video_title or "your new video").strip())
    plural = "s" if clip_count != 1 else ""
    if scheduled_count:
        posting = (f"<p>The best {scheduled_count} {'is' if scheduled_count == 1 else 'are'} "
                   f"scheduled to publish, one a day, on the accounts you picked.</p>")
    else:
        posting = "<p>Review them, tweak anything you like, and post the ones you want.</p>"
    html = f"""
      <div style="font-family:system-ui,sans-serif;max-width:480px;margin:0 auto">
        <h2>Autopilot clipped your new video 🎬</h2>
        <p>You published <strong>{title}</strong> and OpenShorts already turned it
           into {clip_count} short{plural}.</p>
        {posting}
        <p><a href="{dashboard_url}" style="display:inline-block;background:#111;color:#fff;
           padding:12px 20px;border-radius:8px;text-decoration:none">See my clips</a></p>
        <p style="color:#666;font-size:13px">You can pause Autopilot anytime from the
           Autopilot page in your dashboard.</p>
      </div>
    """
    await send_email(email, f"Autopilot: {clip_count} new short{plural} from your video", html)


async def send_clips_expiring_email(email: str, clip_count: int):
    """Free clips enter their last day before deletion — honest loss aversion.

    The deadline is real (FREE_CLIP_RETENTION_DAYS); this simply makes it
    visible instead of deleting silently. Doubles as re-engagement for users
    who clipped once and went quiet.
    """
    # The app has no /dashboard route and never has: it is a single-page app
    # routed entirely through the hash, and #app is what opens it (see
    # dashboard/src/main.jsx). /dashboard used to land on the SPA fallback, so
    # the button quietly showed the marketing page; now that unknown paths
    # return a real 404 it fails visibly.
    dash = f"{settings.frontend_url}/#app"
    n = clip_count
    clips = f"{n} clip" + ("s" if n != 1 else "")
    html = f"""
      <div style="font-family:system-ui,sans-serif;max-width:480px;margin:0 auto">
        <h2>Your {clips} will be deleted tomorrow ⏳</h2>
        <p>Free clips are stored for 7 days, and {('these' if n != 1 else 'this one')}
           {'are' if n != 1 else 'is'} about to expire. Two ways to keep them:</p>
        <ul style="line-height:1.9;padding-left:20px">
          <li><strong>Download them now</strong> from your dashboard, or</li>
          <li><strong>Upgrade to Starter ($12/mo)</strong> &mdash; clips stored forever,
              no watermark, and 100 minutes every month.</li>
        </ul>
        <p><a href="{dash}" style="display:inline-block;background:#111;color:#fff;
           padding:12px 20px;border-radius:8px;text-decoration:none">Save my clips</a></p>
        <p style="color:#666;font-size:13px">After tomorrow they're gone for good
           &mdash; we can't recover deleted clips.</p>
      </div>
    """
    print(f"⏳ Clips-expiring email → {email} ({clips})")
    await send_email(email, f"Your {clips} will be deleted tomorrow", html)


async def send_out_of_minutes_email(email: str, upgrade_url: str):
    """Free user hit their monthly quota — the natural upgrade moment.

    Mirrors the in-app upgrade modal: lead with what they lose by staying free
    (watermark, clips deleted after 7 days) and one concrete plan, not a
    generic pricing link.
    """
    html = f"""
      <div style="font-family:system-ui,sans-serif;max-width:480px;margin:0 auto">
        <h2>Your video is still waiting 🎬</h2>
        <p>You've used this month's 20 free minutes — which usually means the
           clips are working for you. Here's what <strong>Starter ($12/mo)</strong>
           changes today:</p>
        <ul style="line-height:1.9;padding-left:20px">
          <li><strong>100 minutes</strong> every month (5&times; your free quota)</li>
          <li><strong>No watermark</strong> on your clips</li>
          <li>Clips stored <strong>forever</strong> &mdash; free clips are deleted after 7 days</li>
        </ul>
        <p><a href="{upgrade_url}" style="display:inline-block;background:#111;color:#fff;
           padding:12px 20px;border-radius:8px;text-decoration:none">Upgrade and finish your video</a></p>
        <p style="color:#666;font-size:13px">Cancel anytime. Your free minutes
           reset on the 1st of every month.</p>
      </div>
    """
    print(f"✉️  Out-of-minutes upsell email → {email}")
    await send_email(email, "Your video is waiting — you're out of free minutes", html)


async def send_account_deleted_email(email: str):
    """Confirmation that an account was erased. Sent last, to an address we no
    longer hold: this is the only notice the user will ever get, and it is also
    the only signal they would have if the deletion had not been theirs.
    """
    html = """
      <div style="font-family:system-ui,sans-serif;max-width:480px;margin:0 auto">
        <h2>Your OpenShorts account has been deleted</h2>
        <p>Everything is gone: your account, your projects, your clips and their
           transcripts, your API keys, and the connection to any social accounts
           you had linked. Any active subscription was cancelled.</p>
        <p>Two things we keep, and why:</p>
        <ul style="line-height:1.7;padding-left:20px">
          <li><strong>Your invoices</strong>, for six years &mdash; Spanish
              commercial law requires it, and the Stripe customer reference
              that finds them goes with it.</li>
          <li><strong>A record that this deletion happened</strong>, for five
              years, holding a one-way hash of your email address instead of
              the address itself.</li>
        </ul>
        <p>You can sign up again any time with the same address; it will be a
           brand-new, empty account.</p>
        <p style="color:#666;font-size:13px">If this wasn't you, reply to this
           email straight away &mdash; info@openshorts.app.</p>
      </div>
    """
    print(f"✉️  Account-deleted confirmation → {email}")
    await send_email(email, "Your OpenShorts account has been deleted", html)
