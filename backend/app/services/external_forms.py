from __future__ import annotations

from urllib.parse import urlparse

PROVIDER_HOSTS: dict[str, frozenset[str]] = {
    "google": frozenset({"docs.google.com"}),
    "microsoft": frozenset({"forms.office.com"}),
}
PROVIDER_LABELS: dict[str, str] = {
    "google": "Google Forms",
    "microsoft": "Microsoft Forms",
}


def detect_provider(url: str) -> str | None:
    """Return the supported forms provider for a URL, if any."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    for provider, hosts in PROVIDER_HOSTS.items():
        if host in hosts:
            return provider
    return None


def normalize_form_link(
    url: str | None, provider: str | None = None
) -> tuple[str | None, str | None]:
    """Validate and normalize a published Google/Microsoft Forms link.

    Returns a ``(url, provider)`` pair. Both values are ``None`` when no link
    was supplied. A invalid link raises ``ValueError`` with a user-facing
    message.
    """
    value = (url or "").strip()
    if not value:
        return None, None

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Use a full https link to the published form.")
    if not parsed.netloc:
        raise ValueError("Enter a valid form link.")

    detected = detect_provider(value)
    if detected is None:
        raise ValueError(
            "Only published Google Forms and Microsoft Forms links are supported."
        )
    if provider and provider != detected:
        raise ValueError("The form link does not match the selected provider.")

    if detected == "google" and "/forms/" not in parsed.path.lower():
        raise ValueError("Enter a published Google Forms link.")
    if detected == "microsoft" and not parsed.path.strip("/"):
        raise ValueError("Enter a published Microsoft Forms link.")

    return value, detected


def provider_label(provider: str | None) -> str:
    return PROVIDER_LABELS.get(provider or "", "External form")
