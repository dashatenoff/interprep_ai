# bot/handlers/assessment.py
from aiogram import types, Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command

router = Router()


class AssessmentStates(StatesGroup):
    waiting_experience = State()
    in_assessment = State()


@router.message(Command("assess"))
async def cmd_assess(message: types.Message, state: FSMContext):
    """Быстрая оценка знаний"""
    await state.set_state(AssessmentStates.in_assessment)
    await message.answer(
        "<b>📊 Быстрая оценка знаний</b>\n\n"
        "Опишите что вы знаете (2-3 предложения):\n\n"
        "<b>Пример:</b>\n"
        "Знаю Python, ООП, работал со списками и словарями, решал задачи на сортировку."
    )


@router.message(AssessmentStates.in_assessment)
async def process_assessment(message: types.Message, state: FSMContext, agents: dict, use_rag: bool):
    """Обработка быстрой оценки"""
    from db.models import SessionLocal
    from db.repository import SessionRepository, AssessmentRepository

    with SessionLocal() as db:
        user, db = get_or_create_user(message, db)

        # Создаем сессию
        session = SessionRepository.create_session(
            db=db,
            telegram_id=message.from_user.id,
            session_type='quick_assessment',
            agent='assessor',
            topic='Quick Assessment'
        )

        # Запускаем оценку
        await message.answer("🔍 Анализирую...")

        try:
            # Определяем темы
            topics = ['Python', 'Алгоритмы', 'Структуры данных']

            # Оценка через агента
            result = agents["assessor"].assess(message.text, topics)

            # Формируем ответ
            response = f"""
<b>⚡ Результаты оценки:</b>

{chr(10).join([f'• {skill}: {score}/100' for skill, score in result.scores.items()])}

<b>💡 Рекомендация:</b> {result.follow_up}

База знаний: {'✅ Использована' if result.context_used else '❌ Не использована'}
"""

            await message.answer(response)
            await state.clear()

        except Exception as e:
            print(f"Ошибка оценки: {e}")
            await message.answer("❌ Ошибка при оценке. Попробуйте позже.")
            await state.clear()


def get_or_create_user(message, db):
    """Получает или создает пользователя"""
    from db.repository import UserRepository
    return UserRepository.get_or_create_user(
        db=db,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name
    )


def register_assessment_handlers(dp, agents: dict, use_rag: bool):
    """Регистрация хэндлеров оценки"""
    dp.include_router(router)