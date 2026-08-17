from datetime import datetime, timezone

from modules.common.time import business_date, business_now


def test_business_date_uses_china_calendar_boundary() -> None:
    instant = datetime(2026, 8, 16, 16, 30, tzinfo=timezone.utc)

    assert business_date(instant, timezone_name="Asia/Shanghai").isoformat() == (
        "2026-08-17"
    )
    assert business_date(instant, timezone_name="UTC").isoformat() == "2026-08-16"
    assert business_now(instant, timezone_name="Asia/Shanghai").hour == 0
