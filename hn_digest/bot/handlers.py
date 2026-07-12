"""Хендлеры: команды и callback-навигация по дайджесту."""

from __future__ import annotations

from datetime import date

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import repo
from . import keyboards as kb
from .callbacks import (
    SRC_DATES,
    SRC_SAVED,
    CardCb,
    DatePickCb,
    DatesCb,
    MenuCb,
    SaveCb,
    SavedCb,
    SavedOpenCb,
)
from .keyboards import PAGE_DATES, PAGE_SAVED
from .render import render_card

router = Router()

_MENU_TEXT = "🗞 <b>HN Digest</b>\nЧто показать?"
_EMPTY = "Пока пусто — дайджест ещё не сохранён. Загляни позже. 🙂"


# ── Команды ──────────────────────────────────────────────────────────────
@router.message(CommandStart())
@router.message(Command("menu"))
async def cmd_start(message: Message, command: CommandObject, session: AsyncSession) -> None:
    # Deep-link `/start latest` (из уведомления пайплайна) → сразу карточки.
    if command.args == "latest" and message.from_user is not None:
        await _send_latest(message, session, message.from_user.id)
        return
    await message.answer(_MENU_TEXT, reply_markup=kb.main_menu())


async def _send_latest(message: Message, session: AsyncSession, user_id: int) -> None:
    latest = await repo.latest_date(session)
    if latest is None:
        await message.answer(_EMPTY)
        return
    posts = await repo.get_posts_for_date(session, latest)
    if not posts:
        await message.answer(_EMPTY)
        return
    idx = await repo.first_unviewed_index(session, user_id, latest)
    text, markup = await _build_card_view(session, user_id, posts, idx, SRC_DATES)
    await message.answer(text, reply_markup=markup)


# ── Главное меню ─────────────────────────────────────────────────────────
@router.callback_query(MenuCb.filter(F.action == "noop"))
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(MenuCb.filter(F.action == "home"))
async def cb_home(callback: CallbackQuery) -> None:
    await _safe_edit(callback, _MENU_TEXT, kb.main_menu())
    await callback.answer()


@router.callback_query(MenuCb.filter(F.action == "dates"))
async def cb_menu_dates(callback: CallbackQuery, session: AsyncSession) -> None:
    await _show_dates(callback, session, page=0)


@router.callback_query(MenuCb.filter(F.action == "saved"))
async def cb_menu_saved(callback: CallbackQuery, session: AsyncSession) -> None:
    await _show_saved(callback, session, page=0)


@router.callback_query(MenuCb.filter(F.action == "latest"))
async def cb_latest(callback: CallbackQuery, session: AsyncSession) -> None:
    latest = await repo.latest_date(session)
    if latest is None:
        await callback.answer(_EMPTY, show_alert=True)
        return
    idx = await repo.first_unviewed_index(session, callback.from_user.id, latest)
    await _show_card(callback, session, latest, idx, SRC_DATES)


# ── Список дат ───────────────────────────────────────────────────────────
@router.callback_query(DatesCb.filter())
async def cb_dates_page(
    callback: CallbackQuery, callback_data: DatesCb, session: AsyncSession
) -> None:
    await _show_dates(callback, session, page=callback_data.page)


@router.callback_query(DatePickCb.filter())
async def cb_date_pick(
    callback: CallbackQuery, callback_data: DatePickCb, session: AsyncSession
) -> None:
    d = date.fromisoformat(callback_data.d)
    idx = await repo.first_unviewed_index(session, callback.from_user.id, d)
    await _show_card(callback, session, d, idx, SRC_DATES)


# ── Карточка ─────────────────────────────────────────────────────────────
@router.callback_query(CardCb.filter())
async def cb_card(callback: CallbackQuery, callback_data: CardCb, session: AsyncSession) -> None:
    await _show_card(
        callback,
        session,
        date.fromisoformat(callback_data.d),
        callback_data.i,
        callback_data.s,
    )


@router.callback_query(SaveCb.filter())
async def cb_save(callback: CallbackQuery, callback_data: SaveCb, session: AsyncSession) -> None:
    d = date.fromisoformat(callback_data.d)
    posts = await repo.get_posts_for_date(session, d)
    if not posts:
        await callback.answer(_EMPTY, show_alert=True)
        return
    idx = max(0, min(callback_data.i, len(posts) - 1))
    now_saved = await repo.toggle_saved(session, callback.from_user.id, posts[idx].id)
    # Перерисовываем карточку, чтобы кнопка сменила подпись.
    await _render_existing(callback, session, posts, idx, callback_data.s, callback.from_user.id)
    await callback.answer("Сохранено ⭐" if now_saved else "Убрано из сохранённых")


