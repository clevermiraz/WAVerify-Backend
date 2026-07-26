"""Resolves the configured provider once per process."""

from functools import lru_cache

from app.services.providers.base import WhatsAppProvider
from app.services.providers.direct import DirectWhatsAppProvider


@lru_cache
def get_provider() -> WhatsAppProvider:
    return DirectWhatsAppProvider()


def shutdown_provider() -> None:
    if get_provider.cache_info().currsize:
        get_provider().close()
        get_provider.cache_clear()
