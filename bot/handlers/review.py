from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm import state
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, ReplyKeyboardRemove
from aiogram.utils.keyboard import ReplyKeyboardBuilder

router = Router()


class ReviewStates(StatesGroup):
    waiting_code = State()
    analyzing_code = State()


async def cmd_review(message: Message, state: FSMContext):
    """Начать code review"""
    await state.set_state(ReviewStates.waiting_code)
    await message.answer(
        "🔍 *Code Review*\n\n"
        "Отправьте код для анализа:\n\n"
        "*Формат:*\n"
        "```python\n"
        "def your_function():\n"
        "    # ваш код\n"
        "```\n\n"
        "Или просто отправьте код текстом.\n"
        "Укажите язык и задачу если нужно.",
        parse_mode="Markdown"
    )


async def process_code_review(
        message: Message,
        state: FSMContext,
        agents: dict,
        use_rag: bool,
        get_or_create_user
):
    """Обработка кода для ревью"""
    from db.models import SessionLocal
    from db.repository import SessionRepository, ReviewRepository

    with SessionLocal() as db:
        user, db = get_or_create_user(message, db)

        # Создаем сессию
        session = SessionRepository.create_session(
            db=db,
            telegram_id=message.from_user.id,
            session_type='review',
            agent='reviewer',
            topic='Code Review'
        )

        # Сохраняем код
        SessionRepository.add_message(
            db=db,
            session_id=session.id,
            role='user',
            content=message.text[:1000]  # Ограничиваем длину
        )

        # Анализируем код
        await message.answer("🔎 Анализирую код...")

        try:
            # Используем агента для анализа
            review_result = agents["reviewer"].process_message(message.text)

            # Отправляем результат
            if len(review_result) > 4000:
                # Разбиваем на части если длинно
                parts = [review_result[i:i + 4000] for i in range(0, len(review_result), 4000)]
                for i, part in enumerate(parts, 1):
                    await message.answer(f"*Часть {i}:*\n\n{part}", parse_mode="Markdown")
            else:
                await message.answer(review_result, parse_mode="Markdown")

            # Сохраняем результат в БД
            review_data = {
                'language': 'python',  # Определяем язык
                'code_snippet': message.text[:500],
                'context': 'Code review request',
                'score': 70,  # Примерный балл
                'issues_found': review_result.count('❌') + review_result.count('⚠️'),
                'review_details': {'result': review_result[:300]},
                'feedback': 'Code review completed'
            }

            ReviewRepository.save_code_review(db, message.from_user.id, review_data)

            # Завершаем сессию
            SessionRepository.complete_session(db, session.id)

            # Предлагаем еще
            builder = ReplyKeyboardBuilder()
            builder.button(text="✅ Еще код")
            builder.button(text="❌ Закончить")
            keyboard = builder.as_markup(resize_keyboard=True)

            await message.answer("Проанализировать еще код?", reply_markup=keyboard)

            # Переходим в состояние выбора
            await state.set_state(ReviewStates.analyzing_code)

        except Exception as e:
            print(f"Ошибка code review: {e}")
            await message.answer(
                "❌ Не удалось проанализировать код.\n"
                "Проверьте формат и попробуйте снова."
            )
            await state.clear()


async def process_review_choice(
        message: Message,
        state: FSMContext,
        agents: dict,
        use_rag: bool
):
    """Обработка выбора после ревью"""
    text = message.text.lower()

    if text in ['✅ еще код', 'еще', 'да', 'yes']:
        await message.answer(
            "Отправьте следующий код:",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.set_state(ReviewStates.waiting_code)

    elif text in ['❌ закончить', 'нет', 'no', 'стоп']:
        await message.answer(
            "✅ Code review завершен!",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.clear()

    else:
        await message.answer("Используйте кнопки или напишите 'еще' или 'закончить'")


def register_review_handlers(dp: Router, agents: dict, use_rag: bool, get_or_create_user):
    """Регистрация хэндлеров code review"""
    # Команда /review
    dp.message.register(cmd_review, Command("review"))

    # Обработка кода
    dp.message.register(
        lambda m: process_code_review(m, state, agents, use_rag, get_or_create_user),
        ReviewStates.waiting_code
    )

    # Обработка выбора после ревью
    dp.message.register(
        lambda m: process_review_choice(m, state, agents, use_rag),
        ReviewStates.analyzing_code
    )