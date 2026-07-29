"""Direct WhatsApp Provider utilizing neonize with multi-account pooling."""

import os
import random
import re
import threading
import time
import uuid
from typing import Any

from neonize.client import NewClient
from neonize.events import ConnectedEv, LoggedOutEv, PairStatusEv

from app.core.config import settings
from app.core.exceptions import ProviderError
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.models.whatsapp_account import WhatsAppAccount
from app.services.providers.base import ProviderResult, WhatsAppProvider
from app.utils.phone import ParsedPhone, mask_phone

logger = get_logger(__name__)


def normalize(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 7:
        raise ValueError(f"not a usable phone number: {phone!r}")
    return "+" + digits


def _jitter(lo: float, hi: float) -> None:
    """Sleep a random anti-ban delay. A non-positive max disables it."""
    if hi <= 0:
        return
    time.sleep(random.uniform(max(0.0, lo), hi))


class DirectWhatsAppClient:
    """Manages a single neonize WhatsApp connection."""
    
    def __init__(self, account_id: uuid.UUID):
        self.account_id = account_id
        os.makedirs("data", exist_ok=True)
        self.session_path = f"data/wa-session-{account_id}.sqlite3"
        self._lock = threading.Lock()
        
        self._enrich = settings.PROVIDER_ENRICH_PROFILE
        self.status = "initializing"
        self.qr_data = None
        self.paired_number = None

        self._client = NewClient(self.session_path)
        
        self._client.qr(self._on_qr)
        self._client.event(PairStatusEv)(self._on_pair)
        self._client.event(ConnectedEv)(self._on_connected)
        self._client.event(LoggedOutEv)(self._on_logged_out)

        # Start connection in background
        threading.Thread(target=self._start_connection, daemon=True).start()

    def _start_connection(self) -> None:
        try:
            logger.info("provider.direct_client", action="starting", account_id=str(self.account_id))
            self._client.connect()
        except Exception as exc:
            logger.error("provider.direct_client", action="init_error", account_id=str(self.account_id), error=str(exc))
            self.status = "error"
            self._update_db_status("error")

    def _update_db_status(self, status: str, phone: str | None = None) -> None:
        with SessionLocal() as db:
            account = db.query(WhatsAppAccount).filter(WhatsAppAccount.id == self.account_id).first()
            if account:
                account.status = status
                if phone:
                    account.phone_number = phone
                db.commit()

    def _on_qr(self, client: NewClient, data: bytes) -> None:
        self.qr_data = data.decode()
        self.status = "pairing"
        self._update_db_status("pairing")
        logger.info("provider.direct_client", action="qr_generated", account_id=str(self.account_id))

    def _on_pair(self, client: NewClient, event: PairStatusEv) -> None:
        self.paired_number = f"+{event.ID.User}"
        self.status = "connected"
        self.qr_data = None
        self._update_db_status("connected", phone=self.paired_number)
        logger.info("provider.direct_client", action="paired", account_id=str(self.account_id), number=self.paired_number)

    def _on_connected(self, client: NewClient, event: ConnectedEv) -> None:
        self.status = "connected"
        self.qr_data = None
        self._update_db_status("connected")
        logger.info("provider.direct_client", action="connected", account_id=str(self.account_id))

    def _on_logged_out(self, client: NewClient, event: LoggedOutEv) -> None:
        self.status = "disconnected"
        self.qr_data = None
        self.paired_number = None
        self._update_db_status("disconnected", phone=None)
        logger.warning("provider.direct_client", action="logged_out", account_id=str(self.account_id))
        
    def get_status(self) -> dict[str, Any]:
        return {
            "id": str(self.account_id),
            "status": self.status,
            "qr_data": self.qr_data,
            "paired_number": self.paired_number,
        }

    def check(self, phone: str) -> dict[str, Any]:
        number = normalize(phone)
        try:
            with self._lock:
                # Humanized delay before the lookup. Inside the lock so queued
                # requests wait their turn instead of firing in a burst. Tune
                # via PROVIDER_LOOKUP_DELAY_* — smaller is faster, riskier.
                _jitter(
                    settings.PROVIDER_LOOKUP_DELAY_MIN,
                    settings.PROVIDER_LOOKUP_DELAY_MAX,
                )
                responses = self._client.is_on_whatsapp(number)
            
            found = {}
            for response in responses:
                for key in (re.sub(r"\D", "", response.Query), response.JID.User):
                    if key:
                        found.setdefault(key, response)
                        
            hit = found.get(re.sub(r"\D", "", number))
            if hit is None or not hit.IsIn:
                return {"phone": number, "exists": False}
            return self._payload(number, hit)
        except Exception as exc:
            return {"phone": number, "exists": False, "error": str(exc)}

    def _payload(self, phone: str, result: Any) -> dict[str, Any]:
        verified_name = result.VerifiedName.Details.verifiedName or None
        payload: dict[str, Any] = {
            "phone": phone,
            "exists": True,
            "jid": f"{result.JID.User}@{result.JID.Server}",
            "business": bool(verified_name),
            "display_name": verified_name,
            "name_source": "business_verified" if verified_name else None,
            "about": None,
            "profile_photo": None,
            "profile_photo_id": None,
            "device_count": None,
        }
        if self._enrich:
            payload.update(self._profile(result.JID, have_name=bool(verified_name)))
        return payload

    def _profile(self, jid: Any, *, have_name: bool) -> dict[str, Any]:
        out: dict[str, Any] = {}
        # Use the JID whatsmeow handed back verbatim. Rebuilding it as
        # "<user>@s.whatsapp.net" silently breaks every number that resolves to
        # a LID, which is what made about/photo come back null for some numbers.
        target = jid

        try:
            with self._lock:
                # Small jitter between enrichment calls. Tune via
                # PROVIDER_ENRICH_DELAY_*.
                _jitter(
                    settings.PROVIDER_ENRICH_DELAY_MIN,
                    settings.PROVIDER_ENRICH_DELAY_MAX,
                )
                infos = self._client.get_user_info(target)
            for info in infos:
                out["about"] = info.UserInfo.Status or None
                # get_user_info carries the verified name too, and it is
                # populated in cases where is_on_whatsapp left it empty.
                if not have_name:
                    business_name = info.UserInfo.VerifiedName.Details.verifiedName or None
                    if business_name:
                        out["display_name"] = business_name
                        out["name_source"] = "business_verified"
                        out["business"] = True
                        have_name = True
                if info.UserInfo.PictureID:
                    out["profile_photo_id"] = info.UserInfo.PictureID
                break
        except Exception as exc:
            logger.warning(
                "provider.direct_user_info_failed", jid=jid.User, error=str(exc)
            )

        if not have_name:
            out.update(self._contact_name(target))

        try:
            with self._lock:
                _jitter(
                    settings.PROVIDER_ENRICH_DELAY_MIN,
                    settings.PROVIDER_ENRICH_DELAY_MAX,
                )
                picture = self._client.get_profile_picture(target)
            out["profile_photo"] = picture.URL or None
            if picture.ID:
                out["profile_photo_id"] = picture.ID
        except Exception as exc:
            # A hidden profile photo also lands here, so this is expected noise
            # as much as a real fault — log it, do not fail the lookup.
            logger.warning(
                "provider.direct_profile_photo_failed", jid=jid.User, error=str(exc)
            )

        try:
            with self._lock:
                _jitter(
                    settings.PROVIDER_ENRICH_DELAY_MIN,
                    settings.PROVIDER_ENRICH_DELAY_MAX,
                )
                devices = self._client.get_user_devices(target)
            out["device_count"] = len(devices)
        except Exception as exc:
            logger.warning(
                "provider.direct_devices_failed", jid=jid.User, error=str(exc)
            )

        return out

    def _contact_name(self, target: Any) -> dict[str, Any]:
        """Last resort for a personal name.

        Only ever returns something when this paired account already knows the
        contact — whatsmeow learns a push name from an incoming message or from
        synced app state, never from a cold lookup.
        """
        try:
            contact = self._client.contact.get_contact(target)
        except Exception as exc:
            logger.warning(
                "provider.direct_contact_failed", jid=target.User, error=str(exc)
            )
            return {}

        if not contact.Found:
            return {}
        for source, value in (
            ("business_name", contact.BusinessName),
            ("contact_name", contact.FullName),
            ("push_name", contact.PushName),
        ):
            if value:
                return {"display_name": value, "name_source": source}
        return {}

    def close(self) -> None:
        try:  # noqa: SIM105
            self._client.stop()
        except Exception:
            pass


class DirectWhatsAppProvider(WhatsAppProvider):
    name = "direct"

    def __init__(self) -> None:
        self._clients: dict[uuid.UUID, DirectWhatsAppClient] = {}
        self._lock = threading.Lock()
        self._rr_index = 0
        
        # Load all accounts from DB on startup
        try:
            with SessionLocal() as db:
                accounts = db.query(WhatsAppAccount).all()
                for account in accounts:
                    self._start_client(account.id)
        except Exception as exc:
            logger.error("provider.direct", action="db_load_error", error=str(exc))

    def _start_client(self, account_id: uuid.UUID) -> DirectWhatsAppClient:
        with self._lock:
            if account_id in self._clients:
                self._clients[account_id].close()
            client = DirectWhatsAppClient(account_id)
            self._clients[account_id] = client
            return client
            
    def add_account(self, account_id: uuid.UUID) -> None:
        self._start_client(account_id)
        
    def remove_account(self, account_id: uuid.UUID) -> None:
        with self._lock:
            client = self._clients.pop(account_id, None)
            if client:
                client.close()
            # Also remove sqlite file if possible
            try:  # noqa: SIM105
                os.remove(f"data/wa-session-{account_id}.sqlite3")
            except OSError:
                pass

    def reverify_account(self, account_id: uuid.UUID) -> None:
        self._start_client(account_id)
        
    def get_account_status(self, account_id: uuid.UUID) -> dict[str, Any] | None:
        client = self._clients.get(account_id)
        if client:
            return client.get_status()
        return None
        
    def get_all_statuses(self) -> list[dict[str, Any]]:
        return [client.get_status() for client in self._clients.values()]

    def _get_available_client(self) -> DirectWhatsAppClient | None:
        with self._lock:
            # Gather all connected clients
            connected = [client for client in self._clients.values()
                         if client.status == "connected"]
            if not connected:
                return None

            # Load balancing: Round-Robin across all connected accounts.
            # This prevents hammering a single account and drastically reduces ban rates.
            self._rr_index = (self._rr_index + 1) % len(connected)
            return connected[self._rr_index]

    def check(self, phone: ParsedPhone) -> ProviderResult:
        client = self._get_available_client()
        if not client:
            raise ProviderError("No connected WhatsApp accounts available in the pool", code="no_accounts")
            
        try:
            payload = client.check(phone.e164)
            
            # Update usage stats
            with SessionLocal() as db:
                account = db.query(WhatsAppAccount).filter(WhatsAppAccount.id == client.account_id).first()
                if account:
                    account.total_lookups_performed += 1
                    account.lookups_this_month += 1
                    db.commit()
                    
        except Exception as exc:
            logger.warning("provider.direct_error", error=str(exc), phone=mask_phone(phone.e164))
            raise ProviderError() from exc

        if payload.get("error"):
            logger.warning("provider.direct_lookup_error", error=payload["error"], phone=mask_phone(phone.e164))
            raise ProviderError(payload["error"])

        return self._to_result(payload)

    @staticmethod
    def _to_result(payload: dict[str, Any]) -> ProviderResult:
        exists = bool(payload.get("exists"))
        if not exists:
            return ProviderResult(exists=False)
        return ProviderResult(
            exists=True,
            display_name=payload.get("display_name"),
            name_source=payload.get("name_source"),
            about=payload.get("about"),
            is_business=bool(payload.get("business")),
            profile_photo_url=payload.get("profile_photo"),
            profile_photo_id=payload.get("profile_photo_id"),
            device_count=payload.get("device_count"),
        )

    def close(self) -> None:
        with self._lock:
            for client in self._clients.values():
                client.close()
            self._clients.clear()
