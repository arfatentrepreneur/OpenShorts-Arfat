"""Account erasure (cloud/account.py): the GDPR Art. 17 delete.

The one thing worth testing without a database is coverage. The endpoint tells
the user everything is gone, so any table holding their rows that the delete
list forgets turns that sentence into a false statement — and a table added a
year from now is exactly the kind of thing nobody remembers to add here.
"""
import hashlib
import os

from cloud import account
from cloud.database import Base
from cloud.models import AccountDeletion, User


def _tables_referencing_users():
    """Every table with a foreign key into ``users`` — the ground truth the
    delete list has to keep up with."""
    found = set()
    for table in Base.metadata.tables.values():
        for fk in table.foreign_keys:
            if fk.column.table.name == User.__tablename__:
                found.add(table.name)
    return found


class TestCoverage:
    def test_every_user_owned_table_is_erased(self):
        listed = {m.__tablename__ for m in account.USER_OWNED_TABLES}
        missing = _tables_referencing_users() - listed
        assert not missing, (
            f"{missing} reference users.id but are not erased on account "
            f"deletion — add them to account.USER_OWNED_TABLES")

    def test_children_are_deleted_before_their_parents(self):
        # clip_expiry_warnings has an FK into user_videos, so deleting the
        # videos first would trip that constraint.
        order = [m.__tablename__ for m in account.USER_OWNED_TABLES]
        assert order.index("clip_expiry_warnings") < order.index("user_videos")

    def test_the_erasure_record_itself_is_not_erased(self):
        # It has no FK to users on purpose (the row it would point at is gone),
        # so it must not appear in the delete list either.
        assert AccountDeletion not in account.USER_OWNED_TABLES
        assert AccountDeletion.__tablename__ not in _tables_referencing_users()


class TestDeletionReason:
    """The reason outlives the account, so it must never carry free text."""

    def test_the_ui_offers_exactly_the_reasons_the_server_accepts(self):
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        card = open(os.path.join(
            repo, "dashboard/src/components/DeleteAccountCard.jsx")).read()
        for value in account.DELETION_REASONS:
            assert f"'{value}'" in card, f"{value} is accepted but never offered"

    def test_the_column_cannot_hold_a_typed_sentence(self):
        # 32 chars is under every label in the list and far under anything a
        # user could write, so a free-text regression fails loudly at the DB.
        assert AccountDeletion.reason.type.length == 32
        assert max(len(r) for r in account.DELETION_REASONS) <= 32


class TestEmailFingerprint:
    def test_is_a_plain_sha256_of_the_normalised_address(self):
        assert account.email_fingerprint("user@example.com") == \
            hashlib.sha256(b"user@example.com").hexdigest()

    def test_does_not_contain_the_address(self):
        assert "user@example.com" not in account.email_fingerprint("user@example.com")

    def test_survives_the_aliasing_the_account_key_ignores(self):
        # Sign-up normalises Gmail dots and +tags, so the fingerprint has to
        # match the same way or a deleted user could not be found by the
        # address they actually typed.
        assert account.email_fingerprint("Foo.Bar+news@gmail.com") == \
            account.email_fingerprint("foobar@gmail.com")

    def test_different_addresses_differ(self):
        assert account.email_fingerprint("a@example.com") != \
            account.email_fingerprint("b@example.com")


# --------------------------------------------------------------------------- #
# The endpoint's gates
# --------------------------------------------------------------------------- #
import asyncio                                                   # noqa: E402

import pytest                                                    # noqa: E402
from fastapi import FastAPI                                      # noqa: E402
from fastapi.testclient import TestClient                         # noqa: E402


class _FakeUser:
    id = "11111111-1111-1111-1111-111111111111"
    email = "owner@example.com"


@pytest.fixture
def client(monkeypatch):
    """The endpoint with authentication stubbed out.

    Everything past the confirmation gate needs Postgres, so these cover only
    what happens before it — which is the part that decides whether an account
    gets destroyed.
    """
    async def _fake_session_user(request):
        return _FakeUser()

    monkeypatch.setattr(account, "_session_user", _fake_session_user)
    app = FastAPI()
    app.include_router(account.router)
    return TestClient(app, raise_server_exceptions=False)


def _delete(client, **body):
    return client.request("DELETE", "/api/account", json=body)


class TestConfirmationGate:
    def test_a_wrong_email_deletes_nothing(self, client):
        r = _delete(client, confirm_email="someone.else@example.com")
        assert r.status_code == 400

    def test_an_empty_confirmation_deletes_nothing(self, client):
        # The UI can render before /api/me resolves; an empty box must never
        # read as agreement.
        assert _delete(client, confirm_email="").status_code == 400

    def test_a_missing_confirmation_deletes_nothing(self, client):
        assert client.request("DELETE", "/api/account").status_code == 422

    def test_the_right_email_gets_past_the_gate(self, client):
        # No database here, so "past the gate" is anything but the 400/422 the
        # cases above return. What matters is that it stopped rejecting.
        assert _delete(client, confirm_email="owner@example.com").status_code \
            not in (400, 422)

    def test_the_gate_ignores_case_and_gmail_aliasing(self, client, monkeypatch):
        # Sign-up normalises the address, so the stored one may not be what the
        # user remembers typing.
        class _Gmail(_FakeUser):
            email = "foobar@gmail.com"

        async def _fake(request):
            return _Gmail()
        monkeypatch.setattr(account, "_session_user", _fake)
        assert _delete(client, confirm_email="Foo.Bar+news@GMAIL.com").status_code \
            not in (400, 422)


class TestApiKeyAuth:
    def test_an_api_key_cannot_delete_the_account_it_belongs_to(self):
        # Not the stubbed fixture: this must be the real _session_user.
        app = FastAPI()
        app.include_router(account.router)
        c = TestClient(app, raise_server_exceptions=False)
        for headers in ({"Authorization": "Bearer osk_abc123"},
                        {"X-API-Key": "osk_abc123"}):
            r = c.request("DELETE", "/api/account",
                          json={"confirm_email": "owner@example.com"},
                          headers=headers)
            assert r.status_code == 403


class TestStripeCancel:
    def test_an_already_cancelled_subscription_does_not_trap_the_user(self, monkeypatch):
        """Our row can say "active" long after Stripe stopped billing — a
        cancellation made in the portal whose webhook never landed. If that
        raised, the one account impossible to delete would be the one Stripe
        already stopped charging."""
        stripe = pytest.importorskip("stripe")  # not in the minimal CI deps

        class _Row:
            stripe_subscription_id = "sub_gone"
            status = "active"
            plan = "starter"

        class _Result:
            def scalars(self):
                return [_Row()]

        class _Session:
            async def execute(self, _stmt):
                return _Result()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_a):
                return False

        def _boom(_sid):
            raise stripe.InvalidRequestError("No such subscription", None)

        monkeypatch.setattr(account.database, "session", lambda: _Session())
        monkeypatch.setattr(stripe.Subscription, "cancel", staticmethod(_boom))

        assert asyncio.run(account._cancel_subscriptions("uid")) == "starter"
