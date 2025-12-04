# bot/handlers/general.py
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ParseMode

router = Router()


async def handle_general_message(message: types.Message, agents: dict, use_rag: bool):
    """Обработка общих сообщений через координатора"""
    from db.models import SessionLocal
    from db.repository import SessionRepository

    with SessionLocal() as db:
        from bot.utils import get_or_create_user
        user, db = get_or_create_user(message, db)

        # Пропускаем команды
        if message.text.startswith('/'):
            return

        try:
            # Определяем агента через координатора
            route_result = agents["coordinator"].route(message.text)

            # Создаем сессию
            session = SessionRepository.create_session(
                db=db,
                telegram_id=message.from_user.id,
                session_type='general',
                agent=route_result.agent.lower(),
                topic=route_result.context[:50]
            )

            # Сохраняем запрос
            SessionRepository.add_message(
                db=db,
                session_id=session.id,
                role='user',
                content=message.text
            )

            # Формируем ответ в зависимости от агента
            if route_result.agent == "ASSESSOR":
                # Быстрая оценка
                topics = route_result.metadata.get('suggested_topics', ['Программирование', 'Алгоритмы'])
                result = agents["assessor"].assess(message.text, topics)

                response = f"""
⚡ *Быстрая оценка*

📊 *Результаты:*
{chr(10).join([f'• {skill}: {score}/100' for skill, score in result.scores.items()])}

💡 *Рекомендация:* {result.follow_up}

База знаний: {'✅ Использована' if result.context_used else '❌ Не использована'}
"""

            elif route_result.agent == "INTERVIEWER":
                # Быстрый вопрос для собеседования
                response = f"""
💬 *Координатор определил: нужна практика собеседования*

📝 *Контекст:* {route_result.context}

*Используйте* /interview *для полноценного собеседования*

*Или ответьте на этот вопрос:*
«{route_result.metadata.get('primary_topic', 'Расскажите о вашем опыте')}»
"""

            elif route_result.agent == "PLANNER":
                # Рекомендация по планированию
                response = f"""
🗓️ *Координатор определил: нужен план обучения*

📝 *Контекст:* {route_result.context}

*Используйте* /plan *для создания персонализированного плана*

*Или опишите подробнее:*
1. Что вы хотите изучить?
2. На каком вы сейчас уровне?
3. Сколько времени готовы уделять?
"""

            elif route_result.agent == "REVIEWER":
                # Code review предложение
                response = """
🔍 *Координатор определил: нужен анализ кода*

*Используйте* /review *для code review*


*Или просто отправьте код текстом.*
"""

            else:
                # Общий ответ для неизвестного агента
                response = f"""
🤖 *Координатор выбрал:* {route_result.agent}
📝 *Контекст:* {route_result.context}

*Для конкретных действий используйте команды:*
/assess - оценка знаний
/interview - собеседование  
/plan - план обучения
/review - анализ кода
"""

            # Отправляем ответ
            await message.answer(response, parse_mode="Markdown")

            # Сохраняем ответ в БД
            SessionRepository.add_message(
                db=db,
                session_id=session.id,
                role='assistant',
                content=response[:500]  # Сохраняем только начало
            )

            # Завершаем сессию
            SessionRepository.complete_session(db, session.id)

        except Exception as e:
            print(f"Ошибка обработки сообщения: {e}")

            # Простой ответ при ошибке
            await message.answer(
                "🤔 Пока не понял запрос.\n\n"
                "Попробуйте использовать команды:\n"
                "• /begin - начать подготовку\n"
                "• /assess - оценить знания\n"
                "• /interview - пройти собеседование\n"
                "• /plan - создать план обучения\n"
                "• /review - проверить код"
            )


# Регистрируем хендлер для всех текстовых сообщений (не команд)
@router.message(lambda message: message.text and not message.text.startswith('/'))
async def general_message_handler(message: Message, agents: dict, use_rag: bool):
    """Обработчик общих сообщений"""
    await handle_general_message(message, agents, use_rag)