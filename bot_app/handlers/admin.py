from __future__ import annotations

import json
import logging
import re

from aiogram import Bot, F, Router
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

CATEGORIES = {
    "dresses": "Платья",
    "outerwear": "Верхняя одежда",
    "tailoring": "Костюмы",
    "knitwear": "Трикотаж",
    "blouses": "Блузки",
    "skirts": "Юбки",
    "trousers": "Брюки",
    "accessories": "Аксессуары",
}

SIZES = ["XS", "S", "M", "L", "XL"]


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
        [InlineKeyboardButton(text="➕ Добавить товар", callback_data="adm:add_product")],
        [InlineKeyboardButton(text="➕ Добавить коллекцию", callback_data="adm:add_collection")],
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


# ── Products List ──

@router.callback_query(F.data == "adm:products")
async def cb_products(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        return await callback.answer("Нет доступа", show_alert=True)
    try:
        products = await admin_api.get_products()
        active = [p for p in products if p.get("active") and not p.get("isTest")]
        if not active:
            await callback.message.edit_text(
                "📦 Товаров пока нет.\nДобавьте первый товар!",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="➕ Добавить товар", callback_data="adm:add_product")],
                    [InlineKeyboardButton(text="◀️ Назад", callback_data="adm:menu")],
                ]),
            )
            return

        active.sort(key=lambda p: p.get("stockQuantity", 0))

        lines: list[str] = ["📦 <b>Товары</b>\n"]
        for p in active[:20]:
            stock = p.get("stockQuantity", 0)
            icon = "🔴" if stock == 0 else "🟡" if stock <= 5 else "🟢"
            title = p.get("title", "—")
            if len(title) > 30:
                title = title[:28] + "…"
            price = p.get("price", 0)
            lines.append(f"{icon} <b>{title}</b> — {price}€ ({stock} шт)")

        if len(active) > 20:
            lines.append(f"\n<i>...и ещё {len(active) - 20}</i>")

        rows = []
        for p in active[:8]:
            pid = p["id"]
            title = p.get("title", "—")
            if len(title) > 22:
                title = title[:20] + "…"
            rows.append([InlineKeyboardButton(
                text=f"📦 {title}",
                callback_data=f"adm:prod:{pid}",
            )])
        rows.append([InlineKeyboardButton(text="➕ Добавить товар", callback_data="adm:add_product")])
        rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="adm:menu")])

        await callback.message.edit_text(
            "\n".join(lines), parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
    except Exception:
        logger.exception("products error")
        await callback.answer("Ошибка загрузки", show_alert=True)


# ── Product Detail ──

@router.callback_query(F.data.startswith("adm:prod:"))
async def cb_product_detail(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        return await callback.answer("Нет доступа", show_alert=True)
    pid = callback.data.split(":", 2)[2]
    try:
        products = await admin_api.get_products()
        p = next((x for x in products if x["id"] == pid), None)
        if not p:
            return await callback.answer("Товар не найден", show_alert=True)

        cat = CATEGORIES.get(p.get("category", ""), p.get("category", "—"))
        sizes = ", ".join(p.get("sizes") or []) or "—"
        col_name = p.get("collectionName") or "—"
        text = (
            f"📦 <b>{p.get('title', '—')}</b>\n\n"
            f"💰 Цена: <b>{p.get('price', 0)}€</b>\n"
            f"📂 Категория: {cat}\n"
            f"📏 Размеры: {sizes}\n"
            f"📦 Остаток: <b>{p.get('stockQuantity', 0)}</b> шт\n"
            f"🗂 Коллекция: {col_name}\n"
        )
        desc = p.get("description", "")
        if desc:
            short = desc[:100] + "…" if len(desc) > 100 else desc
            text += f"\n📝 {short}"

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Изменить остаток", callback_data=f"adm:stock:{pid}")],
            [InlineKeyboardButton(text="🗑 Удалить товар", callback_data=f"adm:del:{pid}")],
            [InlineKeyboardButton(text="◀️ К товарам", callback_data="adm:products")],
        ])
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        logger.exception("product detail error")
        await callback.answer("Ошибка", show_alert=True)


# ── Delete Product ──

@router.callback_query(F.data.startswith("adm:del:"))
async def cb_delete_confirm(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        return await callback.answer("Нет доступа", show_alert=True)
    pid = callback.data.split(":", 2)[2]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚠️ Да, удалить", callback_data=f"adm:delok:{pid}"),
         InlineKeyboardButton(text="Отмена", callback_data=f"adm:prod:{pid}")],
    ])
    await callback.message.edit_text(
        f"Вы уверены что хотите удалить товар <code>{pid}</code>?",
        parse_mode="HTML", reply_markup=kb,
    )


