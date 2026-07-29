"""Unit tests for pure helpers — no database required."""

import dns.resolver
import pytest

from app.core.exceptions import InvalidTokenError, ValidationError
from app.core.security import (
    TokenType,
    create_access_token,
    create_password_reset_token,
    decode_token,
    generate_api_key,
    hash_api_key,
    hash_password,
    password_reset_fingerprint,
    verify_password,
)
from app.services.email_verify import EmailVerificationService
from app.utils.phone import mask_phone, parse_phone


class TestPhoneParsing:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("+8801712345678", "+8801712345678"),
            ("+880 1712-345678", "+8801712345678"),
            ("8801712345678", "+8801712345678"),
            ("+1 415 555 2671", "+14155552671"),
        ],
    )
    def test_normalises_to_e164(self, raw: str, expected: str) -> None:
        assert parse_phone(raw).e164 == expected

    @pytest.mark.parametrize("raw", ["12345", "not-a-number", "+999999999999999", ""])
    def test_rejects_invalid(self, raw: str) -> None:
        with pytest.raises(ValidationError):
            parse_phone(raw)

    def test_extracts_country_code(self) -> None:
        assert parse_phone("+8801712345678").country_code == "+880"

    def test_mask_hides_subscriber_digits(self) -> None:
        masked = mask_phone("+8801712345678")
        assert masked.startswith("+8801") and masked.endswith("78")
        assert "1712345" not in masked


class TestPasswords:
    def test_round_trip(self) -> None:
        hashed = hash_password("secret123")
        assert hashed != "secret123"
        assert verify_password("secret123", hashed)
        assert not verify_password("secret124", hashed)

    def test_rejects_over_bcrypt_limit(self) -> None:
        with pytest.raises(ValueError):
            hash_password("a" * 73)

    def test_malformed_hash_is_a_failed_login_not_a_crash(self) -> None:
        assert verify_password("secret123", "garbage") is False

    def test_salted(self) -> None:
        assert hash_password("secret123") != hash_password("secret123")


class TestTokens:
    def test_access_token_round_trip(self) -> None:
        token = create_access_token("user-1", role="user")
        payload = decode_token(token, TokenType.ACCESS)
        assert payload["sub"] == "user-1"
        assert payload["role"] == "user"

    def test_token_type_confusion_is_rejected(self) -> None:
        token = create_access_token("user-1")
        with pytest.raises(InvalidTokenError):
            decode_token(token, TokenType.REFRESH)

    def test_tampered_token_is_rejected(self) -> None:
        token = create_access_token("user-1")
        with pytest.raises(InvalidTokenError):
            decode_token(token + "x", TokenType.ACCESS)

    def test_reset_token_is_bound_to_the_current_password(self) -> None:
        old_hash = hash_password("secret123")
        token = create_password_reset_token("user-1", old_hash)
        payload = decode_token(token, TokenType.PASSWORD_RESET)

        assert payload["fp"] == password_reset_fingerprint(old_hash)
        # After the password changes the fingerprint no longer matches, which
        # is what makes the link single-use.
        assert payload["fp"] != password_reset_fingerprint(hash_password("newer123"))


class TestApiKeys:
    def test_hash_matches_and_prefix_is_a_real_prefix(self) -> None:
        key, hashed, prefix = generate_api_key()
        assert hash_api_key(key) == hashed
        assert key.startswith(prefix)
        assert key.startswith("wav_")

    def test_keys_are_unique(self) -> None:
        assert len({generate_api_key()[0] for _ in range(50)}) == 50


class _FakeMX:
    def __init__(self, preference: int, exchange: str) -> None:
        self.preference = preference
        self.exchange = exchange

    def __str__(self) -> str:
        return self.exchange


class _FakeResolver:
    """Stands in for dns.resolver.Resolver so no test touches the network.

    `answers` maps a record type to either a list of records or an exception
    class to raise, which is how the real resolver reports "no such domain"
    and "no records of this type".
    """

    answers: dict = {}

    def __init__(self) -> None:
        self.lifetime = None
        self.timeout = None

    def resolve(self, domain: str, record_type: str):
        outcome = self.answers.get(record_type, dns.resolver.NoAnswer)
        if isinstance(outcome, type) and issubclass(outcome, Exception):
            raise outcome()
        return outcome


