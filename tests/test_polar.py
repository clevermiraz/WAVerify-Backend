"""Polar checkout and fulfilment webhook.

The webhook is the only path that grants paid credits, and it is reachable by
anyone on the internet, so the cases that matter here are the adversarial
ones: forged signatures, replayed deliveries, and payloads that lie about
which plan was bought.
"""

import base64
import json
import time
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from standardwebhooks.webhooks import Webhook

from app.core.config import settings
from app.repositories.wallet import WalletRepository

API = "/api/v1"
WEBHOOK = f"{API}/billing/polar/webhook"
SECRET = "whsec_test_secret_value"

FREE_CREDITS = 20
STARTER_CREDITS = 7_500


@pytest.fixture(autouse=True)
def polar_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """Turn the integration on without putting real credentials in the repo."""
    monkeypatch.setattr(settings, "POLAR_ACCESS_TOKEN", "polar_oat_test")
    monkeypatch.setattr(settings, "POLAR_WEBHOOK_SECRET", SECRET)


def build_order(
    *,
    user_id: str,
    order_id: str = "ord_test_1",
    product_slug: str | None = "starter",
    checkout_slug: str = "starter",
    amount: int = 900,
) -> dict:
    """A realistic `order.paid` body.

    `product_slug` is what the Polar product is tagged with — the only source
    the backend trusts. `checkout_slug` is the metadata we set when opening
    the checkout, which the tests use to prove it is *not* trusted.
    """
    now = "2026-07-28T10:00:00Z"
    product_metadata = {} if product_slug is None else {"plan_slug": product_slug}
    return {
        "id": order_id,
        "created_at": now,
        "modified_at": None,
        "status": "paid",
        "paid": True,
        "subtotal_amount": amount,
        "discount_amount": 0,
        "net_amount": amount,
        "amount": amount,
        "tax_amount": 0,
        "total_amount": amount,
        "refunded_amount": 0,
        "refunded_tax_amount": 0,
        "refundable_amount": amount,
        "refundable_tax_amount": 0,
        "due_amount": 0,
        "applied_balance_amount": 0,
        "platform_fee_amount": 0,
        "platform_fee_currency": "usd",
        "currency": "usd",
        "billing_reason": "purchase",
        "billing_name": "Test Buyer",
        "billing_address": None,
        "is_invoice_generated": False,
        "description": "Credit pack",
        "invoice_number": "INV-1",
        "receipt_number": "RCP-1",
        "customer_id": "cus_test",
        "product_id": "prod_test",
        "discount_id": None,
        "subscription_id": None,
        "checkout_id": "chk_test",
        "metadata": {"user_id": user_id, "plan_slug": checkout_slug},
        "custom_field_data": {},
        "customer": {
            "id": "cus_test",
            "created_at": now,
            "modified_at": None,
            "metadata": {},
            "external_id": user_id,
            "email": "buyer@example.com",
            "email_verified": True,
            "name": "Test Buyer",
            "billing_name": "Test Buyer",
            "billing_address": None,
            "tax_id": None,
            "organization_id": "org_test",
            "deleted_at": None,
            "avatar_url": "https://example.com/a.png",
            "type": "individual",
        },
        "product": {
            "id": "prod_test",
            "created_at": now,
            "modified_at": None,
            "name": "Credit pack",
            "description": None,
            "recurring_interval": None,
            "recurring_interval_count": None,
            "is_recurring": False,
            "is_archived": False,
            "organization_id": "org_test",
            "metadata": product_metadata,
            "visibility": "public",
            "trial_interval": None,
            "trial_interval_count": None,
            "meter_interval": None,
            "meter_interval_count": None,
        },
        "discount": None,
        "subscription": None,
        "items": [],
    }


def sign(body: bytes, *, secret: str = SECRET, msg_id: str = "msg_1") -> dict[str, str]:
    """Headers Polar would send. It base64-encodes the secret before signing,
    which is what `validate_event` undoes on the way back in."""
    webhook = Webhook(base64.b64encode(secret.encode()).decode())
    timestamp = int(time.time())
    signature = webhook.sign(
        msg_id, datetime.fromtimestamp(timestamp, tz=UTC), body.decode()
    )
    return {
        "webhook-id": msg_id,
        "webhook-timestamp": str(timestamp),
        "webhook-signature": signature,
        "content-type": "application/json",
    }


