import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage

from bot.handlers import all_routers
from config import settings
from db.session import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    logger.info("🚀 Telegram ERP bot ishga tushmoqda...")

    # Init DB (creates tables if not exist)
    await init_db()
    logger.info("✅ Ma'lumotlar bazasi tayyor.")

    # FSM storage — Redis
    storage = RedisStorage.from_url(settings.REDIS_URL)

    # Bot & Dispatcher
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=storage)

    # Register all routers
    for router in all_routers:
        dp.include_router(router)

    logger.info(f"📋 {len(all_routers)} ta router ro'yxatga olindi.")

    # Start polling
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        logger.info("👋 Bot to'xtatildi.")


if __name__ == "__main__":
    asyncio.run(main())
