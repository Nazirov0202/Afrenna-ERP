from aiogram import F, Router
from aiogram.types import Message

from db.models import UserRole
from db.session import AsyncSessionLocal
from services.report_service import ReportService
from services.user_service import UserService
from utils.helpers import format_money, format_qty, order_status_label, role_label

router = Router()

ADMIN_ROLES = (UserRole.ADMIN, UserRole.MANAGER)


@router.message(F.text == "📊 Hisobotlar")
async def reports_menu(message: Message):
    async with AsyncSessionLocal() as session:
        user = await UserService.get_by_telegram_id(session, message.from_user.id)
        if not user or user.role not in ADMIN_ROLES:
            await message.answer("⛔ Ruxsatingiz yo'q.")
            return

    await message.answer(
        "📊 <b>Hisobotlar</b>\n\n"
        "Quyidagi buyruqlardan foydalaning:\n\n"
        "/report_daily — Bugungi barcha xodimlar\n"
        "/report_orders — Zakazlar holati\n"
        "/report_balances — Xodimlar balanslari",
        parse_mode="HTML",
    )


@router.message(F.text.startswith("/report_daily"))
async def report_all_daily(message: Message):
    async with AsyncSessionLocal() as session:
        user = await UserService.get_by_telegram_id(session, message.from_user.id)
        if not user or user.role not in ADMIN_ROLES:
            await message.answer("⛔ Ruxsatingiz yo'q.")
            return
        rows = await ReportService.all_workers_daily(session)

    if not rows:
        await message.answer("📊 Bugun hech kim ishlayotgani yo'q.")
        return

    lines = ["📊 <b>Bugungi natijalar (barcha xodimlar):</b>\n"]
    for i, r in enumerate(rows, 1):
        if r["total_qty"] > 0:
            lines.append(
                f"{i}. <b>{r['full_name']}</b>\n"
                f"   ✅ {format_qty(r['total_qty'])} | 💰 {format_money(r['total_earned'])}"
            )
    if len(lines) == 1:
        lines.append("Bugun hech kim topshirmadi.")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(F.text.startswith("/report_orders"))
async def report_orders(message: Message):
    async with AsyncSessionLocal() as session:
        user = await UserService.get_by_telegram_id(session, message.from_user.id)
        if not user or user.role not in ADMIN_ROLES:
            await message.answer("⛔ Ruxsatingiz yo'q.")
            return
        rows = await ReportService.order_status_report(session)

    if not rows:
        await message.answer("📋 Faol zakazlar yo'q.")
        return

    lines = ["📋 <b>Zakazlar holati:</b>\n"]
    for r in rows:
        deadline_str = r["deadline"].strftime("%d.%m") if r["deadline"] else "—"
        lines.append(
            f"• <b>{r['order_code']}</b> — {r['model_name']}\n"
            f"  {order_status_label(r['status'].value)} | "
            f"{r['progress']}% | Muddat: {deadline_str}"
        )
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(F.text.startswith("/report_balances"))
async def report_balances(message: Message):
    async with AsyncSessionLocal() as session:
        user = await UserService.get_by_telegram_id(session, message.from_user.id)
        if not user or user.role not in ADMIN_ROLES:
            await message.answer("⛔ Ruxsatingiz yo'q.")
            return
        rows = await ReportService.workers_balance_report(session)

    if not rows:
        await message.answer("💼 Balansi bor xodimlar yo'q.")
        return

    lines = ["💼 <b>Xodimlar balanslari:</b>\n"]
    for i, r in enumerate(rows, 1):
        lines.append(
            f"{i}. <b>{r['full_name']}</b> ({role_label(r['role'].value)})\n"
            f"   💰 {format_money(r['balance'])}"
        )
    await message.answer("\n".join(lines), parse_mode="HTML")


# ─── Xodimlar ro'yxati ────────────────────────────────────────────────────────

@router.message(F.text == "👥 Xodimlar")
async def workers_list(message: Message):
    async with AsyncSessionLocal() as session:
        user = await UserService.get_by_telegram_id(session, message.from_user.id)
        if not user or user.role not in ADMIN_ROLES:
            await message.answer("⛔ Ruxsatingiz yo'q.")
            return
        workers = await UserService.get_all_active(session)

    if not workers:
        await message.answer("👥 Xodimlar ro'yxati bo'sh.")
        return

    lines = [f"👥 <b>Xodimlar ({len(workers)} ta):</b>\n"]
    for w in workers:
        role_str = role_label(w.role.value) if w.role else "❓ Rol yo'q"
        lines.append(f"• <b>{w.full_name}</b> — {role_str}")

    await message.answer("\n".join(lines), parse_mode="HTML")