def deliver(
    client: TestClient,
    order: dict,
    *,
    secret: str = SECRET,
    msg_id: str = "msg_1",
    event: str = "order.paid",
):
    body = json.dumps(
        {"type": event, "timestamp": "2026-07-28T10:00:00Z", "data": order}
    ).encode()
    return client.post(
        WEBHOOK, content=body, headers=sign(body, secret=secret, msg_id=msg_id)
    )


def balance(client: TestClient, registered: dict) -> int:
    response = client.get(f"{API}/billing", headers=registered["headers"])
    assert response.status_code == 200, response.text
    return response.json()["wallet"]["credits_balance"]


class TestWebhookAuthentication:
    def test_forged_signature_is_rejected(
        self, client: TestClient, registered: dict
    ) -> None:
        order = build_order(user_id=registered["user"]["id"])
        response = deliver(client, order, secret="whsec_the_wrong_secret")

        assert response.status_code == 403
        assert balance(client, registered) == FREE_CREDITS

    def test_unsigned_request_is_rejected(
        self, client: TestClient, registered: dict
    ) -> None:
        order = build_order(user_id=registered["user"]["id"])
        response = client.post(WEBHOOK, json={"type": "order.paid", "data": order})

        assert response.status_code == 403
        assert balance(client, registered) == FREE_CREDITS

    def test_tampered_body_is_rejected(
        self, client: TestClient, registered: dict
    ) -> None:
        """Signed for one payload, delivered with another."""
        order = build_order(user_id=registered["user"]["id"])
        body = json.dumps(
            {"type": "order.paid", "timestamp": "2026-07-28T10:00:00Z", "data": order}
        ).encode()
        headers = sign(body)

        swapped = build_order(user_id=registered["user"]["id"], product_slug="pro")
        forged = json.dumps(
            {"type": "order.paid", "timestamp": "2026-07-28T10:00:00Z", "data": swapped}
        ).encode()

        response = client.post(WEBHOOK, content=forged, headers=headers)

        assert response.status_code == 403
        assert balance(client, registered) == FREE_CREDITS


class TestFulfilment:
    def test_paid_order_grants_credits(
        self, client: TestClient, registered: dict
    ) -> None:
        order = build_order(user_id=registered["user"]["id"])
        response = deliver(client, order)

        assert response.status_code == 202
        assert balance(client, registered) == FREE_CREDITS + STARTER_CREDITS

    def test_redelivery_does_not_grant_twice(
        self, client: TestClient, registered: dict
    ) -> None:
        """Polar retries up to ten times and can be replayed by hand."""
        order = build_order(user_id=registered["user"]["id"])

        assert deliver(client, order).status_code == 202
        after_first = balance(client, registered)

        # Same order id, fresh delivery id — exactly what a retry looks like.
        assert deliver(client, order, msg_id="msg_2").status_code == 202

        assert balance(client, registered) == after_first
        assert after_first == FREE_CREDITS + STARTER_CREDITS

    def test_purchase_is_recorded(self, client: TestClient, registered: dict) -> None:
        deliver(client, build_order(user_id=registered["user"]["id"]))

        response = client.get(f"{API}/billing/payments", headers=registered["headers"])

        assert response.status_code == 200
        payments = response.json()
        assert len(payments) == 1
        assert payments[0]["status"] == "paid"
        assert payments[0]["credits_granted"] == STARTER_CREDITS
        assert payments[0]["amount_cents"] == 900

    def test_plan_comes_from_the_product_not_the_checkout(
        self, client: TestClient, registered: dict
    ) -> None:
        """The buyer must not be able to talk a $9 order into a Pro grant.

        Checkout metadata originates from a request; the product is configured
        in the Polar dashboard. Only the latter decides what is granted.
        """
        order = build_order(
            user_id=registered["user"]["id"],
            product_slug="starter",
            checkout_slug="pro",
        )

        assert deliver(client, order).status_code == 202

        assert balance(client, registered) == FREE_CREDITS + STARTER_CREDITS

    def test_unmapped_product_grants_nothing_but_is_recorded(
        self, client: TestClient, registered: dict
    ) -> None:
        """Money moved, but nothing says what was sold. Acknowledge, bank the
        record for support, grant nothing."""
        order = build_order(user_id=registered["user"]["id"], product_slug=None)

        response = deliver(client, order)

        # 2xx, because retrying would fail identically and Polar disables an
        # endpoint after ten consecutive failures.
        assert response.status_code == 202
        assert balance(client, registered) == FREE_CREDITS

        payments = client.get(
            f"{API}/billing/payments", headers=registered["headers"]
        ).json()
        assert len(payments) == 1
        assert payments[0]["status"] == "unmapped"
        assert payments[0]["credits_granted"] == 0

    def test_unknown_user_is_acknowledged_without_granting(
        self, client: TestClient, registered: dict
    ) -> None:
        order = build_order(user_id=str(uuid.uuid4()))

        response = deliver(client, order)

        assert response.status_code == 202
        assert balance(client, registered) == FREE_CREDITS


