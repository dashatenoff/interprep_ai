# bot/handlers/__init__.py
from aiogram import Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ParseMode


def register_handlers(dp: Dispatcher, agents: dict, use_rag: bool):
    """Регистрация всех хэндлеров в aiogram 3.x"""

    # Базовые команды (в дополнение к тем, что в main.py)
    @dp.message(Command("progress"))
    async def cmd_progress(message: types.Message):
        """Показать прогресс"""
        from db.models import SessionLocal
        from db.repository import get_user_stats
        from bot.utils import get_or_create_user

        with SessionLocal() as db:
            user, db = get_or_create_user(message, db)

            try:
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
                await message.answer(response)

            except Exception as e:
                await message.answer("📊 Пройдите /assess чтобы начать отслеживать прогресс")

    @dp.message(Command("plan"))
    async def cmd_plan(message: types.Message):
        """План обучения"""
        await message.answer(
            "<b>🗓️ План обучения</b>\n\n"
            "Эта функция в разработке.\n"
            "Сейчас используйте:\n"
            "• /assess - оцените знания\n"
            "• /interview - попрактикуйтесь"
        )

    @dp.message(Command("review"))
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

    # Импортируем и регистрируем остальные хэндлеры
    from .start import register_start_handlers
    from .assessment import register_assessment_handlers
    from .interview import register_interview_handlers
    from .planning import register_planning_handlers
    from .review import register_review_handlers
    from .general import register_general_handlers

    register_start_handlers(dp, agents, use_rag)
    register_assessment_handlers(dp, agents, use_rag)
    register_interview_handlers(dp, agents, use_rag)
    register_planning_handlers(dp, agents, use_rag)
    register_review_handlers(dp, agents, use_rag)
    register_general_handlers(dp, agents, use_rag)