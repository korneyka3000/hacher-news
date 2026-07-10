"""Тонкий клиент Telegram Bot API."""

from __future__ import annotations

import time

import httpx

from .logging_setup import get_logger

log = get_logger(__name__)

USER_AGENT = "hn-digest/0.2"


class TelegramClient:
    def __init__(self, token: str, chat_id: str) -> None:
        self._base = f"https://api.telegram.org/bot{token}"
        self._chat_id = chat_id

    def send(self, text: str, *, parse_mode: str | None = "HTML") -> None:
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "disable_web_page_preview": "true",
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        resp = httpx.post(
            f"{self._base}/sendMessage",
            data=payload,
            headers={"User-Agent": USER_AGENT},
            timeout=30.0,
        )
        body = resp.json()
        if not body.get("ok"):
            raise RuntimeError(f"Telegram отклонил сообщение: {body}")

    def send_all(self, messages: list[str]) -> None:
        for idx, msg in enumerate(messages, 1):
            self.send(msg)
            log.info("Отправлено сообщение %s/%s", idx, len(messages))
            time.sleep(1)  # щадим лимиты Telegram

    def send_error(self, text: str) -> None:
        """Уведомление об ошибке. Без parse_mode и глотает свои исключения,
        чтобы обработчик падения сам не упал."""
        try:
            self.send(text, parse_mode=None)
        except Exception as exc:  # noqa: BLE001
            log.error("Не удалось отправить уведомление об ошибке: %s", exc)
