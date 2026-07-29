"""End-to-end API tests."""

from fastapi.testclient import TestClient

API = "/api/v1"


class TestRegistration:
    def test_creates_user_on_the_free_plan(self, client: TestClient) -> None:
        response = client.post(
            f"{API}/auth/register",
            json={"email": "new@example.com", "password": "secret123"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["user"]["email"] == "new@example.com"
        assert body["user"]["role"] == "user"
        assert body["tokens"]["access_token"]

        billing = client.get(
            f"{API}/billing",
            headers={"Authorization": f"Bearer {body['tokens']['access_token']}"},
        )
        assert billing.json()["subscription"]["plan"]["slug"] == "free"

    def test_duplicate_email_conflicts(self, client: TestClient, registered: dict) -> None:
        response = client.post(
            f"{API}/auth/register",
            json={"email": registered["email"], "password": "secret123"},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "conflict"

    def test_email_is_normalised(self, client: TestClient) -> None:
        client.post(
            f"{API}/auth/register",
            json={"email": "Mixed@Example.com", "password": "secret123"},
        )
        response = client.post(
            f"{API}/auth/register",
            json={"email": "mixed@example.com", "password": "secret123"},
        )
        assert response.status_code == 409

    def test_password_must_mix_letters_and_digits(self, client: TestClient) -> None:
        response = client.post(
            f"{API}/auth/register",
            json={"email": "weak@example.com", "password": "abcdefgh"},
        )
        assert response.status_code == 422
        assert "password" in response.json()["error"]["details"]["fields"]


class TestLogin:
    def test_valid_credentials(self, client: TestClient, registered: dict) -> None:
        response = client.post(
            f"{API}/auth/login",
            json={"email": registered["email"], "password": registered["password"]},
        )
        assert response.status_code == 200

    def test_wrong_password(self, client: TestClient, registered: dict) -> None:
        response = client.post(
            f"{API}/auth/login",
            json={"email": registered["email"], "password": "wrongpass1"},
        )
        assert response.status_code == 401

    def test_unknown_email_gives_the_same_error(self, client: TestClient) -> None:
        response = client.post(
            f"{API}/auth/login",
            json={"email": "ghost@example.com", "password": "secret123"},
        )
        assert response.status_code == 401
        assert response.json()["error"]["message"] == "Incorrect email or password."


class TestTokenLifecycle:
    def test_refresh_rotates_and_revokes(self, client: TestClient, registered: dict) -> None:
        first = client.post(
            f"{API}/auth/refresh", json={"refresh_token": registered["refresh"]}
        )
        assert first.status_code == 200

        replay = client.post(
            f"{API}/auth/refresh", json={"refresh_token": registered["refresh"]}
        )
        assert replay.status_code == 401

    def test_logout_invalidates_the_refresh_token(
        self, client: TestClient, registered: dict
    ) -> None:
        client.post(f"{API}/auth/logout", json={"refresh_token": registered["refresh"]})
        response = client.post(
            f"{API}/auth/refresh", json={"refresh_token": registered["refresh"]}
        )
        assert response.status_code == 401

    def test_me_requires_a_token(self, client: TestClient) -> None:
        assert client.get(f"{API}/auth/me").status_code == 401


class TestCheck:
    def test_returns_the_documented_shape(
        self, client: TestClient, registered: dict
    ) -> None:
        response = client.post(
            f"{API}/check",
            json={"phone": "+8801712345678"},
            headers=registered["headers"],
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["phone"] == "+8801712345678"
        assert isinstance(body["exists"], bool)
        assert body["response_time_ms"] > 0
        assert set(body) >= {
            "success",
            "exists",
            "display_name",
            "about",
            "business",
            "profile_photo",
            "response_time_ms",
        }

    def test_normalises_input(self, client: TestClient, registered: dict) -> None:
        response = client.post(
            f"{API}/check",
            json={"phone": "880 1712-345678"},
            headers=registered["headers"],
        )
        assert response.json()["phone"] == "+8801712345678"

    def test_rejects_an_invalid_number(self, client: TestClient, registered: dict) -> None:
        response = client.post(
            f"{API}/check", json={"phone": "+1111111"}, headers=registered["headers"]
        )
        assert response.status_code == 422

    def test_requires_authentication(self, client: TestClient) -> None:
        response = client.post(f"{API}/check", json={"phone": "+8801712345678"})
        assert response.status_code == 401

    def test_works_with_an_api_key(self, client: TestClient, registered: dict) -> None:
        created = client.post(
            f"{API}/api-keys", json={"name": "CI"}, headers=registered["headers"]
        ).json()
        response = client.post(
            f"{API}/check",
            json={"phone": "+8801712345678"},
            headers={"X-API-Key": created["key"]},
        )
        assert response.status_code == 200

    def test_rejects_an_unknown_api_key(self, client: TestClient) -> None:
        response = client.post(
            f"{API}/check",
            json={"phone": "+8801712345678"},
            headers={"X-API-Key": "wav_test_not_a_real_key"},
        )
        assert response.status_code == 401

    def test_lookup_is_recorded_in_history(
        self, client: TestClient, registered: dict
    ) -> None:
        client.post(
            f"{API}/check",
            json={"phone": "+8801712345678"},
            headers=registered["headers"],
        )
        history = client.get(f"{API}/searches", headers=registered["headers"]).json()
        assert history["meta"]["total"] == 1
        assert history["items"][0]["phone_number"] == "+8801712345678"

    def test_quota_is_enforced(self, client: TestClient, registered: dict) -> None:
        # The Free plan allows 100 requests; drive usage past it directly
        # rather than issuing a hundred lookups.
        from datetime import UTC, datetime

        from app.db.session import SessionLocal
        from app.repositories.usage import UsageRepository

        with SessionLocal() as db:
            repo = UsageRepository(db)
            for _ in range(100):
                repo.record(
                    user_id=__import__("uuid").UUID(registered["user"]["id"]),
                    day=datetime.now(UTC).date(),
                    succeeded=True,
                    response_time_ms=10,
                )
            db.commit()

        response = client.post(
            f"{API}/check",
            json={"phone": "+8801712345678"},
            headers=registered["headers"],
        )
        assert response.status_code == 402
        assert response.json()["error"]["code"] == "quota_exceeded"


class TestApiKeys:
    def test_plaintext_is_returned_once_only(
        self, client: TestClient, registered: dict
    ) -> None:
        created = client.post(
            f"{API}/api-keys", json={"name": "Prod"}, headers=registered["headers"]
        )
        assert created.status_code == 201
        assert created.json()["key"].startswith("wav_")

        listed = client.get(f"{API}/api-keys", headers=registered["headers"]).json()
        assert "key" not in listed[0]
        assert listed[0]["prefix"]

    def test_duplicate_name_conflicts(self, client: TestClient, registered: dict) -> None:
        client.post(f"{API}/api-keys", json={"name": "Prod"}, headers=registered["headers"])
        response = client.post(
            f"{API}/api-keys", json={"name": "Prod"}, headers=registered["headers"]
        )
        assert response.status_code == 409

    def test_rename_and_delete(self, client: TestClient, registered: dict) -> None:
        key_id = client.post(
            f"{API}/api-keys", json={"name": "Old"}, headers=registered["headers"]
        ).json()["id"]

        renamed = client.patch(
            f"{API}/api-keys/{key_id}",
            json={"name": "New"},
            headers=registered["headers"],
        )
        assert renamed.json()["name"] == "New"

        assert (
            client.delete(
                f"{API}/api-keys/{key_id}", headers=registered["headers"]
            ).status_code
            == 204
        )
        assert client.get(f"{API}/api-keys", headers=registered["headers"]).json() == []

    def test_cannot_touch_another_users_key(
        self, client: TestClient, registered: dict
    ) -> None:
        key_id = client.post(
            f"{API}/api-keys", json={"name": "Mine"}, headers=registered["headers"]
        ).json()["id"]

        other = client.post(
            f"{API}/auth/register",
            json={"email": "other@example.com", "password": "secret123"},
        ).json()
        headers = {"Authorization": f"Bearer {other['tokens']['access_token']}"}

        assert client.delete(f"{API}/api-keys/{key_id}", headers=headers).status_code == 404


class TestBilling:
    def test_plans_are_public(self, client: TestClient) -> None:
        response = client.get(f"{API}/plans")
        assert response.status_code == 200
        assert {p["slug"] for p in response.json()} == {
            "free",
            "starter",
            "pro",
            "enterprise",
        }

    def test_plan_change(self, client: TestClient, registered: dict) -> None:
        response = client.post(
            f"{API}/billing/plan",
            json={"plan_slug": "starter"},
            headers=registered["headers"],
        )
        assert response.status_code == 200
        assert response.json()["plan"]["slug"] == "starter"

    def test_enterprise_requires_sales(self, client: TestClient, registered: dict) -> None:
        response = client.post(
            f"{API}/billing/plan",
            json={"plan_slug": "enterprise"},
            headers=registered["headers"],
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "contact_sales_required"


class TestUsageAndSettings:
    def test_usage_overview(self, client: TestClient, registered: dict) -> None:
        client.post(
            f"{API}/check",
            json={"phone": "+8801712345678"},
            headers=registered["headers"],
        )
        body = client.get(f"{API}/usage", headers=registered["headers"]).json()
        assert body["summary"]["today_requests"] == 1
        assert body["summary"]["quota"] == 100
        assert body["summary"]["remaining_credits"] == 99
        assert len(body["daily"]) == 30
        assert len(body["recent"]) == 1

    def test_profile_update(self, client: TestClient, registered: dict) -> None:
        response = client.patch(
            f"{API}/users/me",
            json={"full_name": "Updated Name", "company": "Acme"},
            headers=registered["headers"],
        )
        assert response.json()["full_name"] == "Updated Name"

    def test_change_password(self, client: TestClient, registered: dict) -> None:
        response = client.post(
            f"{API}/auth/change-password",
            json={"current_password": "secret123", "new_password": "brandnew123"},
            headers=registered["headers"],
        )
        assert response.status_code == 200

        assert (
            client.post(
                f"{API}/auth/login",
                json={"email": registered["email"], "password": "brandnew123"},
            ).status_code
            == 200
        )

    def test_change_password_requires_the_current_one(
        self, client: TestClient, registered: dict
    ) -> None:
        response = client.post(
            f"{API}/auth/change-password",
            json={"current_password": "wrongpass1", "new_password": "brandnew123"},
            headers=registered["headers"],
        )
        assert response.status_code == 401

    def test_delete_account(self, client: TestClient, registered: dict) -> None:
        response = client.post(
            f"{API}/users/me/delete",
            json={"password": "secret123"},
            headers=registered["headers"],
        )
        assert response.status_code == 204
        assert client.get(f"{API}/auth/me", headers=registered["headers"]).status_code == 401


class TestAdmin:
    def test_regular_users_are_refused(self, client: TestClient, registered: dict) -> None:
        response = client.get(f"{API}/admin/stats", headers=registered["headers"])
        assert response.status_code == 403

    def test_admin_can_read_stats(self, client: TestClient, registered: dict) -> None:
        from app.db.session import SessionLocal
        from app.models.user import UserRole
        from app.repositories.user import UserRepository

        with SessionLocal() as db:
            repo = UserRepository(db)
            user = repo.get_by_email(registered["email"])
            repo.update(user, role=UserRole.ADMIN)
            db.commit()

        response = client.get(f"{API}/admin/stats", headers=registered["headers"])
        assert response.status_code == 200
        assert response.json()["total_users"] >= 1


class TestErrorEnvelope:
    def test_every_error_uses_the_same_shape(self, client: TestClient) -> None:
        response = client.get(f"{API}/auth/me")
        body = response.json()
        assert body["success"] is False
        assert set(body["error"]) == {"code", "message", "details"}

    def test_health(self, client: TestClient) -> None:
        assert client.get(f"{API}/health").json()["status"] in {"ok", "degraded"}


class TestEmailCheck:
    """`POST /check/email` — the email on its own, with no phone number."""

    def test_verifies_an_email_without_a_phone(
        self, client: TestClient, registered: dict
    ) -> None:
        response = client.post(
            f"{API}/check/email",
            json={"email": "jane@acme.com"},
            headers=registered["headers"],
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["email"] == "jane@acme.com"
        assert body["email_info"]["syntax_valid"] is True
        assert body["email_info"]["deliverable"] is True
        assert body["email_info"]["status"] == "valid"
        assert body["response_time_ms"] > 0

    def test_malformed_email_is_answered_not_rejected(
        self, client: TestClient, registered: dict
    ) -> None:
        response = client.post(
            f"{API}/check/email",
            json={"email": "not-an-email"},
            headers=registered["headers"],
        )
        # The whole point: a bad address is a verdict, not a failed request.
        assert response.status_code == 200
        info = response.json()["email_info"]
        assert info["syntax_valid"] is False
        assert info["status"] == "invalid_syntax"
        assert info["reason"]

    def test_flags_a_disposable_domain(
        self, client: TestClient, registered: dict
    ) -> None:
        response = client.post(
            f"{API}/check/email",
            json={"email": "someone@mailinator.com"},
            headers=registered["headers"],
        )
        info = response.json()["email_info"]
        assert info["disposable"] is True
        assert info["status"] == "disposable"

    def test_does_not_use_up_a_request(
        self, client: TestClient, registered: dict
    ) -> None:
        stats = f"{API}/dashboard/stats"
        before = client.get(stats, headers=registered["headers"]).json()
        client.post(
            f"{API}/check/email",
            json={"email": "jane@acme.com"},
            headers=registered["headers"],
        )
        after = client.get(stats, headers=registered["headers"]).json()
        assert after["remaining_credits"] == before["remaining_credits"]

    def test_requires_authentication(self, client: TestClient) -> None:
        response = client.post(f"{API}/check/email", json={"email": "jane@acme.com"})
        assert response.status_code == 401

    def test_works_when_no_whatsapp_account_is_connected(
        self, client: TestClient, registered: dict, monkeypatch
    ) -> None:
        """The reason this route exists: an empty pool must not affect it."""
        from app.core.exceptions import ProviderError
        from app.services.providers.direct import DirectWhatsAppProvider

        def dead_pool(self, phone):
            raise ProviderError("No WhatsApp account is connected", code="no_accounts")

        monkeypatch.setattr(DirectWhatsAppProvider, "check", dead_pool)

        # The number route is down…
        assert (
            client.post(
                f"{API}/check",
                json={"phone": "+8801712345678"},
                headers=registered["headers"],
            ).status_code
            == 502
        )
        # …while the email route still answers.
        response = client.post(
            f"{API}/check/email",
            json={"email": "jane@acme.com"},
            headers=registered["headers"],
        )
        assert response.status_code == 200
        assert response.json()["email_info"]["status"] == "valid"


class TestFailedLookupBilling:
    def test_a_provider_failure_does_not_use_up_a_request(
        self, client: TestClient, registered: dict, monkeypatch
    ) -> None:
        """An outage is ours, not the caller's — it must not cost them credit."""
        from app.core.exceptions import ProviderError
        from app.services.providers.direct import DirectWhatsAppProvider

        def dead_pool(self, phone):
            raise ProviderError("No WhatsApp account is connected", code="no_accounts")

        monkeypatch.setattr(DirectWhatsAppProvider, "check", dead_pool)

        stats = f"{API}/dashboard/stats"
        before = client.get(stats, headers=registered["headers"]).json()
        response = client.post(
            f"{API}/check",
            json={"phone": "+8801712345678"},
            headers=registered["headers"],
        )
        assert response.status_code == 502

        after = client.get(stats, headers=registered["headers"]).json()
        assert after["remaining_credits"] == before["remaining_credits"]
