# main.py
import os
import sys
import asyncio
import logging
from pathlib import Path
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv

# Добавляем путь для импорта модулей
sys.path.append(str(Path(__file__).resolve().parent))

# Импорты из нашего проекта
from bot.handlers import register_handlers
from bot.utils import setup_rag, setup_database, setup_agents
from bot.config import WELCOME_MESSAGE

# =========================
# Настройка логирования
# =========================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =========================
# Загрузка окружения
# =========================
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("❌ TELEGRAM_BOT_TOKEN не найден в .env")

# =========================
# Инициализация бота (aiogram 3.x)
# =========================
bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# =========================
# Глобальные объекты (для доступа в хэндлерах)
# =========================
agents = {}
USE_RAG = False


# =========================
# Обработчик команд
# =========================
@dp.message(Command("start", "help"))
async def cmd_start(message: types.Message):
    """Начало работы с ботом"""
    status = "✅ Активна" if USE_RAG else "❌ Не активна"
    await message.answer(WELCOME_MESSAGE.format(status))


# =========================
# Основная функция запуска
# =========================
async def main():
    """Главная функция запуска бота"""
    logger.info("🚀 Запуск InterPrep AI...")

    global USE_RAG, agents

    # 1. Настройка базы данных
    try:
        setup_database()
        logger.info("✅ База данных инициализирована")
    except Exception as e:
        logger.error(f"❌ Ошибка БД: {e}")

    # 2. Настройка RAG
    try:
        rag_status = setup_rag()
        USE_RAG = rag_status.get("status") == "ready"
        if USE_RAG:
            logger.info(f"✅ RAG база готова: {rag_status.get('documents_count', 0)} документов")
        else:
            logger.warning("⚠️  RAG база не готова")
    except Exception as e:
        logger.error(f"❌ Ошибка RAG: {e}")
        USE_RAG = False

    # 3. Настройка агентов
    try:
        agents = setup_agents(USE_RAG)
        logger.info("✅ Агенты инициализированы")
    except Exception as e:
        logger.error(f"❌ Ошибка агентов: {e}")
        raise

    # 4. Регистрация хэндлеров
    register_handlers(dp, agents, USE_RAG)
    logger.info("✅ Хэндлеры зарегистрированы")

    logger.info("✅ InterPrep AI готов к работе!")

    # 5. Запуск поллинга
    await dp.start_polling(bot)


async def on_shutdown():
    """Завершение работы бота"""
    logger.info("👋 Завершение работы InterPrep AI...")
    await bot.close()


# =========================
# Запуск бота
# =========================
if __name__ == "__main__":
    print("🤖 InterPrep AI v1.0 с RAG и SQLite")
    print("-" * 40)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Выключение по запросу пользователя...")
        asyncio.run(on_shutdown())
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        asyncio.run(on_shutdown())