@router.callback_query(F.data.startswith("adm:delok:"))
async def cb_delete_exec(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        return await callback.answer("Нет доступа", show_alert=True)
    pid = callback.data.split(":", 2)[2]
    try:
        await admin_api.delete_product(pid)
        await callback.answer("✅ Товар удалён")
        await cb_products(callback)
    except Exception:
        logger.exception("delete error")
        await callback.answer("Ошибка удаления", show_alert=True)


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
        "Введите новое количество на складе:",
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
            f"✅ <b>{title}</b>\nОстаток: <b>{quantity}</b> шт",
            parse_mode="HTML", reply_markup=main_menu_keyboard(is_admin=True),
        )
    except Exception:
        logger.exception("stock update error")
        await message.answer("Ошибка. Попробуйте ещё раз.", reply_markup=main_menu_keyboard(is_admin=True))


# ══════════════════════════════════════════════════════════════
# ── ADD PRODUCT WIZARD ──
# ══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm:add_product")
async def cb_add_product(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        return await callback.answer("Нет доступа", show_alert=True)
    await state.clear()
    await state.set_state(AdminStates.add_title)
    await callback.message.edit_text(
        "➕ <b>Новый товар</b>\n\n"
        "Шаг 1/7 — <b>Название</b>\n\n"
        "Напишите название товара:",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.add_title)
async def on_add_title(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    title = (message.text or "").strip()
    if not title or len(title) < 2:
        await message.answer("Название слишком короткое. Введите ещё раз:")
        return
    product_id = re.sub(r"[^a-z0-9]+", "-", title.lower().strip())[:60].strip("-")
    await state.update_data(title=title, product_id=product_id)
    await state.set_state(AdminStates.add_price)
    await message.answer(
        f"✅ <b>{title}</b>\n\n"
        "Шаг 2/7 — <b>Цена</b>\n\n"
        "Введите цену в евро (например: 250):",
        parse_mode="HTML",
    )


@router.message(AdminStates.add_price)
async def on_add_price(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    text = (message.text or "").strip().replace(",", ".")
    try:
        price = float(text)
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите число больше 0 (например: 250):")
        return
    await state.update_data(price=price)
    await state.set_state(AdminStates.add_category)

    rows = []
    row = []
    for key, label in CATEGORIES.items():
        row.append(InlineKeyboardButton(text=label, callback_data=f"adm:cat:{key}"))
        if len(row) == 2:
            rows.append(row[:])
            row.clear()
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="adm:cancel_add")])

    await message.answer(
        f"✅ Цена: <b>{price}€</b>\n\n"
        "Шаг 3/7 — <b>Категория</b>\n\n"
        "Выберите категорию:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.startswith("adm:cat:"))
async def on_add_category(callback: CallbackQuery, state: FSMContext) -> None:
    category = callback.data.split(":", 2)[2]
    await state.update_data(category=category)
    await state.set_state(AdminStates.add_sizes)
    await state.update_data(selected_sizes=[])

    rows = []
    row = []
    for s in SIZES:
        row.append(InlineKeyboardButton(text=s, callback_data=f"adm:sz:{s}"))
        if len(row) == 3:
            rows.append(row[:])
            row.clear()
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="✅ Готово", callback_data="adm:sz_done")])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="adm:cancel_add")])

    await callback.message.edit_text(
        f"✅ Категория: <b>{CATEGORIES.get(category, category)}</b>\n\n"
        "Шаг 4/7 — <b>Размеры</b>\n\n"
        "Нажимайте на размеры которые есть в наличии, "
        "затем нажмите <b>Готово</b>:\n\n"
        "Выбрано: <i>пока ничего</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:sz:"))
async def on_toggle_size(callback: CallbackQuery, state: FSMContext) -> None:
    size = callback.data.split(":", 2)[2]
    data = await state.get_data()
    selected = data.get("selected_sizes", [])
    if size in selected:
        selected.remove(size)
    else:
        selected.append(size)
    await state.update_data(selected_sizes=selected)

    rows = []
    row = []
    for s in SIZES:
        mark = "✓ " if s in selected else ""
        row.append(InlineKeyboardButton(text=f"{mark}{s}", callback_data=f"adm:sz:{s}"))
        if len(row) == 3:
            rows.append(row[:])
            row.clear()
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="✅ Готово", callback_data="adm:sz_done")])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="adm:cancel_add")])

    display = ", ".join(selected) if selected else "<i>пока ничего</i>"
    text = callback.message.text or ""
    # Update just the "Выбрано:" line
    base = text.split("Выбрано:")[0] if "Выбрано:" in text else text
    await callback.message.edit_text(
        f"{base}Выбрано: {display}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data == "adm:sz_done")
async def on_sizes_done(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    selected = data.get("selected_sizes", [])
    if not selected:
        return await callback.answer("Выберите хотя бы один размер!", show_alert=True)
    await state.set_state(AdminStates.add_stock)
    await callback.message.edit_text(
        f"✅ Размеры: <b>{', '.join(selected)}</b>\n\n"
        "Шаг 5/7 — <b>Количество</b>\n\n"
        "Сколько штук на складе?",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.add_stock)
async def on_add_stock(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Введите целое число (например: 10):")
        return
    stock = int(text)
    await state.update_data(stock=stock)
    await state.set_state(AdminStates.add_photos)
    await state.update_data(photos=[])
    await message.answer(
        f"✅ На складе: <b>{stock}</b> шт\n\n"
        "Шаг 6/7 — <b>Фотографии</b>\n\n"
        "Отправьте фото товара (одно или несколько).\n"
        "Когда закончите — нажмите кнопку ниже.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏩ Пропустить фото", callback_data="adm:photos_done")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="adm:cancel_add")],
        ]),
    )


