"""Точка входа для FastAPI Cloud.

`fastapi run` / FastAPI Cloud ищут переменную `app` в корневом main.py, а сам
код бота живёт в hn_digest/bot/main.py — здесь только переэкспорт.
"""

from hn_digest.bot.main import app  # noqa: F401
