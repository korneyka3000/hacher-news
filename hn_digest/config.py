"""Конфигурация: загрузка .env и типизированные настройки."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Корень проекта (папка, где лежат .env, state/ и т.д.) — на уровень выше пакета.
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_env(env_path: Path | None = None) -> None:
    """Подгружает KEY=VALUE из .env, не перетирая уже заданное окружение."""
    path = env_path or (PROJECT_ROOT / ".env")
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(slots=True)
class Settings:
    telegram_bot_token: str
    telegram_chat_id: str
    claude_bin: str
    claude_model: str
    hn_frontpage_count: int
    hn_showhn_count: int
    hn_min_points: int
    hn_lookback_hours: int
    enrich_top_n: int
    seen_path: Path
    seen_ttl_days: int
    usage_path: Path
    schedule_hour: int
    schedule_minute: int
    run_window_minutes: int

    @classmethod
    def from_env(cls) -> Settings:
        load_env()
        return cls(
            telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(),
            telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", "").strip(),
            claude_bin=os.environ.get("CLAUDE_BIN", "claude").strip(),
            claude_model=os.environ.get("CLAUDE_MODEL", "").strip(),
            hn_frontpage_count=int(os.environ.get("HN_FRONTPAGE_COUNT", "50")),
            hn_showhn_count=int(os.environ.get("HN_SHOWHN_COUNT", "30")),
            hn_min_points=int(os.environ.get("HN_MIN_POINTS", "20")),
            hn_lookback_hours=int(os.environ.get("HN_LOOKBACK_HOURS", "36")),
            enrich_top_n=int(os.environ.get("ENRICH_TOP_N", "25")),
            seen_path=Path(os.environ.get("SEEN_PATH", str(PROJECT_ROOT / "state" / "seen.json"))),
            seen_ttl_days=int(os.environ.get("SEEN_TTL_DAYS", "30")),
            usage_path=Path(
                os.environ.get("USAGE_PATH", str(PROJECT_ROOT / "state" / "usage.jsonl"))
            ),
            schedule_hour=int(os.environ.get("SCHEDULE_HOUR", "9")),
            schedule_minute=int(os.environ.get("SCHEDULE_MINUTE", "0")),
            run_window_minutes=int(os.environ.get("RUN_WINDOW_MINUTES", "90")),
        )

    def require_telegram(self) -> None:
        if not self.telegram_bot_token or not self.telegram_chat_id:
            raise SystemExit("Не заданы TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID (см. .env).")
