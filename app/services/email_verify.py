"""Email address verification: syntax, then whether the domain accepts mail.

This is a verdict, not enrichment. Where `GravatarService` answers "is there a
public profile behind this address", this answers "is this address usable at
all", so a broken address is a result the caller reads off `EmailInfo` rather
than a 422 that fails the whole check.

Deliberately stops at the domain. Proving one specific mailbox exists means
opening an SMTP session and issuing `RCPT TO`, which providers treat as
address harvesting and answer with a blocklisting — so `deliverable` means
"the domain publishes a mail server", and nothing stronger is claimed.

DNS resolution is the only part that can be slow, so it is bounded by
`EMAIL_VERIFY_DNS_TIMEOUT_SECONDS` and the whole verdict is cached in Redis.
"""

import json

import dns.exception
import dns.resolver
import redis
from email_validator import EmailNotValidError, validate_email

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.check import EmailInfo
from app.utils.email_domains import (
    DISPOSABLE_DOMAINS,
    FREE_PROVIDER_DOMAINS,
    ROLE_LOCAL_PARTS,
)

logger = get_logger(__name__)

_CACHE_PREFIX = "emailverify:"


class EmailVerificationService:
    def __init__(self, redis_client: redis.Redis | None = None) -> None:
        self.redis = redis_client

    def verify(self, email: str) -> EmailInfo | None:
        """Verify one address. ``None`` only when there is nothing to verify.

        Unlike the Gravatar side-channel, a failure here still produces an
        `EmailInfo` — with `status: unknown` — because the caller asked a
        question and deserves an answer, even an inconclusive one.
        """
        if not settings.EMAIL_VERIFY_ENABLED or not email or not email.strip():
            return None

        cached = self._read_cache(email)
        if cached is not None:
            return EmailInfo(**cached)

        info = self._verify_uncached(email)
        self._write_cache(email, info)
        return info

    # --- Checks ----------------------------------------------------------

    def _verify_uncached(self, email: str) -> EmailInfo:
        raw = email.strip()

        try:
            # deliverability is checked separately below so the DNS timeout and
            # the "unknown" outcome stay under our control rather than becoming
            # an EmailNotValidError indistinguishable from a typo.
            parsed = validate_email(raw, check_deliverability=False)
        except EmailNotValidError as exc:
            return EmailInfo(
                email=raw.lower(),
                syntax_valid=False,
                domain=raw.rpartition("@")[2].lower() or None,
                status="invalid_syntax",
                reason=str(exc),
            )

        normalised = parsed.normalized.lower()
        domain = parsed.domain.lower()
        local_part = parsed.local_part.lower() if parsed.local_part else ""

        disposable = domain in DISPOSABLE_DOMAINS
        info = EmailInfo(
            email=normalised,
            syntax_valid=True,
            domain=domain,
            disposable=disposable,
            role_account=local_part in ROLE_LOCAL_PARTS,
            free_provider=domain in FREE_PROVIDER_DOMAINS,
            status="valid",
        )

        deliverable, mx_hosts, dns_status, reason = self._resolve_mail_hosts(domain)
        info.deliverable = deliverable
        info.mx_hosts = mx_hosts

        # A throwaway domain outranks the DNS answer: it resolves and delivers,
        # which is precisely what makes it worth flagging over a plain `valid`.
        if disposable:
            info.status = "disposable"
            info.reason = "The domain is a known throwaway-inbox service."
        elif dns_status != "valid":
            info.status = dns_status
            info.reason = reason

        return info

    def _resolve_mail_hosts(
        self, domain: str
    ) -> tuple[bool | None, list[str], str, str | None]:
        """Look up where `domain` receives mail.

        Returns `(deliverable, mx_hosts, status, reason)`. `deliverable` is
        tri-state: None means the question could not be answered, which must
        not be reported as a failed address.
        """
        if not settings.EMAIL_VERIFY_CHECK_MX:
            return None, [], "unknown", "Domain checking is turned off on this server."

        resolver = dns.resolver.Resolver()
        resolver.lifetime = settings.EMAIL_VERIFY_DNS_TIMEOUT_SECONDS
        resolver.timeout = settings.EMAIL_VERIFY_DNS_TIMEOUT_SECONDS

        try:
            answers = resolver.resolve(domain, "MX")
        except dns.resolver.NXDOMAIN:
            return False, [], "domain_not_found", "The domain does not exist."
        except dns.resolver.NoAnswer:
            # No MX record is not the end of it: RFC 5321 §5.1 says a domain
            # with an address record accepts mail on that host instead.
            return self._implicit_mx(resolver, domain)
        except (dns.exception.DNSException, OSError) as exc:
            logger.warning("email_verify.dns_failed", domain=domain, error=str(exc))
            return None, [], "unknown", "The domain check could not be completed."

        hosts = [
            str(record.exchange).rstrip(".")
            for record in sorted(answers, key=lambda r: r.preference)
            # A single "." target is the null MX of RFC 7505 — an explicit
            # "this domain never receives mail".
            if str(record.exchange).rstrip(".")
        ]
        if not hosts:
            return False, [], "no_mail_server", "The domain refuses all mail."
        return True, hosts, "valid", None

    @staticmethod
    def _implicit_mx(
        resolver: dns.resolver.Resolver, domain: str
    ) -> tuple[bool | None, list[str], str, str | None]:
        for record_type in ("A", "AAAA"):
            try:
                resolver.resolve(domain, record_type)
            except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
                continue
            except (dns.exception.DNSException, OSError) as exc:
                logger.warning(
                    "email_verify.dns_failed", domain=domain, error=str(exc)
                )
                return None, [], "unknown", "The domain check could not be completed."
            return True, [domain], "valid", None
        return False, [], "no_mail_server", "The domain has no mail server."

    # --- Cache -----------------------------------------------------------

    def _cache_key(self, email: str) -> str:
        return f"{_CACHE_PREFIX}{email.strip().lower()}"

    def _read_cache(self, email: str) -> dict | None:
        if self.redis is None or settings.EMAIL_VERIFY_CACHE_TTL_SECONDS <= 0:
            return None
        try:
            raw = self.redis.get(self._cache_key(email))
        except redis.RedisError as exc:
            logger.warning("email_verify.cache_unavailable", error=str(exc))
            return None
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def _write_cache(self, email: str, info: EmailInfo) -> None:
        if self.redis is None or settings.EMAIL_VERIFY_CACHE_TTL_SECONDS <= 0:
            return
        # An inconclusive DNS answer is not worth remembering — caching it
        # would keep returning "unknown" long after the resolver recovered.
        if info.status == "unknown":
            return
        try:
            self.redis.setex(
                self._cache_key(email),
                settings.EMAIL_VERIFY_CACHE_TTL_SECONDS,
                json.dumps(info.model_dump(mode="json")),
            )
        except redis.RedisError as exc:
            logger.warning("email_verify.cache_write_failed", error=str(exc))
