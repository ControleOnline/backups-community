from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from backups.models import ScheduleSettings


def is_due(schedule: ScheduleSettings | None, now: datetime | None = None) -> bool:
    if schedule is None:
        return True
    current = now or datetime.now(ZoneInfo(schedule.timezone))
    return current.strftime("%H:%M") == schedule.time