@router.message(AdminStates.add_photos, F.photo)
async def on_add_photo(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    bot: Bot = message.bot
    photo = message.photo[-1]  # highest resolution
    try:
        file = await bot.get_file(photo.file_id)
        file_bytes = await bot.download_file(file.file_path)
        url = await admin_api.upload_image(
            file_bytes.read(), f"{photo.file_unique_id}.jpg", "image/jpeg",
        )
        data = await state.get_data()
        photos = data.get("photos", [])
        photos.append(url)
        await state.update_data(photos=photos)
        await message.answer(
            f"📸 Фото загружено ({len(photos)} шт)\n\n"
            "Отправьте ещё или нажмите <b>Готово</b>.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Готово — перейти дальше", callback_data="adm:photos_done")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="adm:cancel_add")],
            ]),
        )
    except Exception:
        logger.exception("photo upload error")
        await message.answer("Ошибка загрузки фото. Попробуйте ещё раз.")


@router.message(AdminStates.add_photos)
async def on_add_photos_text(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    await message.answer(
        "Отправьте фото (не файл, а именно фото) или нажмите кнопку ниже.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Готово — перейти дальше", callback_data="adm:photos_done")],
            [InlineKeyboardButton(text="⏩ Пропустить фото", callback_data="adm:photos_done")],
        ]),
    )


@router.callback_query(F.data == "adm:photos_done")
async def on_photos_done(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.add_description)
    await callback.message.edit_text(
        "Шаг 7/7 — <b>Описание</b>\n\n"
        "Напишите описание товара или нажмите <b>Пропустить</b>:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏩ Пропустить", callback_data="adm:desc_skip")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="adm:cancel_add")],
        ]),
    )
    await callback.answer()


@router.message(AdminStates.add_description)
async def on_add_description(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    desc = (message.text or "").strip()
    await state.update_data(description=desc)
    await _show_confirm(message, state)


@router.callback_query(F.data == "adm:desc_skip")
async def on_desc_skip(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(description="")
    await _show_confirm_cb(callback, state)


async def _show_confirm(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(AdminStates.add_confirm)
    text = _build_summary(data)
    # Try to load collections for optional assignment
    collections = []
    try:
        collections = await admin_api.get_collections()
    except Exception:
        pass
    rows = []
    if collections:
        for c in collections[:6]:
            name = c.get("name", "—")
            cid = c.get("id", "")
            rows.append([InlineKeyboardButton(text=f"🗂 {name}", callback_data=f"adm:setcol:{cid}")])
    rows.append([InlineKeyboardButton(text="✅ Создать без коллекции", callback_data="adm:confirm_add")])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="adm:cancel_add")])
    await message.answer(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


async def _show_confirm_cb(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(AdminStates.add_confirm)
    text = _build_summary(data)
    collections = []
    try:
        collections = await admin_api.get_collections()
    except Exception:
        pass
    rows = []
    if collections:
        for c in collections[:6]:
            name = c.get("name", "—")
            cid = c.get("id", "")
            rows.append([InlineKeyboardButton(text=f"🗂 {name}", callback_data=f"adm:setcol:{cid}")])
    rows.append([InlineKeyboardButton(text="✅ Создать без коллекции", callback_data="adm:confirm_add")])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="adm:cancel_add")])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


def _build_summary(data: dict) -> str:
    cat = CATEGORIES.get(data.get("category", ""), data.get("category", "—"))
    sizes = ", ".join(data.get("selected_sizes", []))
    photos_count = len(data.get("photos", []))
    desc = data.get("description", "")
    desc_line = f"\n📝 {desc[:80]}…" if desc and len(desc) > 80 else f"\n📝 {desc}" if desc else ""
    return (
        "📋 <b>Проверьте данные:</b>\n\n"
        f"📌 <b>{data.get('title', '—')}</b>\n"
        f"💰 {data.get('price', 0)}€\n"
        f"📂 {cat}\n"
        f"📏 {sizes}\n"
        f"📦 {data.get('stock', 0)} шт\n"
        f"📸 {photos_count} фото"
        f"{desc_line}\n\n"
        "Выберите коллекцию или создайте без неё:"
    )


