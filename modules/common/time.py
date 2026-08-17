"""业务日期边界，避免将 UTC 日期误当成学习者的“今天”。"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .errors import ConfigurationError


def business_now(
    at: datetime | None = None,
    *,
    timezone_name: str | None = None,
) -> datetime:
    name = str(
        timezone_name or os.getenv("STUDY_COMPANION_TIMEZONE", "Asia/Shanghai")
    ).strip()
    try:
        zone = ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ConfigurationError(
            "STUDY_COMPANION_TIMEZONE is invalid",
            details={"timezone": name},
            cause=exc,
        ) from exc
    instant = at or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(zone)


def business_date(
    at: datetime | None = None,
    *,
    timezone_name: str | None = None,
) -> date:
    return business_now(at, timezone_name=timezone_name).date()


def business_today(*, timezone_name: str | None = None) -> date:
    return business_date(timezone_name=timezone_name)