@pytest.fixture
def fake_dns(monkeypatch):
    def _install(**answers):
        resolver = type("_Resolver", (_FakeResolver,), {"answers": answers})
        monkeypatch.setattr("dns.resolver.Resolver", resolver)

    return _install


class TestEmailVerification:
    service = EmailVerificationService()

    def test_rejects_malformed_without_raising(self) -> None:
        info = self.service.verify("not-an-email")

        # The whole point of the change: a bad address is a verdict, not a 422.
        assert info is not None
        assert info.syntax_valid is False
        assert info.status == "invalid_syntax"
        assert info.reason

    def test_accepts_a_domain_with_mx(self, fake_dns) -> None:
        fake_dns(MX=[_FakeMX(20, "alt.acme.com."), _FakeMX(10, "mx.acme.com.")])
        info = self.service.verify(" Jane@ACME.com ")

        assert info.syntax_valid is True
        assert info.email == "jane@acme.com"
        assert info.domain == "acme.com"
        assert info.deliverable is True
        # Sorted by preference, so the primary is usable as mx_hosts[0].
        assert info.mx_hosts == ["mx.acme.com", "alt.acme.com"]
        assert info.status == "valid"

    def test_missing_domain_is_undeliverable(self, fake_dns) -> None:
        fake_dns(MX=dns.resolver.NXDOMAIN)
        info = self.service.verify("jane@acme.com")

        assert info.deliverable is False
        assert info.status == "domain_not_found"

    def test_falls_back_to_an_address_record(self, fake_dns) -> None:
        # RFC 5321 §5.1: no MX but an A record still means "send mail here".
        fake_dns(MX=dns.resolver.NoAnswer, A=["203.0.113.10"])
        info = self.service.verify("jane@acme.com")

        assert info.deliverable is True
        assert info.mx_hosts == ["acme.com"]
        assert info.status == "valid"

    def test_no_mx_and_no_address_record(self, fake_dns) -> None:
        fake_dns(MX=dns.resolver.NoAnswer, A=dns.resolver.NoAnswer,
                 AAAA=dns.resolver.NoAnswer)
        info = self.service.verify("jane@acme.com")

        assert info.deliverable is False
        assert info.status == "no_mail_server"

    def test_null_mx_refuses_mail(self, fake_dns) -> None:
        # RFC 7505: a single "." target is an explicit "never send here".
        fake_dns(MX=[_FakeMX(0, ".")])
        info = self.service.verify("jane@acme.com")

        assert info.deliverable is False
        assert info.status == "no_mail_server"

    def test_dns_failure_is_unknown_not_undeliverable(self, fake_dns) -> None:
        fake_dns(MX=dns.resolver.LifetimeTimeout)
        info = self.service.verify("jane@acme.com")

        # A resolver problem is ours, not the address's — it must never be
        # reported as a bad email.
        assert info.deliverable is None
        assert info.status == "unknown"
        assert info.syntax_valid is True

    def test_disposable_outranks_a_working_domain(self, fake_dns) -> None:
        fake_dns(MX=[_FakeMX(10, "mail.mailinator.com.")])
        info = self.service.verify("someone@mailinator.com")

        assert info.deliverable is True
        assert info.disposable is True
        assert info.status == "disposable"

    def test_flags_role_and_free_provider(self, fake_dns) -> None:
        fake_dns(MX=[_FakeMX(10, "gmail-smtp-in.l.google.com.")])
        info = self.service.verify("support@gmail.com")

        assert info.role_account is True
        assert info.free_provider is True
        # Neither is a fault, so the verdict stays valid.
        assert info.status == "valid"

    def test_personal_address_is_not_a_role_account(self, fake_dns) -> None:
        fake_dns(MX=[_FakeMX(10, "mx.acme.com.")])
        info = self.service.verify("jane.roe@acme.com")

        assert info.role_account is False
        assert info.free_provider is False

    def test_returns_nothing_when_there_is_no_email(self) -> None:
        assert self.service.verify("") is None
        assert self.service.verify("   ") is None
