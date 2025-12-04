# bot/handlers/__init__.py
import logging
from aiogram import Router, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ParseMode

logger = logging.getLogger(__name__)

# Импортируем роутеры
from .general import router as general_router

# Создаем главный роутер
main_router = Router()


# Базовые команды
@main_router.message(Command("progress"))
async def cmd_progress(message: types.Message):
    """Показать прогресс"""
    from db.models import SessionLocal
    from db.repository import get_user_stats
    from bot.utils import get_or_create_user

    with SessionLocal() as db:
        try:
            # Получаем пользователя
            user, db = get_or_create_user(message, db)

            # Получаем статистику
            stats = get_user_stats(db, message.from_user.id)

            response = f"""
<b>📈 Ваш прогресс</b>

👤 {stats['user'].get('username', 'Аноним')}
🎯 Уровень: {stats['user'].get('level', 'junior')}
🚀 Направление: {stats['user'].get('track', 'backend')}

<b>📊 Активность:</b>
• Сессий: {sum(stats.get('sessions_by_type', {}).values())}
• Оценок: {len(stats.get('latest_assessments', []))}
"""
            await message.answer(response, parse_mode=ParseMode.HTML)

        except Exception as e:
            logger.error(f"Ошибка получения прогресса: {e}")
            await message.answer(
                "📊 Пройдите /assess чтобы начать отслеживать прогресс\n"
                "Или используйте /start для начала работы"
            )


@main_router.message(Command("plan"))
async def cmd_plan(message: types.Message):
    """План обучения"""
    await message.answer(
        "<b>🗓️ План обучения</b>\n\n"
        "Эта функция в разработке.\n"
        "Сейчас используйте:\n"
        "• /assess - оцените знания\n"
        "• /interview - попрактикуйтесь",
        parse_mode=ParseMode.HTML
    )


@main_router.message(Command("review"))
async def cmd_review(message: types.Message):
    """Code review"""
    await message.answer(
        "<b>🔍 Code Review</b>\n\n"
        "Отправьте код в формате:\n"
        "<pre><code class=\"language-python\">"
        "def example():\n"
        "    return 'Hello'"
        "</code></pre>\n\n"
        "Я проанализирую его и дам рекомендации.",
        parse_mode=ParseMode.HTML
    )


@main_router.message(Command("help"))
async def cmd_help(message: types.Message):
    """Справка"""
    help_text = """
🤖 <b>InterPrep AI - помощник для подготовки к собеседованиям</b>

<b>Основные команды:</b>
/start - Начать работу
/help - Эта справка
/progress - Ваш прогресс
/plan - План обучения
/review - Проверить код

<b>Режимы работы:</b>
/assess - Оценка навыков
/interview - Тренировка собеседования

<b>Просто отправьте:</b>
• Вопрос по программированию
• Код для анализа
• Запрос на помощь с подготовкой
"""
    await message.answer(help_text, parse_mode=ParseMode.HTML)


@main_router.message(Command("start"))
async def cmd_start(message: types.Message):
    """Старт бота"""
    await message.answer(
        "🤖 <b>InterPrep AI v1.0</b>\n\n"
        "Интеллектуальный помощник для подготовки к IT-собеседованиям.\n\n"
        "Используйте /help для списка команд.",
        parse_mode=ParseMode.HTML
    )


def register_handlers(dp: Dispatcher, agents: dict, use_rag: bool):
    """
    Регистрация всех хэндлеров в aiogram 3.x

    Args:
        dp: Диспетчер aiogram
        agents: Словарь с агентами
        use_rag: Флаг использования RAG
    """
    # Включаем все роутеры
    dp.include_router(main_router)
    dp.include_router(general_router)

    logger.info("✅ Обработчики зарегистрированы")


@main_router.message(Command("interview"))
async def cmd_interview(message: types.Message, agents: dict, use_rag: bool):
    """Начать собеседование"""
    try:
        # Проверяем, есть ли агент interviewer
        if "interviewer" in agents and agents["interviewer"]:
            await message.answer(
                "<b>💬 Начинаем собеседование!</b>\n\n"
                "Сейчас я задам вам несколько вопросов.\n\n"
                "Используйте /cancel для завершения.",
                parse_mode=ParseMode.HTML
            )

            # Здесь будет логика собеседования
            # Пока просто тестовый ответ
            await message.answer(
                "Расскажите о вашем опыте работы с Python.\n\n"
                "Сколько лет опыта и какие проекты вы реализовывали?"
            )
        else:
            await message.answer(
                "⚠️ <b>Агент собеседования временно недоступен</b>\n\n"
                "Сейчас я могу помочь:\n"
                "• Ответить на вопросы по программированию\n"
                "• Проверить код\n"
                "• Помочь с подготовкой\n\n"
                "Просто напишите ваш запрос.",
                parse_mode=ParseMode.HTML
            )
    except Exception as e:
        logger.error(f"Ошибка в команде interview: {e}")
        await message.answer(
            "🤖 Используйте команды:\n"
            "/start - начало работы\n"
            "/help - помощь\n"
            "/progress - ваш прогресс"
        )

