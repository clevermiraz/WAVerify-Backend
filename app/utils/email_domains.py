"""Static domain and local-part lists used to classify an email address.

Offline on purpose: these are reputation signals, not lookups, so they must
never add latency or a third-party dependency to a check. The lists are
deliberately short and high-confidence — a domain here should be one almost
nobody uses for a real, durable mailbox. Missing entries only cost us a
`disposable: false`, so under-listing is the safe direction to err in.
"""

# Throwaway inbox providers. Their mail is deliverable, which is exactly why
# the flag matters: MX alone would call these addresses good.
DISPOSABLE_DOMAINS = frozenset(
    {
        "0-mail.com",
        "10minutemail.com",
        "10minutemail.net",
        "20minutemail.com",
        "33mail.com",
        "anonbox.net",
        "byom.de",
        "dispostable.com",
        "dropmail.me",
        "e4ward.com",
        "emailondeck.com",
        "fakeinbox.com",
        "fakemailgenerator.com",
        "getairmail.com",
        "getnada.com",
        "guerrillamail.biz",
        "guerrillamail.com",
        "guerrillamail.de",
        "guerrillamail.info",
        "guerrillamail.net",
        "guerrillamail.org",
        "guerrillamailblock.com",
        "harakirimail.com",
        "inboxbear.com",
        "incognitomail.com",
        "jetable.org",
        "mailcatch.com",
        "maildrop.cc",
        "mailinator.com",
        "mailinator.net",
        "mailnesia.com",
        "mailsac.com",
        "mintemail.com",
        "mohmal.com",
        "moakt.com",
        "mytemp.email",
        "nowmymail.com",
        "sharklasers.com",
        "spam4.me",
        "spamgourmet.com",
        "spambox.us",
        "temp-mail.io",
        "temp-mail.org",
        "tempail.com",
        "tempinbox.com",
        "tempmail.dev",
        "tempmail.plus",
        "tempmailo.com",
        "throwawaymail.com",
        "trashmail.com",
        "trashmail.de",
        "trashmail.me",
        "trbvm.com",
        "wegwerfmail.de",
        "yopmail.com",
        "yopmail.fr",
        "yopmail.net",
    }
)

# Consumer mailbox providers. Not a negative signal on its own — most people
# have one — but it tells a caller the address is not a company address.
FREE_PROVIDER_DOMAINS = frozenset(
    {
        "aol.com",
        "gmail.com",
        "googlemail.com",
        "gmx.com",
        "gmx.de",
        "gmx.net",
        "hotmail.co.uk",
        "hotmail.com",
        "hotmail.fr",
        "icloud.com",
        "live.com",
        "live.co.uk",
        "mail.com",
        "mail.ru",
        "me.com",
        "msn.com",
        "outlook.com",
        "outlook.co.uk",
        "pm.me",
        "proton.me",
        "protonmail.com",
        "qq.com",
        "rediffmail.com",
        "tutanota.com",
        "web.de",
        "yahoo.co.in",
        "yahoo.co.uk",
        "yahoo.com",
        "yahoo.fr",
        "yandex.com",
        "yandex.ru",
        "zoho.com",
    }
)

# Shared or automated mailboxes. Mail reaches them, but there is no single
# person behind the address — worth surfacing before anyone treats one as a
# personal contact.
ROLE_LOCAL_PARTS = frozenset(
    {
        "abuse",
        "admin",
        "administrator",
        "billing",
        "careers",
        "compliance",
        "contact",
        "enquiries",
        "enquiry",
        "feedback",
        "help",
        "helpdesk",
        "hello",
        "hostmaster",
        "hr",
        "info",
        "inquiries",
        "it",
        "jobs",
        "legal",
        "mail",
        "marketing",
        "no-reply",
        "noc",
        "noreply",
        "office",
        "postmaster",
        "privacy",
        "root",
        "sales",
        "security",
        "support",
        "sysadmin",
        "team",
        "webmaster",
    }
)
