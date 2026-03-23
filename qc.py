from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from db.models import UserRole
from db.session import AsyncSessionLocal
from services.order_service import OrderService
from services.qc_service import QCService
from services.user_service import UserService
from utils.helpers import format_qty
from utils.keyboards import kb_confirm_cancel, kb_orders_list
from utils.states import QCStates

router = Router()

QC_ROLES = (UserRole.ADMIN, UserRole.MANAGER, UserRole.QC)


# ─── Tekshirish boshlash ──────────────────────────────────────────────────────

@router.message(F.text.in_({"🔍 Tekshirish", "✅ Qabul qilish", "❌ Rad etish"}))
async def qc_start(message: Message, state: FSMContext):
    async with AsyncSessionLocal() as session:
        user = await UserService.get_by_telegram_id(session, message.from_user.id)
        if not user or user.role not in QC_ROLES:
            await message.answer("⛔ Ruxsatingiz yo'q.")
            return
        orders = await OrderService.get_open_orders(session)

    if not orders:
        await message.answer("📭 Tekshirish uchun zakazlar yo'q.")
        return

    await state.update_data(inspector_tg_id=message.from_user.id)
    await message.answer(
        "🔍 <b>Sifat nazorati</b>\n\nQaysi zakazni tekshiryapsiz?",
        parse_mode="HTML",
        reply_markup=kb_orders_list(orders, prefix="qc_order"),
    )
    await state.set_state(QCStates.select_order)


@router.callback_query(QCStates.select_order, F.data.startswith("qc_order:"))
async def qc_order_selected(callback: CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        order = await OrderService.get_by_id(session, order_id)

    await state.update_data(order_id=order_id, order_code=order.order_code)
    await callback.message.edit_text(
        f"🔍 Zakaz: <b>{order.order_code}</b> — {order.model_name}\n\n"
        f"✅ Necha dona <b>qabul qilindi</b>?",
        parse_mode="HTML",
    )
    await state.set_state(QCStates.enter_accepted)


@router.message(QCStates.enter_accepted, F.text)
async def qc_enter_accepted(message: Message, state: FSMContext):
    try:
        accepted = int(message.text.strip())
        if accepted < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Musbat butun son kiriting.")
        return

    await state.update_data(accepted_qty=accepted)
    await message.answer(f"❌ Necha dona <b>rad etildi</b> (brak)?", parse_mode="HTML")
    await state.set_state(QCStates.enter_rejected)


@router.message(QCStates.enter_rejected, F.text)
async def qc_enter_rejected(message: Message, state: FSMContext):
    try:
        rejected = int(message.text.strip())
        if rejected < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Musbat butun son kiriting.")
        return

    await state.update_data(rejected_qty=rejected)

    if rejected > 0:
        await message.answer(
            "📝 Brak sababini kiriting (qisqacha, masalan: «Tikuv noto'g'ri»):"
        )
        await state.set_state(QCStates.enter_reason)
    else:
        await _show_qc_summary(message, state)


@router.message(QCStates.enter_reason, F.text)
async def qc_enter_reason(message: Message, state: FSMContext):
    await state.update_data(reject_reason=message.text.strip())
    await _show_qc_summary(message, state)


async def _show_qc_summary(message: Message, state: FSMContext):
    data = await state.get_data()
    accepted = data.get("accepted_qty", 0)
    rejected = data.get("rejected_qty", 0)
    reason = data.get("reject_reason", "—")

    await message.answer(
        f"📋 <b>QC natijasi:</b>\n\n"
        f"📋 Zakaz: <b>{data['order_code']}</b>\n"
        f"✅ Qabul: <b>{format_qty(accepted)}</b>\n"
        f"❌ Brak: <b>{format_qty(rejected)}</b>\n"
        f"📝 Sabab: {reason if rejected > 0 else '—'}\n\n"
        f"Tasdiqlaysizmi?",
        parse_mode="HTML",
        reply_markup=kb_confirm_cancel(),
    )
    await state.set_state(QCStates.confirm)


@router.callback_query(QCStates.confirm, F.data == "confirm")
async def qc_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    async with AsyncSessionLocal() as session:
        inspector = await UserService.get_by_telegram_id(session, callback.from_user.id)
        order = await OrderService.get_by_id(session, data["order_id"])
        result = await QCService.record_result(
            session,
            inspector=inspector,
            order=order,
            accepted_qty=data["accepted_qty"],
            rejected_qty=data["rejected_qty"],
            reject_reason=data.get("reject_reason"),
        )

    await callback.message.edit_text(
        f"✅ <b>QC natijasi saqlandi!</b>\n\n"
        f"📋 Zakaz: {data['order_code']}\n"
        f"✅ Qabul: {format_qty(result.accepted_qty)}\n"
        f"❌ Brak: {format_qty(result.rejected_qty)}",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(QCStates.confirm, F.data == "cancel")
async def qc_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Bekor qilindi.")
    await callback.answer()


# ─── QC kunlik hisobot ────────────────────────────────────────────────────────

@router.message(F.text == "📊 Hisobot")
async def qc_report(message: Message):
    async with AsyncSessionLocal() as session:
        user = await UserService.get_by_telegram_id(session, message.from_user.id)
        if not user or user.role not in QC_ROLES:
            await message.answer("⛔ Ruxsatingiz yo'q.")
            return
        results = await QCService.get_today_results(session, user)

    if not results:
        await message.answer("📊 Bugun hali QC natijasi yo'q.")
        return

    total_accepted = sum(r.accepted_qty for r in results)
    total_rejected = sum(r.rejected_qty for r in results)
    text = (
        f"📊 <b>Bugungi QC natijalar</b>\n\n"
        f"✅ Jami qabul: <b>{format_qty(total_accepted)}</b>\n"
        f"❌ Jami brak: <b>{format_qty(total_rejected)}</b>\n"
        f"📋 Tekshirishlar soni: {len(results)}"
    )
    await message.answer(text, parse_mode="HTML")
