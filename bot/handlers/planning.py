from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm import state
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.utils.keyboard import ReplyKeyboardBuilder

router = Router()


class PlanningStates(StatesGroup):
    waiting_goal = State()
    creating_plan = State()


async def cmd_plan(message: Message, state: FSMContext):
    """Создать план обучения"""
    await state.set_state(PlanningStates.waiting_goal)
    await message.answer(
        "🗓️ *Создание плана обучения*\n\n"
        "Опишите, что вы хотите изучить или улучшить:\n\n"
        "*Примеры:*\n"
        "• Хочу освоить Python для backend\n"
        "• Нужно улучшить алгоритмы для собеседований\n"
        "• Хочу изучить микросервисную архитектуру",
        parse_mode="Markdown"
    )


async def process_plan_goal(
        message: Message,
        state: FSMContext,
        agents: dict,
        use_rag: bool,
        get_or_create_user
):
    """Обработка цели для плана"""
    from db.models import SessionLocal
    from db.repository import SessionRepository, PlanRepository

    with SessionLocal() as db:
        user, db = get_or_create_user(message, db)

        # Создаем сессию
        session = SessionRepository.create_session(
            db=db,
            telegram_id=message.from_user.id,
            session_type='planning',
            agent='planner',
            topic='Learning Plan'
        )

        # Сохраняем запрос
        SessionRepository.add_message(
            db=db,
            session_id=session.id,
            role='user',
            content=message.text
        )

        # Создаем план
        await message.answer("📝 Создаю персонализированный план...")

        try:
            # Получаем план от агента
            plan_result = agents["planner"].make_plan(
                user_text=message.text,
                level=user.current_level,
                track=user.current_track,
                weeks=4
            )

            # Форматируем ответ
            response = f"""
✅ *План обучения создан!*

📅 *Общая информация:*
• Недель: {plan_result.total_weeks}
• Всего часов: {plan_result.total_hours}
• Фокус: {', '.join(plan_result.focus_areas[:2])}

📝 *Краткое описание:*
{plan_result.summary[:300]}...

*Использована база знаний:* {'✅ Да' if plan_result.rag_context_used else '❌ Нет'}

*Показать детали по неделям?* (да/нет)
"""

            await message.answer(response, parse_mode="Markdown")

            # Сохраняем состояние с планом
            await state.update_data(
                plan_result=plan_result.dict(),
                plan_session_id=session.id
            )

            # Переходим к следующему шагу
            await state.set_state(PlanningStates.creating_plan)

        except Exception as e:
            print(f"Ошибка создания плана: {e}")
            await message.answer("❌ Не удалось создать план. Попробуйте позже.")
            await state.clear()


async def process_plan_details(
        message: Message,
        state: FSMContext,
        agents: dict,
        use_rag: bool,
        get_or_create_user
):
    """Показать детали плана"""
    text = message.text.lower()

    if text in ['да', 'yes', 'покажи', 'детали']:
        data = await state.get_data()
        plan_result = data.get('plan_result')

        if plan_result and plan_result.get('plan'):
            response = "📋 *Детали плана:*\n\n"

            for week in plan_result['plan']:
                response += f"*Неделя {week['week']}: {week['title']}*\n"
                response += f"📚 Темы: {', '.join(week['topics'][:3])}\n"
                response += f"✅ Задачи: {week['tasks'][0] if week['tasks'] else 'Нет'}\n"
                response += f"⏰ Часов: {week.get('estimated_hours', 10)}\n\n"

            # Обрезаем если слишком длинно
            if len(response) > 4000:
                response = response[:4000] + "...\n\n(план сокращен)"

            await message.answer(response, parse_mode="Markdown")

            # Предлагаем сохранить план
            builder = ReplyKeyboardBuilder()
            builder.button(text="✅ Сохранить план")
            builder.button(text="❌ Не сохранять")
            keyboard = builder.as_markup(resize_keyboard=True)

            await message.answer("Сохранить этот план в вашем профиле?", reply_markup=keyboard)

        else:
            await message.answer("❌ План не найден")
            await state.clear()

    elif text in ['нет', 'no', 'пропустить']:
        await message.answer("✅ Хорошо, план не будет сохранен.")
        await state.clear()

    elif text == '✅ сохранить план':
        # Сохраняем план в БД
        from db.models import SessionLocal
        from db.repository import PlanRepository

        data = await state.get_data()
        plan_result = data.get('plan_result')
        session_id = data.get('plan_session_id')

        if plan_result:
            with SessionLocal() as db:
                user, db = get_or_create_user(message, db)

                plan_data = {
                    'title': f'План: {plan_result.get("focus_areas", ["Обучение"])[0]}',
                    'description': plan_result.get('summary', 'План обучения'),
                    'track': user.current_track,
                    'level': user.current_level,
                    'duration_weeks': plan_result.get('total_weeks', 4),
                    'plan_data': plan_result,
                    'progress': 0.0
                }

                PlanRepository.save_learning_plan(db, message.from_user.id, plan_data)

                await message.answer(
                    "✅ *План сохранен!*\n\n"
                    "Вы можете посмотреть его в любой момент через /progress",
                    parse_mode="Markdown",
                    reply_markup=ReplyKeyboardRemove()
                )
        else:
            await message.answer("❌ Нечего сохранять")

        await state.clear()

    elif text == '❌ не сохранять':
        await message.answer("✅ План не сохранен.", reply_markup=ReplyKeyboardRemove())
        await state.clear()

    else:
        await message.answer("Пожалуйста, ответьте 'да' или 'нет'")


def register_planning_handlers(dp: Router, agents: dict, use_rag: bool, get_or_create_user):
    """Регистрация хэндлеров планирования"""
    # Команда /plan
    dp.message.register(cmd_plan, Command("plan"))

    # Обработка цели плана
    dp.message.register(
        lambda m: process_plan_goal(m, state, agents, use_rag, get_or_create_user),
        PlanningStates.waiting_goal
    )

    # Обработка деталей плана
    dp.message.register(
        lambda m: process_plan_details(m, state, agents, use_rag, get_or_create_user),
        PlanningStates.creating_plan
    )