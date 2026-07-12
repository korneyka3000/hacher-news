"""Тесты формирования payload в TelegramClient.send (мок httpx)."""

from __future__ import annotations

import json

import httpx

from hn_digest.telegram import TelegramClient


class _Resp:
    @staticmethod
    def json() -> dict:
        return {"ok": True}


def test_send_includes_reply_markup_and_chat(monkeypatch):
    captured: dict = {}

    def fake_post(url, data=None, headers=None, timeout=None):
        captured["url"] = url
        captured["data"] = data
        return _Resp()

    monkeypatch.setattr(httpx, "post", fake_post)
    client = TelegramClient("TOK", "default_chat")
    client.send("hi", chat_id=42, reply_markup={"inline_keyboard": [[{"text": "x", "url": "u"}]]})
    assert captured["data"]["chat_id"] == 42
    markup = json.loads(captured["data"]["reply_markup"])
    assert markup["inline_keyboard"][0][0]["text"] == "x"


def test_send_defaults_to_configured_chat(monkeypatch):
    captured: dict = {}

    def fake_post(url, data=None, headers=None, timeout=None):
        captured["data"] = data
        return _Resp()

    monkeypatch.setattr(httpx, "post", fake_post)
    TelegramClient("TOK", "default_chat").send("hi")
    assert captured["data"]["chat_id"] == "default_chat"
    assert "reply_markup" not in captured["data"]
