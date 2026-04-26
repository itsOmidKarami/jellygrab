"""Latest session-health snapshot, populated by keepalive and read by the API."""

import time
from dataclasses import asdict, dataclass


@dataclass
class SessionStatus:
    last_check_at: float | None = None
    healthy: bool | None = None  # None = never checked
    logged_in: bool | None = None
    cf_clearance_present: bool = False
    cookies_count: int = 0
    error: str | None = None
    note: str | None = None  # human-readable last result

    def to_dict(self) -> dict:
        return asdict(self) | {"now": time.time()}


status = SessionStatus()