@main_router.message(Command("assess"))
async def cmd_assess(message: types.Message, agents: dict, use_rag: bool):
    """Оценка навыков"""
    try:
        if "assessor" in agents and agents["assessor"]:
            await message.answer(
                "<b>📊 Оценка навыков</b>\n\n"
                "Чтобы оценить ваши знания, ответьте на несколько вопросов.\n\n"
                "<b>Или опишите:</b>\n"
                "• Какие технологии вы знаете\n"
                "• Ваш уровень опыта\n"
                "• Над какими проектами работали\n\n"
                "Пример: <code>Знаю Python, Django, 2 года опыта, работал над API и веб-приложениями</code>",
                parse_mode=ParseMode.HTML
            )
        else:
            await message.answer(
                "📊 <b>Опишите ваши навыки:</b>\n\n"
                "• Языки программирования\n"
                "• Фреймворки\n"
                "• Уровень опыта\n"
                "• Проекты\n\n"
                "<i>Пример: Python, Django, 2 года, веб-приложения</i>",
                parse_mode=ParseMode.HTML
            )
    except Exception as e:
        logger.error(f"Ошибка в команде assess: {e}")
        await message.answer("📊 Просто опишите ваши навыки и опыт работы.")


@main_router.message(Command("begin"))
async def cmd_begin(message: types.Message):
    """Начать подготовку с указанием уровня и направления"""
    try:
        # Разбираем аргументы команды
        args = message.text.split()[1:]  # Пропускаем "/begin"

        if len(args) < 2:
            await message.answer(
                "<b>🎯 Начнем подготовку!</b>\n\n"
                "<b>Формат:</b> <code>/begin [уровень] [направление]</code>\n\n"
                "<b>Уровни:</b> junior, middle, senior\n"
                "<b>Направления:</b> backend, frontend, python, java, data, devops, fullstack\n\n"
                "<b>Пример:</b> <code>/begin junior backend</code>\n"
                "<b>Пример:</b> <code>/begin middle python</code>",
                parse_mode=ParseMode.HTML
            )
            return

        level = args[0].lower()
        track = args[1].lower()

        from bot.config import VALID_LEVELS, VALID_TRACKS

        if level not in VALID_LEVELS:
            await message.answer(
                f"❌ <b>Неверный уровень:</b> {level}\n"
                f"<b>Доступные уровни:</b> {', '.join(VALID_LEVELS)}",
                parse_mode=ParseMode.HTML
            )
            return

        if track not in VALID_TRACKS:
            await message.answer(
                f"❌ <b>Неверное направление:</b> {track}\n"
                f"<b>Доступные направления:</b> {', '.join(VALID_TRACKS)}",
                parse_mode=ParseMode.HTML
            )
            return

        # Сохраняем настройки пользователя
        from db.models import SessionLocal
        from db.repository import UserRepository

        with SessionLocal() as db:
            user = UserRepository.get_or_create_user(db, message.from_user.id)
            UserRepository.update_user_level_track(db, message.from_user.id, level, track)

        await message.answer(
            f"✅ <b>Отлично!</b>\n\n"
            f"🎯 <b>Уровень:</b> {level}\n"
            f"🚀 <b>Направление:</b> {track}\n\n"
            f"Теперь вы можете:\n"
            f"• <code>/assess</code> - оценить знания\n"
            f"• <code>/interview</code> - пройти собеседование\n"
            f"• <code>/plan</code> - создать план обучения\n"
            f"• <code>/review</code> - проверить код\n\n"
            f"<i>Или просто пишите вопросы по программированию!</i>",
            parse_mode=ParseMode.HTML
        )

    except Exception as e:
        logger.error(f"Ошибка в команде begin: {e}")
        await message.answer(
            "🤖 Используйте: <code>/begin [уровень] [направление]</code>\n\n"
            "Пример: <code>/begin junior backend</code>",
            parse_mode=ParseMode.HTML
        )