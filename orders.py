from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from db.models import UserRole
from db.session import AsyncSessionLocal
from services.order_service import OrderService
from services.user_service import UserService
from utils.helpers import format_money, format_qty, order_status_label
from utils.keyboards import kb_confirm_cancel, kb_orders_list
from utils.states import OrderStates

router = Router()

ADMIN_ROLES = (UserRole.ADMIN, UserRole.MANAGER, UserRole.SALES)


async def _get_authed_user(tg_id: int, allowed_roles: tuple):
    """Helper: fetch user and check role. Returns user or None."""
    async with AsyncSessionLocal() as session:
        user = await UserService.get_by_telegram_id(session, tg_id)
    if not user or user.role not in allowed_roles:
        return None
    return user


# ─── Yangi zakaz ochish ───────────────────────────────────────────────────────

@router.message(F.text == "📋 Zakazlar")
async def orders_menu(message: Message):
    async with AsyncSessionLocal() as session:
        user = await UserService.get_by_telegram_id(session, message.from_user.id)
        if not user or user.role not in ADMIN_ROLES:
            await message.answer("⛔ Ruxsatingiz yo'q.")
            return
        orders = await OrderService.get_all(session)

    if not orders:
        await message.answer(
            "📋 Hozircha zakazlar yo'q.\n\n"
            "Yangi zakaz ochish uchun: /neworder"
        )
        return

    text = "📋 <b>Barcha zakazlar:</b>\n\n"
    for o in orders[:15]:
        text += (
            f"• <b>{o.order_code}</b> — {o.model_name}\n"
            f"  {order_status_label(o.status.value)} | "
            f"{o.progress_percent}% | {format_qty(o.remaining_qty)} qolgan\n\n"
        )
    await message.answer(text, parse_mode="HTML")


@router.message(F.text.startswith("/neworder") | (F.text == "➕ Yangi zakaz"))
async def cmd_new_order(message: Message, state: FSMContext):
    async with AsyncSessionLocal() as session:
        user = await UserService.get_by_telegram_id(session, message.from_user.id)
    if not user or user.role not in ADMIN_ROLES:
        await message.answer("⛔ Ruxsatingiz yo'q.")
        return

    await state.update_data(creator_id=user.id)
    await message.answer(
        "📋 <b>Yangi zakaz ochish</b>\n\n"
        "1️⃣ Model nomini kiriting (masalan: «Dress A-123»):",
        parse_mode="HTML",
    )
    await state.set_state(OrderStates.waiting_model)


@router.message(OrderStates.waiting_model, F.text)
async def order_model(message: Message, state: FSMContext):
    await state.update_data(model_name=message.text.strip())
    await message.answer("2️⃣ Mato turini kiriting (masalan: «Chit, Shiftom»):")
    await state.set_state(OrderStates.waiting_fabric)


@router.message(OrderStates.waiting_fabric, F.text)
async def order_fabric(message: Message, state: FSMContext):
    await state.update_data(fabric_type=message.text.strip())
    await message.answer("3️⃣ Umumiy dona sonini kiriting (masalan: «500»):")
    await state.set_state(OrderStates.waiting_qty)


@router.message(OrderStates.waiting_qty, F.text)
async def order_qty(message: Message, state: FSMContext):
    try:
        qty = int(message.text.strip())
        if qty <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Iltimos, musbat butun son kiriting (masalan: 500).")
        return
    await state.update_data(total_qty=qty)
    await message.answer("4️⃣ Bir donaning narxini kiriting (so'mda, masalan: «2500»):")
    await state.set_state(OrderStates.waiting_price)


@router.message(OrderStates.waiting_price, F.text)
async def order_price(message: Message, state: FSMContext):
    try:
        price = float(message.text.strip().replace(",", ".").replace(" ", ""))
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Iltimos, to'g'ri narx kiriting (masalan: 2500).")
        return
    await state.update_data(price_per_unit=price)
    await message.answer(
        "5️⃣ Mijoz nomini kiriting (ixtiyoriy, o'tkazish uchun « - » yozing):"
    )
    await state.set_state(OrderStates.waiting_client)


