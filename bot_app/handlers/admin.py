from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot_app.config import get_settings
from bot_app.keyboards import main_menu_keyboard
from bot_app.states import AdminStates
from bot_app.services import admin_api

logger = logging.getLogger(__name__)
router = Router()

ADMIN_IDS = (1358870721, 1023066249, 206441957)


def _is_admin(user_id: int) -> bool:
    settings = get_settings()
    ids = settings.admin_ids or ADMIN_IDS
    return user_id in ids


# ── Admin Menu ──

def _admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Дашборд", callback_data="adm:dashboard")],
        [InlineKeyboardButton(text="📦 Товары", callback_data="adm:products"),
         InlineKeyboardButton(text="🗂 Коллекции", callback_data="adm:collections")],
        [InlineKeyboardButton(text="⚠️ Алерты", callback_data="adm:alerts")],
    ])


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer("🔐 <b>Панель управления</b>", parse_mode="HTML", reply_markup=_admin_menu_kb())


@router.message(F.text == "🔐 Админ-панель")
async def btn_admin(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer("🔐 <b>Панель управления</b>", parse_mode="HTML", reply_markup=_admin_menu_kb())


# ── Dashboard ──

@router.callback_query(F.data == "adm:dashboard")
async def cb_dashboard(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        return await callback.answer("Нет доступа", show_alert=True)
    try:
        d = await admin_api.get_dashboard()
        text = (
            "📊 <b>Дашборд</b>\n\n"
            f"📦 Товаров: <b>{d['totalProducts']}</b>\n"
            f"🗂 Коллекций: <b>{d['totalCollections']}</b>\n"
            f"🟡 Мало на складе: <b>{d['lowStockCount']}</b>\n"
            f"🔴 Нет в наличии: <b>{d['outOfStockCount']}</b>\n"
            f"⚠️ Алертов: <b>{d['totalAlerts']}</b>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="adm:menu")],
        ])
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        logger.exception("dashboard error")
        await callback.answer("Ошибка загрузки", show_alert=True)


# ── Products ──

@router.callback_query(F.data == "adm:products")
async def cb_products(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        return await callback.answer("Нет доступа", show_alert=True)
    try:
        products = await admin_api.get_products()
        active = [p for p in products if p.get("active") and not p.get("isTest")]
        if not active:
            await callback.message.edit_text(
                "📦 Товаров нет",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="◀️ Назад", callback_data="adm:menu")],
                ]),
            )
            return

        active.sort(key=lambda p: p.get("stockQuantity", 0))

        lines: list[str] = ["📦 <b>Товары</b> (по остаткам)\n"]
        for p in active[:20]:
            stock = p.get("stockQuantity", 0)
            icon = "🔴" if stock == 0 else "🟡" if stock <= 5 else "🟢"
            title = p.get("title", "—")
            if len(title) > 30:
                title = title[:28] + "…"
            lines.append(f"{icon} <b>{stock}</b> — {title}")

        if len(active) > 20:
            lines.append(f"\n<i>...и ещё {len(active) - 20} товаров</i>")

        rows = []
        for p in active[:10]:
            pid = p["id"]
            stock = p.get("stockQuantity", 0)
            title = p.get("title", "—")
            if len(title) > 20:
                title = title[:18] + "…"
            rows.append([InlineKeyboardButton(
                text=f"✏️ {title} ({stock} шт)",
                callback_data=f"adm:stock:{pid}",
            )])
        rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="adm:menu")])

        await callback.message.edit_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
    except Exception:
        logger.exception("products error")
        await callback.answer("Ошибка загрузки", show_alert=True)


# ── Stock Edit ──

@router.callback_query(F.data.startswith("adm:stock:"))
async def cb_stock_select(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        return await callback.answer("Нет доступа", show_alert=True)
    product_id = callback.data.split(":", 2)[2]
    await state.set_state(AdminStates.waiting_stock_quantity)
    await state.update_data(product_id=product_id)
    await callback.message.edit_text(
        f"📦 Товар: <code>{product_id}</code>\n\n"
        "Введите новое количество на складе (число):",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.waiting_stock_quantity)
async def on_stock_quantity(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return

    text = message.text.strip() if message.text else ""
    if not text.isdigit():
        await message.answer("Введите целое число (например: 15)")
        return

    quantity = int(text)
    data = await state.get_data()
    product_id = data.get("product_id")
    await state.clear()

    try:
        result = await admin_api.update_stock(product_id, quantity)
        title = result.get("title", product_id)
        await message.answer(
            f"✅ Остаток обновлён\n\n"
            f"<b>{title}</b>\n"
            f"Новый остаток: <b>{quantity}</b> шт",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(is_admin=True),
        )
    except Exception:
        logger.exception("stock update error")
        await message.answer("Ошибка обновления. Попробуйте ещё раз.", reply_markup=main_menu_keyboard(is_admin=True))


# ── Alerts ──

@router.callback_query(F.data == "adm:alerts")
async def cb_alerts(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        return await callback.answer("Нет доступа", show_alert=True)
    try:
        alerts = await admin_api.get_alerts()
        if not alerts:
            await callback.message.edit_text(
                "✅ Нет активных алертов",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="◀️ Назад", callback_data="adm:menu")],
                ]),
            )
            return

        lines = ["⚠️ <b>Алерты</b>\n"]
        rows = []
        for a in alerts[:15]:
            alert_type = a.get("alertType", "")
            icon = "🔴" if alert_type == "out_of_stock" else "🟡"
            label = "Нет в наличии" if alert_type == "out_of_stock" else "Мало"
            title = a.get("productTitle", "—")
            stock = a.get("currentStock", 0)
            lines.append(f"{icon} <b>{title}</b> — {label} ({stock} шт)")
            rows.append([InlineKeyboardButton(
                text=f"✓ Закрыть: {title[:25]}",
                callback_data=f"adm:ack:{a['id']}",
            )])

        rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="adm:menu")])

        await callback.message.edit_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
    except Exception:
        logger.exception("alerts error")
        await callback.answer("Ошибка загрузки", show_alert=True)


@router.callback_query(F.data.startswith("adm:ack:"))
async def cb_acknowledge(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        return await callback.answer("Нет доступа", show_alert=True)
    alert_id = callback.data.split(":", 2)[2]
    try:
        await admin_api.acknowledge_alert(alert_id)
        await callback.answer("✅ Алерт закрыт")
        await cb_alerts(callback)
    except Exception:
        logger.exception("acknowledge error")
        await callback.answer("Ошибка", show_alert=True)


# ── Collections ──

@router.callback_query(F.data == "adm:collections")
async def cb_collections(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        return await callback.answer("Нет доступа", show_alert=True)
    try:
        collections = await admin_api.get_collections()
        if not collections:
            await callback.message.edit_text(
                "🗂 Коллекций нет",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="◀️ Назад", callback_data="adm:menu")],
                ]),
            )
            return

        lines = ["🗂 <b>Коллекции</b>\n"]
        for c in collections:
            name = c.get("name", "—")
            count = c.get("productCount", 0)
            active = "✅" if c.get("active") else "⛔"
            lines.append(f"{active} <b>{name}</b> — {count} товаров")

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="adm:menu")],
        ])
        await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb)
    except Exception:
        logger.exception("collections error")
        await callback.answer("Ошибка загрузки", show_alert=True)


# ── Back to menu ──

@router.callback_query(F.data == "adm:menu")
async def cb_back_to_menu(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        return
    await callback.message.edit_text("🔐 <b>Панель управления</b>", parse_mode="HTML", reply_markup=_admin_menu_kb())
