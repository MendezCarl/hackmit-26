"""Validation and parsing of professor-supplied Zoom meeting join links.

A join link is the only URL Bloom ever opens on a student's behalf, so it is
constrained tightly at this boundary: ``https`` only, a Zoom-owned host, no
userinfo, and a recognisable meeting path. The parsed result carries the
meeting number so one pasted link both offers a **Join meeting** button and
binds the session to its RTMS transcript stream.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from app.core.errors import AppError, ErrorCode

MAX_JOIN_URL_LENGTH = 2048

ALLOWED_ZOOM_DOMAINS: frozenset[str] = frozenset({"zoom.us", "zoom.com", "zoomgov.com"})

_MEETING_PATH = re.compile(r"^/(?:j|w|s|wc/join|wc/\d+/join)/(\d{9,11})/?$")
_PERSONAL_PATH = re.compile(r"^/my/[A-Za-z0-9._-]{1,64}/?$")
_PASSCODE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


@dataclass(frozen=True, slots=True)
class ZoomJoinLink:
    """A validated Zoom join link and the meeting it points at."""

    url: str
    """Normalised ``https`` URL safe to hand to a browser or the Zoom client."""

    host: str
    meeting_number: str | None
    """Numeric meeting id from the path, or ``None`` for personal-room links."""

    passcode: str | None


def is_allowed_zoom_host(host: str) -> bool:
    """Return whether ``host`` is Zoom-owned.

    Args:
        host: Lower-case hostname without port or userinfo.

    Returns:
        ``True`` for an allowed apex domain or any subdomain of one.
    """

    return any(
        host == domain or host.endswith(f".{domain}") for domain in ALLOWED_ZOOM_DOMAINS
    )


def parse_zoom_join_url(raw: str) -> ZoomJoinLink:
    """Validate a pasted Zoom join link and extract its meeting details.

    Args:
        raw: URL as typed or pasted by the session owner.

    Returns:
        The normalised link; query parameters other than ``pwd`` and the
        fragment are dropped so nothing unexpected is stored or opened.

    Raises:
        ValueError: When the link is not an ``https`` Zoom meeting URL. The
            message is safe to return to the caller and never echoes the input.
    """

    candidate = raw.strip()
    if not candidate or len(candidate) > MAX_JOIN_URL_LENGTH:
        raise ValueError("Zoom join link must be a non-empty https URL.")
    if any(ch.isspace() or ord(ch) < 0x20 for ch in candidate):
        raise ValueError(
            "Zoom join link must not contain whitespace or control characters."
        )

    parts = urlsplit(candidate)
    if parts.scheme.lower() != "https":
        raise ValueError("Zoom join link must use https.")
    if parts.username is not None or parts.password is not None:
        raise ValueError("Zoom join link must not contain credentials.")
    if parts.port is not None:
        raise ValueError("Zoom join link must not specify a port.")
    host = (parts.hostname or "").lower()
    if not host or not is_allowed_zoom_host(host):
        raise ValueError("Zoom join link must point at a zoom.us or zoom.com host.")

    path = parts.path or "/"
    meeting_match = _MEETING_PATH.match(path)
    if meeting_match is None and _PERSONAL_PATH.match(path) is None:
        raise ValueError("Zoom join link must be a meeting or personal-room link.")
    meeting_number = meeting_match.group(1) if meeting_match else None

    passcode: str | None = None
    query = parse_qs(parts.query, keep_blank_values=False)
    pwd_values = query.get("pwd", [])
    if pwd_values:
        pwd = pwd_values[0]
        if len(pwd_values) > 1 or not _PASSCODE.match(pwd):
            raise ValueError("Zoom join link passcode is malformed.")
        passcode = pwd

    normalised = f"https://{host}{path.rstrip('/') or '/'}"
    if passcode is not None:
        normalised += f"?pwd={passcode}"
    return ZoomJoinLink(
        url=normalised, host=host, meeting_number=meeting_number, passcode=passcode
    )


@dataclass(frozen=True, slots=True)
class ZoomMeetingBinding:
    """Meeting id and join link a session stores after owner input is validated."""

    zoom_meeting_id: str | None
    zoom_join_url: str | None


def bind_zoom_meeting(
    zoom_meeting_id: str | None, zoom_join_url: str | None
) -> ZoomMeetingBinding:
    """Combine an optional meeting id and join link into one consistent binding.

    Args:
        zoom_meeting_id: Meeting number or UUID typed by the owner, if any.
        zoom_join_url: Join link pasted by the owner, if any.

    Returns:
        The binding; when only a link is given its meeting number becomes the
        meeting id so RTMS webhooks match the session.

    Raises:
        AppError: ``validation_failed`` when the link is invalid or names a
            different meeting than the explicit id.
    """

    meeting_id = (zoom_meeting_id or "").strip() or None
    if zoom_join_url is None or not zoom_join_url.strip():
        return ZoomMeetingBinding(zoom_meeting_id=meeting_id, zoom_join_url=None)

    try:
        link = parse_zoom_join_url(zoom_join_url)
    except ValueError as error:
        raise AppError(ErrorCode.VALIDATION_FAILED, str(error)) from error

    if meeting_id is None:
        meeting_id = link.meeting_number
    elif (
        link.meeting_number is not None
        and meeting_id.isdigit()
        and link.meeting_number != meeting_id
    ):
        # A meeting UUID cannot be compared with the link's meeting number, so
        # only two differing numeric ids are treated as a conflict.
        raise AppError(
            ErrorCode.VALIDATION_FAILED,
            "Zoom join link names a different meeting than zoom_meeting_id.",
        )
    return ZoomMeetingBinding(zoom_meeting_id=meeting_id, zoom_join_url=link.url)