@router.message(OrderStates.waiting_client, F.text)
async def order_client(message: Message, state: FSMContext):
    client = message.text.strip()
    if client == "-":
        client = None
    await state.update_data(client_name=client)

    data = await state.get_data()
    summary = (
        f"📋 <b>Zakaz ma'lumotlari:</b>\n\n"
        f"🏷 Model: <b>{data['model_name']}</b>\n"
        f"🧵 Mato: <b>{data['fabric_type']}</b>\n"
        f"🔢 Miqdor: <b>{format_qty(data['total_qty'])}</b>\n"
        f"💰 Narx: <b>{format_money(data['price_per_unit'])}</b>/dona\n"
        f"👔 Mijoz: <b>{client or '—'}</b>\n\n"
        f"Tasdiqlaysizmi?"
    )
    await message.answer(summary, parse_mode="HTML", reply_markup=kb_confirm_cancel())
    await state.set_state(OrderStates.confirm)


@router.callback_query(OrderStates.confirm, F.data == "confirm")
async def confirm_order(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    async with AsyncSessionLocal() as session:
        order = await OrderService.create(
            session,
            model_name=data["model_name"],
            fabric_type=data["fabric_type"],
            total_qty=data["total_qty"],
            price_per_unit=data["price_per_unit"],
            created_by_id=data["creator_id"],
            client_name=data.get("client_name"),
        )

    await callback.message.edit_text(
        f"✅ <b>Zakaz yaratildi!</b>\n\n"
        f"📋 Kod: <b>{order.order_code}</b>\n"
        f"🏷 Model: {order.model_name}\n"
        f"🔢 Miqdor: {format_qty(order.total_qty)}\n"
        f"💰 Narx: {format_money(order.price_per_unit)}/dona",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(OrderStates.confirm, F.data == "cancel")
async def cancel_order(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Zakaz ochish bekor qilindi.")
    await callback.answer()


# ─── Zakaz holati ─────────────────────────────────────────────────────────────

@router.message(F.text == "📊 Zakaz holati")
async def order_status(message: Message):
    async with AsyncSessionLocal() as session:
        orders = await OrderService.get_open_orders(session)

    if not orders:
        await message.answer("📭 Faol zakazlar yo'q.")
        return

    await message.answer(
        "Qaysi zakaz haqida ma'lumot olmoqchisiz?",
        reply_markup=kb_orders_list(orders, prefix="order_info"),
    )


@router.callback_query(F.data.startswith("order_info:"))
async def show_order_info(callback: CallbackQuery):
    order_id = int(callback.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        order = await OrderService.get_by_id(session, order_id)

    if not order:
        await callback.answer("❌ Zakaz topilmadi.")
        return

    progress_bar = _progress_bar(order.progress_percent)
    text = (
        f"📋 <b>{order.order_code}</b>\n\n"
        f"🏷 Model: {order.model_name}\n"
        f"🧵 Mato: {order.fabric_type or '—'}\n"
        f"👔 Mijoz: {order.client_name or '—'}\n"
        f"📊 Holat: {order_status_label(order.status.value)}\n\n"
        f"🔢 Jami: {format_qty(order.total_qty)}\n"
        f"✅ Bajarildi: {format_qty(order.completed_qty)}\n"
        f"⏳ Qoldi: {format_qty(order.remaining_qty)}\n\n"
        f"{progress_bar} {order.progress_percent}%\n"
        f"💰 Narx: {format_money(order.price_per_unit)}/dona"
    )
    await callback.message.edit_text(text, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "cancel")
async def cancel_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Bekor qilindi.")
    await callback.answer()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _progress_bar(percent: float, length: int = 10) -> str:
    filled = round(percent / 100 * length)
    return "🟩" * filled + "⬜" * (length - filled)
