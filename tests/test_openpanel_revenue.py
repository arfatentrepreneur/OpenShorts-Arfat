"""OpenPanel revenue mirror: event shape, sign for refunds, acquisition props
from the SignupAttribution row, and silence when OpenPanel is unconfigured.

Pure logic — the HTTP send is stubbed, no DB.
"""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from cloud import analytics


@pytest.fixture
def sent(monkeypatch):
    """Capture payloads instead of POSTing; pretend OpenPanel is configured."""
    box = []
    monkeypatch.setenv("OPENPANEL_CLIENT_ID", "cid")
    monkeypatch.setenv("OPENPANEL_CLIENT_SECRET", "sec")

    class _Loop:
        def create_task(self, coro):
            box.append(coro.cr_frame.f_locals["payload"])
            coro.close()

    monkeypatch.setattr(analytics.asyncio, "get_running_loop", lambda: _Loop())
    return box


def test_revenue_event_shape(sent):
    analytics.track_revenue("11111111-1111-1111-1111-111111111111", 5900, "usd",
                            type="new", plan="creator", interval="monthly", channel="github.com",
                            email=None)
    assert len(sent) == 1
    p = sent[0]
    assert p["type"] == "track"
    assert p["payload"]["name"] == "revenue"
    assert p["payload"]["profileId"] == "11111111-1111-1111-1111-111111111111"
    props = p["payload"]["properties"]
    assert props["__revenue"] == 5900          # minor units, what OpenPanel's views read
    assert props["amount"] == 59.0             # major units for custom reports
    assert props["currency"] == "USD"
    assert props["plan"] == "creator" and props["channel"] == "github.com"
    assert "email" not in props                # None props are dropped


def test_refund_is_negative_and_zero_is_skipped(sent):
    analytics.track_revenue("u", -1500, "eur", type="refund")
    analytics.track_revenue("u", 0, "usd")
    analytics.track_revenue("u", "not-a-number", "usd")
    assert [e["payload"]["properties"]["__revenue"] for e in sent] == [-1500]
    assert sent[0]["payload"]["properties"]["currency"] == "EUR"


def test_silent_when_unconfigured(sent, monkeypatch):
    monkeypatch.delenv("OPENPANEL_CLIENT_ID")
    analytics.track_revenue("u", 5900, "usd")
    assert sent == []


def test_acquisition_properties():
    assert analytics.acquisition_properties(None) == {"channel": "direct"}
    row = SimpleNamespace(
        referrer="https://github.com/mutonby/openshorts", referrer_host="github.com",
        landing_path="/?utm_source=github", utm_source="", utm_medium=None, utm_campaign="readme",
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    assert analytics.acquisition_properties(row) == {
        "channel": "github.com",
        "utm_campaign": "readme",
        "referrer": "github.com",
        "landing_path": "/?utm_source=github",
        "signup_date": "2026-09-01T00:00:00+00:00",
    }
    row.utm_source = "producthunt"
    assert analytics.acquisition_properties(row)["channel"] == "producthunt"
