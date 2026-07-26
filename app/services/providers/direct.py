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
from neonize.utils import build_jid

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


class DirectWhatsAppClient:
    """Manages a single neonize WhatsApp connection."""
    
    def __init__(self, account_id: uuid.UUID):
        self.account_id = account_id
        os.makedirs("data", exist_ok=True)
        self.session_path = f"data/wa-session-{account_id}.sqlite3"
        self._enrich = True
        self._lock = threading.Lock()
        
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
                # Humanized delay: Random wait between 1 to 3 seconds before checking.
                # This MUST be inside the lock so concurrent requests wait in a queue 
                # rather than firing simultaneously after the sleep.
                time.sleep(random.uniform(1.0, 3.0))
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
        payload: dict[str, Any] = {
            "phone": phone,
            "exists": True,
            "jid": f"{result.JID.User}@{result.JID.Server}",
            "business": bool(result.VerifiedName.Details.verifiedName),
            "display_name": result.VerifiedName.Details.verifiedName or None,
            "about": None,
            "profile_photo": None,
        }
        if self._enrich:
            payload.update(self._profile(result.JID))
        return payload

    def _profile(self, jid: Any) -> dict[str, Any]:
        out: dict[str, Any] = {}
        target = build_jid(jid.User)

        try:
            with self._lock:
                # Add micro-delays (jitter) to simulate human speeds when querying profile data
                time.sleep(random.uniform(0.5, 1.5))
                infos = self._client.get_user_info(target)
            for info in infos:
                out["about"] = info.UserInfo.Status or None
                break
        except Exception:
            pass

        try:
            with self._lock:
                time.sleep(random.uniform(0.5, 1.5))
                picture = self._client.get_profile_picture(target)
            out["profile_photo"] = picture.URL or None
        except Exception:
            pass

        return out

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
            about=payload.get("about"),
            is_business=bool(payload.get("business")),
            profile_photo_url=payload.get("profile_photo"),
        )

    def close(self) -> None:
        with self._lock:
            for client in self._clients.values():
                client.close()
            self._clients.clear()
