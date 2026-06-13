"""Timezone-aware helpers for Thailand (UTC+7)."""
from datetime import date, datetime, timedelta, timezone

TZ_THAI = timezone(timedelta(hours=7))


def today_th() -> date:
    """Return current date in Thailand timezone (UTC+7)."""
    return datetime.now(TZ_THAI).date()


def safe_year_month(year, month, today: date) -> tuple[int, int]:
    """Validate calendar query params; fall back to today's year/month."""
    try:
        year = int(year)
        month = int(month)
    except (TypeError, ValueError):
        return today.year, today.month
    if not (1 <= month <= 12) or not (2000 <= year <= today.year + 1):
        return today.year, today.month
    return year, month
