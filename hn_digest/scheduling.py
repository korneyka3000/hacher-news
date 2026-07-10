"""Гард окна запуска: не отправлять поздний прогон.

launchd в 9:00 при спящем Mac выполняет задачу при следующем пробуждении. Для
личного дайджеста поздняя доставка (например, днём) не нужна — если проснулись
сильно позже цели, прогон лучше пропустить. Ручные запуски гард не трогают
(это решает вызывающий код по флагу `--scheduled`).
"""

from __future__ import annotations

from datetime import datetime, timedelta


def is_within_window(now: datetime, hour: int, minute: int, window_minutes: int) -> bool:
    """True, если `now` не позже, чем сегодняшняя цель (hour:minute) + окно.

    Запуск раньше цели допустим (возвращает True) — например, ранний ручной
    прогон в плановом режиме. Поздний запуск (машина спала и проснулась позже
    окна) даёт False.
    """
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    deadline = target + timedelta(minutes=window_minutes)
    return now <= deadline
