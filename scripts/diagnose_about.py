"""Show exactly what WhatsApp returns for one number's profile.

`about` coming back null on /check has three causes that the API response
cannot tell apart: enrichment is switched off, the `get_user_info` call is
failing, or WhatsApp is withholding the status. This prints the raw reply so
you can see which one it is.

    python -m scripts.diagnose_about +8801712345678

Needs a paired, connected account in the pool — the same one /check uses — so
run it against the environment where the problem shows up.
"""

import argparse
import sys
import time

from app.core.config import settings
from app.core.logging import configure_logging
from app.services.providers.direct import DirectWhatsAppProvider, normalize


def _wait_for_client(provider: DirectWhatsAppProvider, timeout: float):
    """Block until one pooled account reports connected, or give up."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        client = provider._get_available_client()  # noqa: SLF001 — diagnostic
        if client is not None:
            return client
        time.sleep(1.0)
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phone", help="Number to inspect, in international format")
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Seconds to wait for an account to connect (default: 60)",
    )
    args = parser.parse_args()

    configure_logging()

    print(f"PROVIDER_ENRICH_PROFILE = {settings.PROVIDER_ENRICH_PROFILE}")
    if not settings.PROVIDER_ENRICH_PROFILE:
        print(
            "\n  ^ This is off, so /check never asks for about, photo or devices.\n"
            "    That alone explains a permanently null `about` while business\n"
            "    names keep working — they come from the existence check itself.\n"
            "    Set PROVIDER_ENRICH_PROFILE=true to re-enable enrichment.\n"
            "    Continuing anyway so you can see the raw reply.\n"
        )

    provider = DirectWhatsAppProvider()
    try:
        client = _wait_for_client(provider, args.timeout)
        if client is None:
            print("No connected WhatsApp account in the pool — nothing to ask with.")
            sys.exit(1)

        number = normalize(args.phone)
        print(f"Using account {client.account_id} ({client.paired_number})")
        print(f"Looking up {number}\n")

        responses = client._client.is_on_whatsapp(number)  # noqa: SLF001
        print(f"is_on_whatsapp -> {len(responses)} response(s)")
        hit = None
        for response in responses:
            print(
                f"  Query={response.Query!r} "
                f"JID={response.JID.User}@{response.JID.Server} "
                f"IsIn={response.IsIn} "
                f"VerifiedName={response.VerifiedName.Details.verifiedName!r}"
            )
            if response.IsIn:
                hit = response

        if hit is None:
            print("\nNumber is not on WhatsApp — there is no profile to fetch.")
            return

        infos = client._client.get_user_info(hit.JID)  # noqa: SLF001
        print(f"\nget_user_info -> {len(infos)} entry/entries")
        if not len(infos):
            print(
                "  Empty. WhatsApp resolved the number but returned no profile\n"
                "  record for it, so `about` can only be null."
            )
        for info in infos:
            status = info.UserInfo.Status
            print(f"  JID       = {info.JID.User}@{info.JID.Server}")
            print(f"  Status    = {status!r}  (this is `about`)")
            print(f"  PictureID = {info.UserInfo.PictureID!r}")
            print(f"  Devices   = {len(info.UserInfo.Devices)}")
            if not status:
                print(
                    "  -> Status is empty. The call worked; WhatsApp withheld the\n"
                    "     about. Either the account hides it, or this pooled\n"
                    "     account is not trusted enough to be shown it."
                )
    finally:
        provider.close()


if __name__ == "__main__":
    main()
