from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from db.models import UserRole
from db.session import AsyncSessionLocal
from services.order_service import OrderService
from services.report_service import ReportService
from services.user_service import UserService
from services.work_service import WorkService
from utils.helpers import format_money, format_qty
from utils.keyboards import kb_confirm_cancel, kb_orders_list
from utils.states import WorkStates

router = Router()

WORKER_ROLES = (
    UserRole.SEWER, UserRole.CUTTER, UserRole.NAITEL,
    UserRole.IRONER, UserRole.PACKER,
    UserRole.ADMIN, UserRole.MANAGER,
)


# ─── Ishni boshlash (zakaz tanlash) ──────────────────────────────────────────

@router.message(F.text == "🟢 Ishni boshlash")
async def start_work(message: Message, state: FSMContext):
    async with AsyncSessionLocal() as session:
        user = await UserService.get_by_telegram_id(session, message.from_user.id)
        if not user or user.role not in WORKER_ROLES:
            await message.answer("⛔ Ruxsatingiz yo'q.")
            return
        orders = await OrderService.get_open_orders(session)

    if not orders:
        await message.answer("📭 Hozircha ochiq zakazlar yo'q.")
        return

    await message.answer(
        "📋 Qaysi zakazda ishlayapsiz?",
        reply_markup=kb_orders_list(orders, prefix="work_order"),
    )
    await state.set_state(WorkStates.select_order)


@router.callback_query(WorkStates.select_order, F.data.startswith("work_order:"))
async def work_order_selected(callback: CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        order = await OrderService.get_by_id(session, order_id)

    if not order or order.remaining_qty <= 0:
        await callback.answer("❌ Bu zakaz yakunlangan yoki topilmadi.")
        return

    await state.update_data(order_id=order_id, order_code=order.order_code,
                            order_name=order.model_name,
                            remaining=order.remaining_qty,
                            price=float(order.price_per_unit))
    await callback.message.edit_text(
        f"📋 Zakaz: <b>{order.order_code}</b> — {order.model_name}\n"
        f"⏳ Qolgan: <b>{format_qty(order.remaining_qty)}</b>\n\n"
        f"Necha dona topshirmoqchisiz?",
        parse_mode="HTML",
    )
    await state.set_state(WorkStates.enter_qty)


# ─── Ishni topshirish ─────────────────────────────────────────────────────────

@router.message(F.text == "✅ Ishni topshirish")
async def submit_work_start(message: Message, state: FSMContext):
    async with AsyncSessionLocal() as session:
        user = await UserService.get_by_telegram_id(session, message.from_user.id)
        if not user or user.role not in WORKER_ROLES:
            await message.answer("⛔ Ruxsatingiz yo'q.")
            return
        orders = await OrderService.get_open_orders(session)

    if not orders:
        await message.answer("📭 Hozircha ochiq zakazlar yo'q.")
        return

    await message.answer(
        "📋 Qaysi zakaz bo'yicha topshiryapsiz?",
        reply_markup=kb_orders_list(orders, prefix="work_order"),
    )
    await state.set_state(WorkStates.select_order)


@router.message(WorkStates.enter_qty, F.text)
async def work_enter_qty(message: Message, state: FSMContext):
    try:
        qty = int(message.text.strip())
        if qty <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Iltimos, musbat butun son kiriting (masalan: 50).")
        return

    data = await state.get_data()
    if qty > data["remaining"]:
        await message.answer(
            f"❌ Zakazda faqat <b>{format_qty(data['remaining'])}</b> qolgan.\n"
            f"Kamroq son kiriting.",
            parse_mode="HTML",
        )
        return

    earned = qty * data["price"]
    await state.update_data(qty=qty, earned=earned)

    await message.answer(
        f"📋 Zakaz: <b>{data['order_code']}</b>\n"
        f"✅ Topshiriladi: <b>{format_qty(qty)}</b>\n"
        f"💰 Hisoblanadi: <b>{format_money(earned)}</b>\n\n"
        f"Tasdiqlaysizmi?",
        parse_mode="HTML",
        reply_markup=kb_confirm_cancel(),
    )
    await state.set_state(WorkStates.confirm)


@router.callback_query(WorkStates.confirm, F.data == "confirm")
async def confirm_work(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    async with AsyncSessionLocal() as session:
        user = await UserService.get_by_telegram_id(session, callback.from_user.id)
        order = await OrderService.get_by_id(session, data["order_id"])

        try:
            tx, earned = await WorkService.submit_work(session, user, order, data["qty"])
        except ValueError as e:
            await callback.answer(str(e), show_alert=True)
            return

        new_balance = float(user.balance)

    await callback.message.edit_text(
        f"✅ <b>Muvaffaqiyatli topshirildi!</b>\n\n"
        f"📋 Zakaz: {data['order_code']}\n"
        f"🔢 Dona: {format_qty(data['qty'])}\n"
        f"💰 Hisoblandi: {format_money(earned)}\n"
        f"💼 Balans: {format_money(new_balance)}",
        parse_mode="HTML",
    )
    await callback.answer("✅ Tayyor!")


@router.callback_query(WorkStates.confirm, F.data == "cancel")
async def cancel_work(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Bekor qilindi.")
    await callback.answer()


# ─── Balans va kunlik hisobot ─────────────────────────────────────────────────

@router.message(F.text == "💰 Mening balansim")
async def my_balance(message: Message):
    async with AsyncSessionLocal() as session:
        user = await UserService.get_by_telegram_id(session, message.from_user.id)
        if not user:
            await message.answer("❌ Foydalanuvchi topilmadi. /start bosing.")
            return

    await message.answer(
        f"💼 <b>Mening hisobim</b>\n\n"
        f"👤 {user.full_name}\n"
        f"💰 Joriy balans: <b>{format_money(user.balance)}</b>",
        parse_mode="HTML",
    )


@router.message(F.text == "📈 Kunlik hisobot")
async def daily_report(message: Message):
    async with AsyncSessionLocal() as session:
        user = await UserService.get_by_telegram_id(session, message.from_user.id)
        if not user:
            await message.answer("❌ Foydalanuvchi topilmadi.")
            return
        report = await ReportService.user_daily_report(session, user)

    if report["tx_count"] == 0:
        await message.answer(
            f"📈 <b>Bugungi hisobot</b>\n\n"
            f"Bugun hali hech narsa topshirilmagan.",
            parse_mode="HTML",
        )
        return

    await message.answer(
        f"📈 <b>Bugungi hisobot</b>\n\n"
        f"👤 {report['user'].full_name}\n"
        f"📅 Sana: {report['date'].strftime('%d.%m.%Y')}\n\n"
        f"✅ Topshirildi: <b>{format_qty(report['total_qty'])}</b>\n"
        f"💰 Hisoblandi: <b>{format_money(report['total_earned'])}</b>\n"
        f"💼 Jami balans: <b>{format_money(report['balance'])}</b>",
        parse_mode="HTML",
    )
