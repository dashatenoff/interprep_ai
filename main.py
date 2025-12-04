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

import os
from pathlib import Path

# Создаем папки при запуске (важно для Railway)
Path("data").mkdir(exist_ok=True)
Path("knowledge").mkdir(exist_ok=True)
Path("chroma_db").mkdir(exist_ok=True)

print(f"📁 Current directory: {os.getcwd()}")
print(f"📁 Contents: {os.listdir('.')}")
# Добавляем путь для импорта модулей
sys.path.append(str(Path(__file__).resolve().parent))

# Импорты из нашего проекта
from bot.handlers import register_handlers
from bot.utils import setup_rag, setup_database, setup_agents, get_bot_commands
from bot.middleware.agents_middleware import AgentsMiddleware
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
# Глобальные переменные
# =========================
agents = {}
USE_RAG = False


# =========================
# Базовые обработчики команд
# =========================
@dp.message(Command("start", "help"))
async def cmd_start(message: types.Message):
    """Начало работы с ботом"""
    try:
        status = "✅ Активна" if USE_RAG else "❌ Не активна"
        welcome_text = WELCOME_MESSAGE.format(status)
        await message.answer(welcome_text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Ошибка в команде start: {e}")
        await message.answer(
            "🤖 <b>InterPrep AI v1.0</b>\n\n"
            "Интеллектуальный помощник для подготовки к IT-собеседованиям.\n\n"
            "Используйте /help для списка команд.",
            parse_mode=ParseMode.HTML
        )

@dp.message(Command("rag_status"))
async def cmd_rag_status(message: types.Message, use_rag: bool = USE_RAG):
    """Проверка статуса RAG"""
    if use_rag:
        try:
            from rag.retriever import check_database_status
            status = check_database_status()
            await message.answer(
                f"📊 <b>Статус RAG базы:</b>\n\n"
                f"✅ <b>Статус:</b> {status.get('status', 'unknown')}\n"
                f"📁 <b>Документов:</b> {status.get('documents_count', 0)}\n"
                f"📚 <b>Коллекция:</b> {status.get('collection_name', 'unknown')}"
            )
        except Exception as e:
            await message.answer(f"❌ Ошибка получения статуса RAG: {e}")
    else:
        await message.answer("⚠️ RAG модуль отключен")


@dp.message(Command("status"))
async def cmd_status(message: types.Message, agents: dict = agents):
    """Статус бота"""
    agents_status = "✅ Доступны" if agents else "❌ Не доступны"
    rag_status = "✅ ВКЛ" if USE_RAG else "❌ ВЫКЛ"

    await message.answer(
        f"🤖 <b>Статус InterPrep AI:</b>\n\n"
        f"🔄 <b>Бот:</b> Активен\n"
        f"🧠 <b>Агенты:</b> {agents_status}\n"
        f"📚 <b>RAG:</b> {rag_status}\n"
        f"💾 <b>База данных:</b> ✅ Готова"
    )


# =========================
# Основная функция запуска
# =========================
async def main():
    """Главная функция запуска бота"""
    global USE_RAG, agents

    logger.info("🚀 Запуск InterPrep AI...")

    # 1. Настройка базы данных
    try:
        if setup_database():
            logger.info("✅ База данных готова")
        else:
            logger.error("❌ Ошибка инициализации БД")
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
        if agents:
            logger.info("✅ Агенты инициализированы")
        else:
            logger.warning("⚠️  Агенты не созданы, бот будет работать в ограниченном режиме")
    except Exception as e:
        logger.error(f"❌ Ошибка агентов: {e}")
        # Создаем пустые агенты для продолжения работы
        agents = {}

    # 4. Добавляем middleware для передачи агентов
    try:
        dp.update.outer_middleware(AgentsMiddleware(agents, USE_RAG))
        logger.info("✅ Middleware добавлен")
    except Exception as e:
        logger.error(f"❌ Ошибка middleware: {e}")

    # 5. Регистрация хэндлеров
    try:
        register_handlers(dp, agents, USE_RAG)
        logger.info("✅ Хэндлеры зарегистрированы")
    except Exception as e:
        logger.error(f"❌ Ошибка регистрации хэндлеров: {e}")

    # 6. Устанавливаем команды бота
    try:
        await bot.set_my_commands(get_bot_commands())
        logger.info("✅ Команды бота установлены")
    except Exception as e:
        logger.error(f"❌ Ошибка установки команд: {e}")

    logger.info("✅ InterPrep AI готов к работе!")
    print("\n🤖 Бот запущен! Нажмите Ctrl+C для остановки.\n")

    # 7. Запуск поллинга
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"❌ Ошибка поллинга: {e}")
        raise


async def on_shutdown():
    """Завершение работы бота"""
    logger.info("👋 Завершение работы InterPrep AI...")
    try:
        await bot.close()
    except Exception as e:
        logger.error(f"❌ Ошибка при закрытии бота: {e}")


# =========================
# Запуск бота
# =========================
if __name__ == "__main__":
    print("🤖 InterPrep AI v1.0 с RAG и SQLite")
    print("-" * 40)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Выключение по запросу пользователя...")
        asyncio.run(on_shutdown())
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        asyncio.run(on_shutdown())