from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm import state
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardRemove

router = Router()


class InterviewStates(StatesGroup):
    in_interview = State()


async def cmd_interview(
        message: Message,
        state: FSMContext,
        agents: dict,
        get_or_create_user
):
    """Начать собеседование"""
    from db.repository import SessionRepository

    user, db = get_or_create_user(message)

    # Создаем сессию
    session = SessionRepository.create_session(
        db=db,
        telegram_id=message.from_user.id,
        session_type='interview',
        agent='interviewer',
        topic=f'{user.current_track} interview'
    )

    # Начинаем интервью
    await state.set_state(InterviewStates.in_interview)

    # Сохраняем в состоянии
    await state.update_data(
        interview_session_id=session.id,
        current_question=0,
        total_questions=3
    )

    # Генерируем вопросы
    await message.answer(f"🎙 *Собеседование по {user.current_track}*", parse_mode="Markdown")
    await message.answer("🔍 Генерирую вопросы...")

    try:
        # Генерация вопросов через агента
        interview_session = agents["interviewer"].start_interview(
            user.current_track,
            user.current_level,
            session.id
        )

        if interview_session and interview_session.questions:
            first_q = interview_session.questions[0]

            response = f"""
📝 *Вопрос 1 из {len(interview_session.questions)}*

❓ *{first_q.question}*

💡 *Ключевые концепции:*
{chr(10).join([f'• {c}' for c in first_q.expected_concepts[:3]])}
"""

            await message.answer(response, parse_mode="Markdown")

            # Сохраняем вопросы
            await state.update_data(
                interview_questions=[q.dict() for q in interview_session.questions]
            )

        else:
            await message.answer("❌ Не удалось сгенерировать вопросы")
            await state.clear()

    except Exception as e:
        await message.answer("❌ Ошибка запуска собеседования")
        print(f"Ошибка: {e}")
        await state.clear()


async def process_interview_answer(
        message: Message,
        state: FSMContext,
        agents: dict,
        use_rag: bool,
        get_or_create_user
):
    """Обработка ответа на вопрос собеседования"""
    from db.repository import SessionRepository

    data = await state.get_data()
    session_id = data.get('interview_session_id')
    current_idx = data.get('current_question', 0)
    questions = data.get('interview_questions', [])

    if not session_id or not questions:
        await message.answer("❌ Сессия не найдена")
        await state.clear()
        return

    user, db = get_or_create_user(message)

    # Оцениваем ответ
    await message.answer("📊 Оцениваю ответ...")

    try:
        score_result = agents["interviewer"].evaluate_answer(session_id, message.text)

        # Ответ
        feedback = f"""
✅ *Оценка:* {score_result.score}/100

📝 *Комментарий:*
{score_result.comment}
"""

        await message.answer(feedback, parse_mode="Markdown")

        # Следующий вопрос или завершение
        current_idx += 1

        if current_idx < len(questions):
            next_q = questions[current_idx]

            await message.answer(
                f"📝 *Вопрос {current_idx + 1} из {len(questions)}*\n\n"
                f"❓ *{next_q.get('question', 'Продолжим?')}*",
                parse_mode="Markdown"
            )

            await state.update_data(current_question=current_idx)

        else:
            # Завершаем интервью
            summary = agents["interviewer"].end_interview(session_id)

            final_response = f"""
🎉 *Собеседование завершено!*

📊 *Итоги:*
• Вопросов: {summary.get('total_questions', 0)}
• Средний балл: {summary.get('average_score', 0)}/100
• Уровень: {summary.get('performance_level', 'Нормально')}

💪 *Сильные стороны:*
{chr(10).join([f'• {p}' for p in summary.get('strong_points', [])[:2]])}
"""

            await message.answer(final_response, parse_mode="Markdown")

            await message.answer("Используйте /plan, /assess или /interview", reply_markup=ReplyKeyboardRemove())

            await state.clear()

    except Exception as e:
        await message.answer("❌ Ошибка оценки")
        print(f"Ошибка: {e}")
        await state.clear()


def register_interview_handlers(dp: Router, agents: dict, use_rag: bool, get_or_create_user):
    """Регистрация хэндлеров собеседования"""
    dp.message.register(
        lambda m: cmd_interview(m, state, agents, get_or_create_user),
        Command("interview")
    )

    dp.message.register(
        lambda m: process_interview_answer(m, state, agents, use_rag, get_or_create_user),
        InterviewStates.in_interview
    )