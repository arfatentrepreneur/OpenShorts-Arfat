"""Subscription-state gates: who is entitled, who is blocked from checkout, and
who must still be able to reach the billing portal.

Regression cover for the past_due dead end found in prod on 25-jul-2026: a
customer whose card was declined read as a plain free account (no warning, no
portal button) AND was blocked from starting a new checkout — no way out.
"""
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

import pytest

from cloud import config, metering


def _sub(status="active", period_end=None):
    return SimpleNamespace(
        status=status,
        current_period_end=period_end or (datetime.now(timezone.utc) + timedelta(days=20)),
    )


class TestEntitles:
    """Only a live subscription inside its period grants plan minutes."""

    @pytest.mark.parametrize("status", ["active", "trialing"])
    def test_live_states_entitle(self, status):
        assert metering._entitles(_sub(status)) is True

    @pytest.mark.parametrize("status", [
        "past_due", "unpaid", "incomplete", "paused", "canceled", "incomplete_expired",
    ])
    def test_everything_else_does_not_entitle(self, status):
        assert metering._entitles(_sub(status)) is False

    def test_expired_period_does_not_entitle(self):
        past = datetime.now(timezone.utc) - timedelta(days=1)
        assert metering._entitles(_sub("active", period_end=past)) is False

    def test_no_subscription_does_not_entitle(self):
        assert metering._entitles(None) is False


class TestCheckoutBlockingStates:
    """Block only while Stripe is actually trying to collect."""

    @pytest.mark.parametrize("status", ["active", "trialing", "past_due", "unpaid", "paused"])
    def test_dunning_or_live_blocks_a_second_subscription(self, status):
        assert status in config.CHECKOUT_BLOCKING_STATES

    def test_incomplete_does_not_block_the_retry(self):
        # Payment abandoned at 3DS/confirm. Nothing is being collected and Stripe
        # expires the row within 24h, so blocking only stops the user paying.
        assert "incomplete" not in config.CHECKOUT_BLOCKING_STATES

    @pytest.mark.parametrize("status", ["canceled", "incomplete_expired"])
    def test_terminal_states_do_not_block(self, status):
        assert status not in config.CHECKOUT_BLOCKING_STATES


class TestAttentionStates:
    """States the account page must surface so the customer can act."""

    @pytest.mark.parametrize("status", ["past_due", "unpaid", "incomplete", "paused"])
    def test_broken_payment_is_visible(self, status):
        assert status in config.BILLING_ATTENTION_STATES

    @pytest.mark.parametrize("status", ["canceled", "incomplete_expired"])
    def test_terminal_states_are_not_nagged_about(self, status):
        assert status not in config.BILLING_ATTENTION_STATES

    def test_none_of_them_entitle_minutes(self):
        # The whole point: these look like "free" to the metering layer, which is
        # why they have to be reported separately or they vanish from the UI.
        for status in config.BILLING_ATTENTION_STATES:
            assert metering._entitles(_sub(status)) is False

    def test_every_blocking_state_is_either_live_or_flagged(self):
        # A state that blocks checkout but is invisible in /api/me would recreate
        # the dead end, so the two sets must stay reconciled.
        for status in config.CHECKOUT_BLOCKING_STATES:
            assert status in ("active", "trialing") or status in config.BILLING_ATTENTION_STATES


class TestNewSubscriberAlert:
    """The 'New subscriber' admin alert must mean money, not a click on pay."""

    def test_incomplete_is_silent(self):
        assert config.new_subscriber_label("incomplete") is None

    @pytest.mark.parametrize("status", ["active", "trialing"])
    def test_paid_states_alert(self, status):
        assert config.new_subscriber_label(status)
