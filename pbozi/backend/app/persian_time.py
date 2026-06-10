from datetime import datetime, timezone, timedelta

import jdatetime

_TEHRAN_TZ = timezone(timedelta(hours=3, minutes=30))


def to_tehran(dt: datetime) -> datetime:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_TEHRAN_TZ)


def to_jalali(dt: datetime) -> jdatetime.datetime:
    tehran_dt = to_tehran(dt)
    return jdatetime.datetime.fromgregorian(datetime=tehran_dt)


def format_persian(dt: datetime, fmt: str = "%Y-%m-%d %H:%M") -> str:
    if dt is None:
        return "-"
    jdt = to_jalali(dt)
    return jdt.strftime(fmt)
