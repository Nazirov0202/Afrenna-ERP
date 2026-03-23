from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db.models import UserRole
from db.session import AsyncSessionLocal
from services.order_service import OrderService
from services.transfer_service import TransferService
from services.user_service import UserService
from utils.helpers import format_qty
from utils.keyboards import kb_confirm_cancel, kb_orders_list, kb_transfer_confirm
from utils.states import TransferStates

router = Router()

TRANSFER_ROLES = (
    UserRole.ADMIN, UserRole.MANAGER,
    UserRole.RAZDACHA_HEAD, UserRole.RAZDACHA_HELPER,
)


def kb_users_list(users):
    builder = InlineKeyboardBuilder()
    for u in users:
        builder.button(
            text=f"👤 {u.full_name}",
            callback_data=f"transfer_to:{u.id}",
        )
    builder.button(text="❌ Bekor", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


# ─── Transfer yaratish ────────────────────────────────────────────────────────

@router.message(F.text == "📦 Topshirish")
async def transfer_start(message: Message, state: FSMContext):
    async with AsyncSessionLocal() as session:
        user = await UserService.get_by_telegram_id(session, message.from_user.id)
        if not user or user.role not in TRANSFER_ROLES:
            await message.answer("⛔ Ruxsatingiz yo'q.")
            return
        orders = await OrderService.get_open_orders(session)

    if not orders:
        await message.answer("📭 Faol zakazlar yo'q.")
        return

    await state.update_data(sender_tg_id=message.from_user.id)
    await message.answer(
        "📦 <b>Mahsulot topshirish</b>\n\nQaysi zakaz bo'yicha?",
        parse_mode="HTML",
        reply_markup=kb_orders_list(orders, prefix="tr_order"),
    )
    await state.set_state(TransferStates.select_order)


@router.callback_query(TransferStates.select_order, F.data.startswith("tr_order:"))
async def transfer_order_selected(callback: CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        order = await OrderService.get_by_id(session, order_id)
        # Get all active users except sender
        all_users = await UserService.get_all_active(session)
        recipients = [u for u in all_users if u.telegram_id != callback.from_user.id]

    await state.update_data(order_id=order_id, order_code=order.order_code)
    await callback.message.edit_text(
        f"📋 Zakaz: <b>{order.order_code}</b>\n\nKimga topshirasiz?",
        parse_mode="HTML",
        reply_markup=kb_users_list(recipients),
    )
    await state.set_state(TransferStates.select_recipient)


@router.callback_query(TransferStates.select_recipient, F.data.startswith("transfer_to:"))
async def transfer_recipient_selected(callback: CallbackQuery, state: FSMContext):
    to_user_id = int(callback.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        recipient = await UserService.get_by_id(session, to_user_id)

    await state.update_data(to_user_id=to_user_id, to_user_name=recipient.full_name)
    await callback.message.edit_text(
        f"👤 Qabul qiluvchi: <b>{recipient.full_name}</b>\n\nNecha dona topshirasiz?",
        parse_mode="HTML",
    )
    await state.set_state(TransferStates.enter_qty)


@router.message(TransferStates.enter_qty, F.text)
async def transfer_enter_qty(message: Message, state: FSMContext):
    try:
        qty = int(message.text.strip())
        if qty <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Musbat butun son kiriting.")
        return

    data = await state.get_data()
    await state.update_data(qty=qty)
    await message.answer(
        f"📦 <b>Transfer:</b>\n\n"
        f"📋 Zakaz: {data['order_code']}\n"
        f"👤 Kimga: {data['to_user_name']}\n"
        f"🔢 Miqdor: <b>{format_qty(qty)}</b>\n\n"
        f"Tasdiqlaysizmi?",
        parse_mode="HTML",
        reply_markup=kb_confirm_cancel(),
    )
    await state.set_state(TransferStates.confirm)


@router.callback_query(TransferStates.confirm, F.data == "confirm")
async def transfer_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    async with AsyncSessionLocal() as session:
        sender = await UserService.get_by_telegram_id(session, callback.from_user.id)
        recipient = await UserService.get_by_id(session, data["to_user_id"])
        order = await OrderService.get_by_id(session, data["order_id"])
        transfer = await TransferService.create(
            session, order, sender, recipient, data["qty"]
        )

    # Notify recipient
    try:
        from aiogram import Bot
        from config import settings
        bot = Bot(token=settings.BOT_TOKEN)
        await bot.send_message(
            recipient.telegram_id,
            f"📦 <b>Yangi topshiriq keldi!</b>\n\n"
            f"📋 Zakaz: <b>{order.order_code}</b>\n"
            f"👤 Kimdan: {sender.full_name}\n"
            f"🔢 Miqdor: <b>{format_qty(data['qty'])}</b>\n"
            f"🏷 Batch: {transfer.batch_code}\n\n"
            f"Qabul qilasizmi?",
            parse_mode="HTML",
            reply_markup=kb_transfer_confirm(transfer.id),
        )
        await bot.session.close()
    except Exception:
        pass  # Notification failure should not break the flow

    await callback.message.edit_text(
        f"✅ <b>Transfer yuborildi!</b>\n\n"
        f"📋 {order.order_code} — {format_qty(data['qty'])} dona\n"
        f"👤 {data['to_user_name']} tasdiqlashini kuting.\n"
        f"🏷 Batch: {transfer.batch_code}",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(TransferStates.confirm, F.data == "cancel")
async def transfer_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Bekor qilindi.")
    await callback.answer()


# ─── Transfer qabul qilish / rad etish (recipient) ───────────────────────────

@router.callback_query(F.data.startswith("transfer_accept:"))
async def transfer_accept(callback: CallbackQuery):
    transfer_id = int(callback.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        transfer = await TransferService.get_by_id(session, transfer_id)
        if not transfer or transfer.status.value != "pending":
            await callback.answer("❌ Transfer allaqachon qayta ishlangan.", show_alert=True)
            return
        transfer = await TransferService.accept(session, transfer)

    await callback.message.edit_text(
        f"✅ <b>Transfer qabul qilindi!</b>\n\n"
        f"🏷 Batch: {transfer.batch_code}\n"
        f"🔢 Miqdor: {format_qty(transfer.qty)} dona",
        parse_mode="HTML",
    )
    await callback.answer("✅ Qabul qilindi!")


@router.callback_query(F.data.startswith("transfer_reject:"))
async def transfer_reject(callback: CallbackQuery):
    transfer_id = int(callback.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        transfer = await TransferService.get_by_id(session, transfer_id)
        if not transfer or transfer.status.value != "pending":
            await callback.answer("❌ Transfer allaqachon qayta ishlangan.", show_alert=True)
            return
        transfer = await TransferService.reject(session, transfer)

    await callback.message.edit_text(
        f"❌ <b>Transfer rad etildi.</b>\n\n"
        f"🏷 Batch: {transfer.batch_code}",
        parse_mode="HTML",
    )
    await callback.answer("❌ Rad etildi.")


# ─── Kutayotgan transferlar ───────────────────────────────────────────────────

@router.message(F.text == "✅ Tasdiqlash")
async def pending_transfers(message: Message):
    async with AsyncSessionLocal() as session:
        user = await UserService.get_by_telegram_id(session, message.from_user.id)
        if not user:
            await message.answer("❌ Foydalanuvchi topilmadi.")
            return
        transfers = await TransferService.get_pending_for_user(session, user)

    if not transfers:
        await message.answer("📭 Kutayotgan transferlar yo'q.")
        return

    for tr in transfers:
        await message.answer(
            f"📦 <b>Kelgan topshiriq</b>\n\n"
            f"🔢 Miqdor: <b>{format_qty(tr.qty)}</b>\n"
            f"🏷 Batch: {tr.batch_code}",
            parse_mode="HTML",
            reply_markup=kb_transfer_confirm(tr.id),
        )
