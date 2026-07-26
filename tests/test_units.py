"""Unit tests for pure helpers — no database required."""

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
