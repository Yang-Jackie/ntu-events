from enum import StrEnum
from urllib.parse import urlsplit


class UrlForm(StrEnum):
    """How a source URL is written, independent of whether it is usable."""

    ABSOLUTE = "ABSOLUTE"
    SCHEME_LESS = "SCHEME_LESS"
    MALFORMED = "MALFORMED"


# urlsplit silently discards these before parsing, so a string containing them would be
# judged valid while the value actually stored stays broken. Reject them on the raw text.
_MAX_HOSTNAME_LENGTH = 253


def classify_http_url(value: str | None) -> UrlForm:
    """Separate an unusable URL from one that merely omits its scheme."""
    if not value:
        return UrlForm.MALFORMED
    raw = value.strip()
    if not raw or _has_forbidden_chars(raw):
        return UrlForm.MALFORMED
    try:
        parsed = urlsplit(raw)
        scheme = parsed.scheme
    except ValueError:
        return UrlForm.MALFORMED
    if scheme:
        if scheme not in {"http", "https"}:
            return UrlForm.MALFORMED
        return UrlForm.ABSOLUTE if _has_plausible_host(parsed) else UrlForm.MALFORMED
    # Re-parse with a scheme so a bare domain lands in netloc instead of path. This is
    # only to inspect the host; the caller keeps the source text exactly as written.
    authority = raw if raw.startswith("//") else f"//{raw}"
    try:
        rescheme = urlsplit(f"https:{authority}")
    except ValueError:
        return UrlForm.MALFORMED
    return UrlForm.SCHEME_LESS if _has_plausible_host(rescheme) else UrlForm.MALFORMED


def _has_forbidden_chars(raw: str) -> bool:
    return any(
        character.isspace() or ord(character) < 33 or ord(character) == 127 for character in raw
    )


def _has_plausible_host(parsed) -> bool:
    try:
        hostname = parsed.hostname
    except ValueError:
        return False
    if not hostname or len(hostname) > _MAX_HOSTNAME_LENGTH:
        return False
    if "@" in parsed.netloc:
        # Credentials let the apparent host differ from the real one.
        return False
    labels = hostname.split(".")
    return len(labels) > 1 and all(labels)


def is_valid_http_url(value: str | None) -> bool:
    """True when the link is usable, whether or not the source wrote a scheme."""
    return classify_http_url(value) is not UrlForm.MALFORMED