# ── Сохранённые ──────────────────────────────────────────────────────────
@router.callback_query(SavedCb.filter())
async def cb_saved_page(
    callback: CallbackQuery, callback_data: SavedCb, session: AsyncSession
) -> None:
    await _show_saved(callback, session, page=callback_data.page)


@router.callback_query(SavedOpenCb.filter())
async def cb_saved_open(
    callback: CallbackQuery, callback_data: SavedOpenCb, session: AsyncSession
) -> None:
    post = await repo.get_post(session, callback_data.pid)
    if post is None:
        await callback.answer("Пост не найден.", show_alert=True)
        return
    posts = await repo.get_posts_for_date(session, post.digest_date)
    idx = next((i for i, p in enumerate(posts) if p.id == post.id), 0)
    await _show_card(callback, session, post.digest_date, idx, SRC_SAVED)


# ── Общие помощники ──────────────────────────────────────────────────────
async def _show_dates(callback: CallbackQuery, session: AsyncSession, page: int) -> None:
    user_id = callback.from_user.id
    rows = await repo.list_dates(session, user_id, PAGE_DATES + 1, page * PAGE_DATES)
    has_next = len(rows) > PAGE_DATES
    rows = rows[:PAGE_DATES]
    if not rows and page == 0:
        await _safe_edit(callback, _EMPTY, kb.main_menu())
        await callback.answer()
        return
    await _safe_edit(callback, "Выбери день:", kb.dates_kb(rows, page, has_next))
    await callback.answer()


async def _show_saved(callback: CallbackQuery, session: AsyncSession, page: int) -> None:
    user_id = callback.from_user.id
    total = await repo.count_saved(session, user_id)
    posts = await repo.list_saved(session, user_id, PAGE_SAVED, page * PAGE_SAVED)
    if not posts and page == 0:
        await _safe_edit(
            callback, "Пока ничего не сохранено. Открой пост и жми «⭐ Сохранить».", kb.main_menu()
        )
        await callback.answer()
        return
    has_next = (page + 1) * PAGE_SAVED < total
    await _safe_edit(callback, f"Твои сохранённые ({total}):", kb.saved_kb(posts, page, has_next))
    await callback.answer()


async def _show_card(
    callback: CallbackQuery,
    session: AsyncSession,
    d: date,
    idx: int,
    src: str,
) -> None:
    posts = await repo.get_posts_for_date(session, d)
    if not posts:
        await callback.answer(_EMPTY, show_alert=True)
        return
    idx = max(0, min(idx, len(posts) - 1))
    await _render_existing(callback, session, posts, idx, src, callback.from_user.id)
    await callback.answer()


async def _build_card_view(
    session: AsyncSession, user_id: int, posts: list, idx: int, src: str
) -> tuple[str, InlineKeyboardMarkup]:
    """Считает (текст, клавиатуру) карточки posts[idx] и помечает её просмотренной.

    Переиспользуется и для редактирования (callback), и для отправки новым
    сообщением (deep-link `/start latest`).
    """
    post = posts[idx]
    _, is_saved = await repo.get_state(session, user_id, post.id)
    is_new = await repo.mark_viewed(session, user_id, post.id)
    text = render_card(post, idx, len(posts), is_new)
    markup = kb.card_kb(
        post,
        d=post.digest_date.isoformat(),
        idx=idx,
        src=src,
        total=len(posts),
        is_saved=is_saved,
    )
    return text, markup


async def _render_existing(
    callback: CallbackQuery,
    session: AsyncSession,
    posts: list,
    idx: int,
    src: str,
    user_id: int,
) -> None:
    """Перерисовывает карточку в текущем сообщении (edit)."""
    text, markup = await _build_card_view(session, user_id, posts, idx, src)
    await _safe_edit(callback, text, markup)


async def _safe_edit(callback: CallbackQuery, text: str, markup) -> None:
    """edit_text с проглатыванием 'message is not modified'."""
    message = callback.message
    # InaccessibleMessage (слишком старое сообщение) не редактируется — шлём новое.
    if not isinstance(message, Message):
        if message is not None and callback.bot is not None:
            await callback.bot.send_message(message.chat.id, text, reply_markup=markup)
        return
    try:
        await message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise
