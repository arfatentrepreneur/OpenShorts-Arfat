"""Opting out of the one email we send that is a commercial communication.

Every other message OpenShorts sends is a service notice: a sign-in link, "your
clips are ready", "your free clips are deleted tomorrow", "your account has been
deleted". ``send_out_of_minutes_email`` is not — it leads with a price and a
Buy button, which makes it a comunicación comercial under LSSI art. 21. Art.
21.2 permits it to an existing customer for a similar product, but only if
*every single message* offers a simple, free way to refuse — and until now it
offered none: no footer link and no ``List-Unsubscribe`` header.

The link has to work with no session (the reader is in their mail client, not
the app) and must never expire, so it carries an HMAC of the user id keyed on
the app's JWT secret. That token proves nothing except "the holder was sent an
email addressed to this account", and the only thing it can do is set the flag
— it cannot read anything, and it cannot re-subscribe anyone.
"""
import hashlib
import hmac

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from sqlalchemy import update

from . import database
from .config import settings
from .models import User

router = APIRouter(prefix="/api/marketing", tags=["marketing"])


def unsubscribe_token(user_id) -> str:
    return hmac.new(settings.jwt_secret.encode(), f"unsub:{user_id}".encode(),
                    hashlib.sha256).hexdigest()[:32]


def unsubscribe_url(user_id) -> str:
    """The absolute link that goes in the email body and the header.

    Empty when PUBLIC_API_URL is unset, and ``emails.py`` then falls back to a
    plain "reply to this email" line rather than printing a broken link.
    """
    base = settings.public_api_url
    if not base or not settings.jwt_secret:
        return ""
    return (f"{base}/api/marketing/unsubscribe"
            f"?u={user_id}&t={unsubscribe_token(user_id)}")


async def is_opted_out(user_id) -> bool:
    """True when this account has refused commercial email."""
    from sqlalchemy import select
    async with database.session() as s:
        value = (await s.execute(
            select(User.marketing_opt_out).where(User.id == user_id)
        )).scalar_one_or_none()
    return bool(value)


_PAGE = """<!doctype html><meta charset="utf-8">
<title>%(title)s</title>
<style>body{font:16px/1.6 system-ui,sans-serif;max-width:34rem;margin:12vh auto;
padding:0 1.5rem;color:#111}h1{font-size:1.35rem}a{color:#111}</style>
<h1>%(title)s</h1><p>%(body)s</p>"""


def _page(title, body, status=200):
    return HTMLResponse(_PAGE % {"title": title, "body": body}, status_code=status)


async def _opt_out(u: str, t: str):
    if not u or not t or not settings.jwt_secret:
        return _page("That link didn't work",
                     "The unsubscribe link is incomplete. Email "
                     "<a href='mailto:info@openshorts.app'>info@openshorts.app</a> "
                     "and we'll do it by hand.", status=400)
    if not hmac.compare_digest(t, unsubscribe_token(u)):
        return _page("That link didn't work",
                     "We couldn't verify this unsubscribe link. Email "
                     "<a href='mailto:info@openshorts.app'>info@openshorts.app</a> "
                     "and we'll do it by hand.", status=400)
    try:
        async with database.session() as s:
            async with s.begin():
                await s.execute(update(User).where(User.id == u)
                                .values(marketing_opt_out=True))
    except Exception:
        # A malformed uuid, or the account is already gone. Both mean there is
        # nothing left to mail, so the honest answer is still "done".
        pass
    return _page("You're unsubscribed",
                 "We won't send you upgrade emails again. You will still get "
                 "the messages the service itself needs to send you — your "
                 "sign-in link, and a warning before clips are deleted. You can "
                 "delete your account entirely from Account → Delete account.")


@router.get("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe_get(u: str = "", t: str = ""):
    return await _opt_out(u, t)


@router.post("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe_post(u: str = "", t: str = ""):
    """RFC 8058 one-click. Gmail and Outlook POST this URL from their own
    "Unsubscribe" button, without ever showing the user our page."""
    return await _opt_out(u, t)
