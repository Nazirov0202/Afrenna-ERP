from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db.models import UserRole
from db.session import AsyncSessionLocal
from services.inventory_service import InventoryService
from services.order_service import OrderService
from services.user_service import UserService
from utils.helpers import format_qty
from utils.keyboards import kb_confirm_cancel, kb_orders_list
from utils.states import InventoryStates

router = Router()

INVENTORY_ROLES = (UserRole.ADMIN, UserRole.MANAGER, UserRole.FABRIC_HEAD)


def kb_items_list(items):
    builder = InlineKeyboardBuilder()
    for item in items:
        builder.button(
            text=f"🧵 {item.item_name} — {item.qty_on_hand} {item.unit}",
            callback_data=f"inv_item:{item.id}",
        )
    builder.button(text="➕ Yangi mato qo'shish", callback_data="inv_new_item")
    builder.button(text="❌ Bekor", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


# ─── Qoldiq ko'rish ───────────────────────────────────────────────────────────

@router.message(F.text == "📦 Qoldiq ko'rish")
async def inventory_view(message: Message):
    async with AsyncSessionLocal() as session:
        user = await UserService.get_by_telegram_id(session, message.from_user.id)
        if not user or user.role not in INVENTORY_ROLES:
            await message.answer("⛔ Ruxsatingiz yo'q.")
            return
        items = await InventoryService.get_all(session)

    if not items:
        await message.answer("📦 Ombor bo'sh. Avval mato kirim qiling.")
        return

    text = "📦 <b>Ombor qoldiqlari:</b>\n\n"
    for item in items:
        text += f"🧵 {item.item_name}: <b>{item.qty_on_hand} {item.unit}</b>\n"
    await message.answer(text, parse_mode="HTML")


# ─── Mato kirim ───────────────────────────────────────────────────────────────

@router.message(F.text == "📥 Mato kirim")
async def inventory_in_start(message: Message, state: FSMContext):
    async with AsyncSessionLocal() as session:
        user = await UserService.get_by_telegram_id(session, message.from_user.id)
        if not user or user.role not in INVENTORY_ROLES:
            await message.answer("⛔ Ruxsatingiz yo'q.")
            return
        items = await InventoryService.get_all(session)

    await state.update_data(action="in", performer_tg_id=message.from_user.id)
    await message.answer(
        "📥 <b>Mato kirim</b>\n\nQaysi matoni kiritmoqchisiz?",
        parse_mode="HTML",
        reply_markup=kb_items_list(items),
    )
    await state.set_state(InventoryStates.select_item)


@router.callback_query(InventoryStates.select_item, F.data.startswith("inv_item:"))
async def inv_item_selected(callback: CallbackQuery, state: FSMContext):
    item_id = int(callback.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        item = await InventoryService.get_by_id(session, item_id)
    await state.update_data(item_id=item_id, item_name=item.item_name, unit=item.unit)
    await callback.message.edit_text(
        f"🧵 Mato: <b>{item.item_name}</b>\n"
        f"📦 Joriy qoldiq: <b>{item.qty_on_hand} {item.unit}</b>\n\n"
        f"Necha {item.unit} kirim qilinadi?",
        parse_mode="HTML",
    )
    await state.set_state(InventoryStates.enter_qty)


@router.callback_query(InventoryStates.select_item, F.data == "inv_new_item")
async def inv_new_item(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Yangi mato nomini kiriting:")
    await state.set_state(InventoryStates.enter_item_name)


@router.message(InventoryStates.enter_item_name, F.text)
async def inv_item_name(message: Message, state: FSMContext):
    await state.update_data(item_name=message.text.strip(), item_id=None, unit="metr")
    await message.answer(
        f"O'lchov birligini kiriting (metr, kg, dona — standart: metr):"
    )
    await state.set_state(InventoryStates.enter_unit)


@router.message(InventoryStates.enter_unit, F.text)
async def inv_item_unit(message: Message, state: FSMContext):
    unit = message.text.strip() or "metr"
    await state.update_data(unit=unit)
    await message.answer(f"Necha {unit} kirim qilinadi?")
    await state.set_state(InventoryStates.enter_qty)


@router.message(InventoryStates.enter_qty, F.text)
async def inv_enter_qty(message: Message, state: FSMContext):
    try:
        qty = float(message.text.strip().replace(",", "."))
        if qty <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Iltimos, musbat son kiriting.")
        return

    data = await state.get_data()
    await state.update_data(qty=qty)

    action = data.get("action", "in")
    action_label = "📥 Kirim" if action == "in" else "📤 Chiqim"
    item_name = data.get("item_name", "—")
    unit = data.get("unit", "metr")

    if action == "out":
        await message.answer(
            f"{action_label}: <b>{qty} {unit}</b> — {item_name}\n\n"
            f"Qaysi zakaz uchun?",
            parse_mode="HTML",
        )
        async with AsyncSessionLocal() as session:
            orders = await OrderService.get_open_orders(session)
        await message.answer(
            "Zakaz tanlang:",
            reply_markup=kb_orders_list(orders, prefix="inv_order"),
        )
        await state.set_state(InventoryStates.select_order)
    else:
        await message.answer(
            f"{action_label}: <b>{qty} {unit}</b> — <b>{item_name}</b>\n\nTasdiqlaysizmi?",
            parse_mode="HTML",
            reply_markup=kb_confirm_cancel(),
        )
        await state.set_state(InventoryStates.confirm)


@router.callback_query(InventoryStates.select_order, F.data.startswith("inv_order:"))
async def inv_order_selected(callback: CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    await state.update_data(order_id=order_id)
    await callback.message.edit_text(
        f"📤 Chiqim: <b>{data['qty']} {data['unit']}</b> — {data['item_name']}\n\n"
        f"Tasdiqlaysizmi?",
        parse_mode="HTML",
        reply_markup=kb_confirm_cancel(),
    )
    await state.set_state(InventoryStates.confirm)


@router.callback_query(InventoryStates.confirm, F.data == "confirm")
async def inv_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    async with AsyncSessionLocal() as session:
        performer = await UserService.get_by_telegram_id(session, callback.from_user.id)

        if data.get("item_id"):
            item = await InventoryService.get_by_id(session, data["item_id"])
        else:
            item = await InventoryService.create_item(session, data["item_name"], data["unit"])

        try:
            if data.get("action") == "out":
                order = await OrderService.get_by_id(session, data.get("order_id"))
                await InventoryService.deduct_stock(
                    session, item, data["qty"], performer, order
                )
                action_text = "📤 Chiqim"
            else:
                await InventoryService.add_stock(session, item, data["qty"], performer)
                action_text = "📥 Kirim"
        except ValueError as e:
            await callback.answer(str(e), show_alert=True)
            return

    await callback.message.edit_text(
        f"✅ <b>{action_text} muvaffaqiyatli!</b>\n\n"
        f"🧵 Mato: {item.item_name}\n"
        f"📦 Miqdor: <b>{data['qty']} {data['unit']}</b>\n"
        f"📊 Yangi qoldiq: <b>{item.qty_on_hand} {item.unit}</b>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(InventoryStates.confirm, F.data == "cancel")
async def inv_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Bekor qilindi.")
    await callback.answer()


# ─── Mato chiqim ──────────────────────────────────────────────────────────────

@router.message(F.text == "📤 Mato chiqim")
async def inventory_out_start(message: Message, state: FSMContext):
    async with AsyncSessionLocal() as session:
        user = await UserService.get_by_telegram_id(session, message.from_user.id)
        if not user or user.role not in INVENTORY_ROLES:
            await message.answer("⛔ Ruxsatingiz yo'q.")
            return
        items = await InventoryService.get_all(session)

    if not items:
        await message.answer("📦 Ombor bo'sh.")
        return

    await state.update_data(action="out", performer_tg_id=message.from_user.id)
    await message.answer(
        "📤 <b>Mato chiqim</b>\n\nQaysi matoni chiqarmoqchisiz?",
        parse_mode="HTML",
        reply_markup=kb_items_list(items),
    )
    await state.set_state(InventoryStates.select_item)


# ─── Tarix ────────────────────────────────────────────────────────────────────

@router.message(F.text == "📜 Tarix")
async def inventory_history(message: Message):
    async with AsyncSessionLocal() as session:
        user = await UserService.get_by_telegram_id(session, message.from_user.id)
        if not user or user.role not in INVENTORY_ROLES:
            await message.answer("⛔ Ruxsatingiz yo'q.")
            return
        logs = await InventoryService.get_logs(session, limit=20)

    if not logs:
        await message.answer("📜 Tarix bo'sh.")
        return

    text = "📜 <b>So'nggi 20 ta harakat:</b>\n\n"
    for log in logs:
        icon = "📥" if log.action.value == "in" else "📤"
        text += (
            f"{icon} {log.qty} — "
            f"{log.created_at.strftime('%d.%m %H:%M')}\n"
        )
    await message.answer(text, parse_mode="HTML")