class TestRefunds:
    """Backs the published policy: the credits left over from a refunded
    purchase are removed, and a balance can never be driven negative."""

    def test_refund_removes_the_unused_credits(
        self, client: TestClient, registered: dict
    ) -> None:
        order = build_order(user_id=registered["user"]["id"])
        deliver(client, order)
        assert balance(client, registered) == FREE_CREDITS + STARTER_CREDITS

        deliver(client, order, msg_id="msg_refund", event="order.refunded")

        # The pack's credits go; the free-trial allowance is untouched.
        assert balance(client, registered) == FREE_CREDITS

    def test_refund_does_not_drive_the_balance_negative(
        self, client: TestClient, registered: dict, session: Session
    ) -> None:
        """Someone who spent most of the pack still lands on zero, not below —
        a negative balance would lock them out of the free tier too."""
        order = build_order(user_id=registered["user"]["id"])
        deliver(client, order)

        wallet = WalletRepository(session).get_for_user(
            uuid.UUID(registered["user"]["id"])
        )
        wallet.credits_balance = 300  # nearly all of it spent
        session.flush()

        deliver(client, order, msg_id="msg_refund", event="order.refunded")

        assert balance(client, registered) == 0

    def test_refund_is_idempotent(
        self, client: TestClient, registered: dict
    ) -> None:
        order = build_order(user_id=registered["user"]["id"])
        deliver(client, order)
        deliver(client, order, msg_id="msg_refund", event="order.refunded")
        after_first = balance(client, registered)

        deliver(client, order, msg_id="msg_refund_2", event="order.refunded")

        assert balance(client, registered) == after_first

    def test_refund_is_recorded_on_the_purchase(
        self, client: TestClient, registered: dict
    ) -> None:
        order = build_order(user_id=registered["user"]["id"])
        deliver(client, order)
        deliver(client, order, msg_id="msg_refund", event="order.refunded")

        payments = client.get(
            f"{API}/billing/payments", headers=registered["headers"]
        ).json()
        assert len(payments) == 1
        assert payments[0]["status"] == "refunded"

    def test_refund_for_an_unknown_order_is_acknowledged(
        self, client: TestClient, registered: dict
    ) -> None:
        """A refund for something we never recorded must not 500 — Polar would
        retry it ten times and then disable the endpoint."""
        order = build_order(user_id=registered["user"]["id"], order_id="ord_never_seen")

        response = deliver(
            client, order, msg_id="msg_refund", event="order.refunded"
        )

        assert response.status_code == 202
        assert balance(client, registered) == FREE_CREDITS


class TestCheckout:
    def test_free_plan_cannot_be_bought(
        self, client: TestClient, registered: dict
    ) -> None:
        response = client.post(
            f"{API}/billing/checkout",
            json={"plan_slug": "free"},
            headers=registered["headers"],
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "free_trial_already_claimed"

    def test_unknown_plan_is_rejected(
        self, client: TestClient, registered: dict
    ) -> None:
        response = client.post(
            f"{API}/billing/checkout",
            json={"plan_slug": "does-not-exist"},
            headers=registered["headers"],
        )

        assert response.status_code == 404

    def test_requires_authentication(self, client: TestClient) -> None:
        response = client.post(f"{API}/billing/checkout", json={"plan_slug": "starter"})

        assert response.status_code == 401
