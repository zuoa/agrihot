"""Five-field cron parsing shared by settings, previews and the worker."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from croniter import CroniterBadCronError, CroniterBadDateError, croniter

def validate_cron(value: str) -> str:
    expression = " ".join(value.split())
    if len(expression) > 100 or len(expression.split()) != 5:
        raise ValueError("Cron 表达式应为五段：分 时 日 月 周，不包含秒或年份")
    try:
        if not croniter.is_valid(expression):
            raise ValueError("Cron 表达式无效，请检查各字段的范围和写法")
        croniter(expression, datetime.now(timezone.utc), max_years_between_matches=8).get_next(datetime)
    except (CroniterBadCronError, CroniterBadDateError) as exc:
        raise ValueError("Cron 表达式无效，或没有可执行的日期") from exc
    return expression


def daily_cron(value: str) -> str:
    hour, minute = (int(part) for part in value.split(":"))
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("每日时刻应为 HH:MM")
    return f"{minute} {hour} * * *"


def cron_preview(expression: str, timezone_name: str, *, now=None, count=3) -> dict:
    expression = validate_cron(expression)
    zone = ZoneInfo(timezone_name)
    current = (now or datetime.now(timezone.utc)).astimezone(zone)
    iterator = croniter(expression, current, max_years_between_matches=8)
    return {"expression": expression, "timezone": timezone_name,
            "next_runs": [iterator.get_next(datetime).astimezone(timezone.utc) for _ in range(count)]}


def matches(expression: str, moment: datetime) -> bool:
    return croniter.match(expression, moment, day_or=True)
