"""Timezone-aware helpers for Thailand (UTC+7)."""
from datetime import date, datetime, timedelta, timezone

TZ_THAI = timezone(timedelta(hours=7))


def today_th() -> date:
    """Return current date in Thailand timezone (UTC+7)."""
    return datetime.now(TZ_THAI).date()