@router.callback_query(F.data.startswith("adm:setcol:"))
async def on_set_collection(callback: CallbackQuery, state: FSMContext) -> None:
    col_id = callback.data.split(":", 2)[2]
    await state.update_data(collection_id=col_id)
    await _do_create_product(callback, state)


@router.callback_query(F.data == "adm:confirm_add")
async def on_confirm_add(callback: CallbackQuery, state: FSMContext) -> None:
    await _do_create_product(callback, state)


async def _do_create_product(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        return
    data = await state.get_data()
    await state.clear()

    photos = data.get("photos", [])
    images_json = json.dumps(photos) if photos else "[]"
    col_id = data.get("collection_id")

    payload = {
        "id": data.get("product_id", "product"),
        "title": data.get("title", ""),
        "description": data.get("description", ""),
        "price": data.get("price", 0),
        "category": data.get("category", ""),
        "sizes": data.get("selected_sizes", []),
        "collectionId": col_id,
        "stockQuantity": data.get("stock", 0),
        "lowStockThreshold": 5,
        "active": True,
        "images": images_json,
        "occasion": None,
        "color": None,
        "material": None,
        "subtitle": None,
        "sku": None,
    }
    try:
        result = await admin_api.create_product(payload)
        await callback.message.edit_text(
            f"✅ <b>Товар создан!</b>\n\n"
            f"📌 {result.get('title', '—')}\n"
            f"💰 {result.get('price', 0)}€\n"
            f"📦 {result.get('stockQuantity', 0)} шт\n\n"
            "Товар уже на сайте!",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ В панель", callback_data="adm:menu")],
            ]),
        )
    except Exception:
        logger.exception("create product error")
        await callback.message.edit_text(
            "❌ Ошибка при создании товара. Попробуйте ещё раз.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ В панель", callback_data="adm:menu")],
            ]),
        )
    await callback.answer()


@router.callback_query(F.data == "adm:cancel_add")
async def on_cancel_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("🔐 <b>Панель управления</b>", parse_mode="HTML", reply_markup=_admin_menu_kb())
    await callback.answer()


# ══════════════════════════════════════════════════════════════
# ── ADD COLLECTION WIZARD ──
# ══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm:add_collection")
async def cb_add_collection(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        return await callback.answer("Нет доступа", show_alert=True)
    await state.clear()
    await state.set_state(AdminStates.col_name)
    await callback.message.edit_text(
        "➕ <b>Новая коллекция</b>\n\n"
        "Введите название коллекции:",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.col_name)
async def on_col_name(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    name = (message.text or "").strip()
    if not name or len(name) < 2:
        await message.answer("Название слишком короткое. Введите ещё раз:")
        return
    await state.update_data(col_name=name)
    await state.set_state(AdminStates.col_description)
    await message.answer(
        f"✅ Коллекция: <b>{name}</b>\n\n"
        "Введите описание или нажмите <b>Пропустить</b>:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏩ Пропустить", callback_data="adm:col_no_desc")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="adm:cancel_add")],
        ]),
    )


@router.message(AdminStates.col_description)
async def on_col_desc(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    desc = (message.text or "").strip()
    await state.update_data(col_description=desc)
    await _create_collection(message, state)


@router.callback_query(F.data == "adm:col_no_desc")
async def on_col_no_desc(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(col_description="")
    data = await state.get_data()
    await state.clear()
    try:
        result = await admin_api.create_collection(data["col_name"], "")
        await callback.message.edit_text(
            f"✅ <b>Коллекция создана!</b>\n\n"
            f"🗂 {result.get('name', '—')}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ В панель", callback_data="adm:menu")],
            ]),
        )
    except Exception:
        logger.exception("create collection error")
        await callback.message.edit_text(
            "❌ Ошибка при создании. Попробуйте ещё раз.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ В панель", callback_data="adm:menu")],
            ]),
        )
    await callback.answer()


async def _create_collection(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    try:
        result = await admin_api.create_collection(data["col_name"], data.get("col_description", ""))
        await message.answer(
            f"✅ <b>Коллекция создана!</b>\n\n"
            f"🗂 {result.get('name', '—')}",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(is_admin=True),
        )
    except Exception:
        logger.exception("create collection error")
        await message.answer(
            "❌ Ошибка при создании. Попробуйте ещё раз.",
            reply_markup=main_menu_keyboard(is_admin=True),
        )


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
            "\n".join(lines), parse_mode="HTML",
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
                "🗂 Коллекций нет. Создайте первую!",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="➕ Добавить коллекцию", callback_data="adm:add_collection")],
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
            [InlineKeyboardButton(text="➕ Добавить коллекцию", callback_data="adm:add_collection")],
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
