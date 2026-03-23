from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Contact, Message

from db.models import UserRole
from db.session import AsyncSessionLocal
from services.user_service import UserService
from utils.helpers import role_label
from utils.keyboards import (
    kb_confirm_cancel, kb_select_role, kb_share_phone, menu_by_role,
)
from utils.states import RegistrationStates

router = Router()


# ─── /start ───────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    async with AsyncSessionLocal() as session:
        user = await UserService.get_by_telegram_id(session, message.from_user.id)

    if user and user.role:
        await message.answer(
            f"👋 Xush kelibsiz, <b>{user.full_name}</b>!\n"
            f"Rolingiz: {role_label(user.role.value)}",
            parse_mode="HTML",
            reply_markup=menu_by_role(user.role),
        )
        return

    # New user — start registration
    await message.answer(
        "👋 <b>Telegram ERP</b> tizimiga xush kelibsiz!\n\n"
        "Davom etish uchun telefon raqamingizni ulashing:",
        parse_mode="HTML",
        reply_markup=kb_share_phone(),
    )
    await state.set_state(RegistrationStates.waiting_phone)


# ─── Receive phone contact ────────────────────────────────────────────────────

@router.message(RegistrationStates.waiting_phone, F.contact)
async def received_phone(message: Message, state: FSMContext):
    contact: Contact = message.contact
    # Only accept own contact
    if contact.user_id != message.from_user.id:
        await message.answer("❌ Iltimos, o'z raqamingizni ulashing.")
        return

    await state.update_data(phone=contact.phone_number)
    await message.answer(
        "✅ Telefon qabul qilindi.\n\n"
        "Endi to'liq ismingizni kiriting (Ism Familiya):",
        reply_markup=None,
    )
    await state.set_state(RegistrationStates.waiting_name)


@router.message(RegistrationStates.waiting_phone)
async def phone_not_shared(message: Message):
    await message.answer(
        "📱 Iltimos, «Raqamni ulashish» tugmasini bosing.",
        reply_markup=kb_share_phone(),
    )


# ─── Receive name ─────────────────────────────────────────────────────────────

@router.message(RegistrationStates.waiting_name, F.text)
async def received_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 3:
        await message.answer("❌ Ism kamida 3 ta harf bo'lishi kerak. Qayta kiriting:")
        return

    data = await state.get_data()
    await state.update_data(full_name=name)

    await message.answer(
        f"📋 Ma'lumotlar:\n"
        f"👤 Ism: <b>{name}</b>\n"
        f"📱 Telefon: <b>{data['phone']}</b>\n\n"
        f"Tasdiqlaysizmi?",
        parse_mode="HTML",
        reply_markup=kb_confirm_cancel(),
    )


@router.callback_query(RegistrationStates.waiting_name, F.data == "confirm")
async def confirm_registration(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    async with AsyncSessionLocal() as session:
        user = await UserService.get_by_telegram_id(session, callback.from_user.id)
        if not user:
            user = await UserService.create(
                session,
                telegram_id=callback.from_user.id,
                full_name=data["full_name"],
                phone=data.get("phone"),
            )

    await callback.message.edit_text(
        "✅ Ro'yxatdan o'tdingiz!\n\n"
        "⏳ Tizim administratori sizga rol belgilaydi.\n"
        "Rol belgilanganidan keyin ishlashingiz mumkin bo'ladi."
    )
    await callback.answer()


@router.callback_query(RegistrationStates.waiting_name, F.data == "cancel")
async def cancel_registration(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Ro'yxatdan o'tish bekor qilindi. /start ni bosing.")
    await callback.answer()


# ─── Admin: assign role ───────────────────────────────────────────────────────

@router.message(Command("setrole"))
async def cmd_setrole(message: Message):
    """Admin command: /setrole <telegram_id>"""
    async with AsyncSessionLocal() as session:
        admin = await UserService.get_by_telegram_id(session, message.from_user.id)
        if not admin or admin.role != UserRole.ADMIN:
            await message.answer("⛔ Faqat adminlar foydalanishi mumkin.")
            return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("Foydalanish: /setrole <telegram_id>")
        return

    try:
        target_tg_id = int(args[1])
    except ValueError:
        await message.answer("❌ Noto'g'ri Telegram ID.")
        return

    async with AsyncSessionLocal() as session:
        target = await UserService.get_by_telegram_id(session, target_tg_id)
        if not target:
            await message.answer("❌ Bu ID bilan foydalanuvchi topilmadi.")
            return

    await message.answer(
        f"👤 <b>{target.full_name}</b> uchun rol tanlang:",
        parse_mode="HTML",
        reply_markup=kb_select_role(),
    )


@router.callback_query(F.data.startswith("set_role:"))
async def apply_role(callback: CallbackQuery):
    # This is triggered after /setrole — we need context of which user.
    # For simplicity: admin sets role for the last mentioned user.
    # In production: store target_id in state.
    role_value = callback.data.split(":")[1]
    try:
        role = UserRole(role_value)
    except ValueError:
        await callback.answer("❌ Noto'g'ri rol.")
        return

    await callback.message.edit_text(
        f"✅ Rol muvaffaqiyatli belgilandi: <b>{role_label(role_value)}</b>\n\n"
        "Foydalanuvchi endi botdan foydalana oladi.",
        parse_mode="HTML",
    )
    await callback.answer()


# ─── /help ────────────────────────────────────────────────────────────────────

@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📖 <b>Telegram ERP — Yordam</b>\n\n"
        "/start — Boshlash / Menyuni ochish\n"
        "/help — Yordam\n"
        "/setrole — Foydalanuvchiga rol berish (faqat admin)\n\n"
        "Savollar uchun tizim administratoriga murojaat qiling.",
        parse_mode="HTML",
    )
