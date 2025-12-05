# bot/handlers/planning.py
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.enums import ParseMode

import logging

logger = logging.getLogger(__name__)

router = Router()


# Определяем состояния конкретно для плана
class PlanStates(StatesGroup):
    waiting_goal = State()  # Что изучать
    waiting_level = State()  # Какой уровень
    waiting_time = State()  # Сколько времени
    confirm_details = State()  # Показать детали
    save_plan = State()  # Сохранить план


async def cmd_plan(message: Message, state: FSMContext):
    """Создать план обучения - УПРОЩЕННАЯ версия"""
    await state.clear()  # Очищаем предыдущие состояния

    await state.set_state(PlanStates.waiting_goal)
    await message.answer(
        "🗓️ <b>Создание плана обучения</b>\n\n"
        "<i>Что конкретно хотите изучить?</i>\n\n"
        "<b>Примеры:</b>\n"
        "• Микросервисная архитектура с нуля\n"
        "• Docker и Kubernetes для микросервисов\n"
        "• Паттерны проектирования микросервисов",
        parse_mode=ParseMode.HTML
    )


async def process_plan_goal(
        message: Message,
        state: FSMContext,
        agents: dict,
        use_rag: bool,
        get_or_create_user
):
    """Обработка цели для плана - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
    user_goal = message.text.strip()

    # Сохраняем цель
    await state.update_data(user_goal=user_goal)

    # Сразу переходим к следующему вопросу
    await state.set_state(PlanStates.waiting_level)

    # Создаем клавиатуру для выбора уровня
    builder = ReplyKeyboardBuilder()
    builder.button(text="🟢 Начинающий")
    builder.button(text="🟡 Средний")
    builder.button(text="🔴 Продвинутый")
    keyboard = builder.as_markup(resize_keyboard=True)

    await message.answer(
        f"🎯 <b>Отлично! Будем изучать: {user_goal}</b>\n\n"
        "<b>Теперь выберите ваш текущий уровень:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


async def process_plan_level(
        message: Message,
        state: FSMContext,
        agents: dict,
        use_rag: bool,
        get_or_create_user
):
    """Обработка уровня"""
    level_text = message.text.strip()

    # Определяем уровень по тексту
    if "начин" in level_text.lower():
        level = "Начинающий"
    elif "сред" in level_text.lower():
        level = "Средний"
    elif "продви" in level_text.lower():
        level = "Продвинутый"
    else:
        level = "Средний"

    # Сохраняем уровень
    await state.update_data(user_level=level)

    # Создаем клавиатуру для выбора времени
    builder = ReplyKeyboardBuilder()
    builder.button(text="⏳ 2-3 часа в неделю")
    builder.button(text="⏰ 5-7 часов в неделю")
    builder.button(text="⚡ 10+ часов в неделю")
    keyboard = builder.as_markup(resize_keyboard=True)

    await state.set_state(PlanStates.waiting_time)

    await message.answer(
        f"📊 <b>Уровень: {level}</b>\n\n"
        "<b>Сколько времени готовы уделять в неделю?</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


async def process_plan_time(
        message: Message,
        state: FSMContext,
        agents: dict,
        use_rag: bool,
        get_or_create_user
):
    """Обработка времени и создание плана"""
    time_text = message.text.strip()

    # Сохраняем время
    await state.update_data(user_time=time_text)

    # Получаем все данные
    data = await state.get_data()
    user_goal = data.get('user_goal', 'Тема не указана')
    user_level = data.get('user_level', 'Средний')

    # Показываем, что начинаем создавать план
    await message.answer(
        f"🔄 <b>Создаю план обучения...</b>\n\n"
        f"📚 <b>Тема:</b> {user_goal}\n"
        f"📊 <b>Уровень:</b> {user_level}\n"
        f"⏱️ <b>Время:</b> {time_text}\n\n"
        f"<i>Генерирую персонализированный план...</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove()
    )

    try:
        # Получаем Planner агента
        planner_agent = agents.get("planner")

        if not planner_agent:
            logger.error("PlannerAgent не найден в agents dict")
            raise Exception("Агент планирования недоступен")

        # Создаем контекст для плана
        plan_context = {
            'user_goal': user_goal,
            'user_level': user_level,
            'user_time': time_text,
            'weeks': 6,  # По умолчанию 6 недель
            'track': 'backend',  # Можно получать из данных пользователя
            'experience': f"Уровень: {user_level}",
            'goals': user_goal,
            'available_time': time_text
        }

        # Пробуем создать план через агента
        plan_result = None

        # Проверяем разные методы вызова
        if hasattr(planner_agent, 'make_plan'):
            plan_result = planner_agent.make_plan(plan_context)
        elif hasattr(planner_agent, 'create_plan'):
            plan_result = planner_agent.create_plan(plan_context)
        elif hasattr(planner_agent, 'process_query'):
            query = f"Создай план обучения по теме: {user_goal}, уровень: {user_level}, время: {time_text}"
            plan_result = await planner_agent.process_query(query, use_rag=use_rag)
        else:
            logger.warning("PlannerAgent не имеет известных методов создания плана")

        # Форматируем результат
        if plan_result:
            # Если план в виде dict
            if isinstance(plan_result, dict):
                plan_data = plan_result
            elif hasattr(plan_result, 'dict'):
                plan_data = plan_result.dict()
            else:
                plan_data = {'summary': str(plan_result)}
        else:
            # Fallback план
            plan_data = create_fallback_plan(user_goal, user_level, time_text)

        # Сохраняем план в состоянии
        await state.update_data(
            plan_data=plan_data,
            plan_goal=user_goal,
            plan_level=user_level,
            plan_time=time_text
        )

        # Форматируем ответ
        response = format_plan_response(plan_data, user_goal, user_level, time_text)

        # Создаем клавиатуру для действий
        builder = ReplyKeyboardBuilder()
        builder.button(text="✅ Да, показать детали")
        builder.button(text="❌ Нет, создать заново")
        keyboard = builder.as_markup(resize_keyboard=True)

        await state.set_state(PlanStates.confirm_details)

        await message.answer(
            response,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Ошибка создания плана: {e}", exc_info=True)

        # Fallback план при ошибке
        fallback_plan = create_fallback_plan(user_goal, "Средний", time_text)

        await state.update_data(
            plan_data=fallback_plan,
            plan_goal=user_goal,
            plan_level="Средний",
            plan_time=time_text
        )

        response = format_plan_response(fallback_plan, user_goal, "Средний", time_text)

        builder = ReplyKeyboardBuilder()
        builder.button(text="✅ Да, показать детали")
        builder.button(text="❌ Нет, создать заново")
        keyboard = builder.as_markup(resize_keyboard=True)

        await state.set_state(PlanStates.confirm_details)

        await message.answer(
            response,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )


async def process_plan_confirmation(
        message: Message,
        state: FSMContext,
        agents: dict,
        use_rag: bool,
        get_or_create_user
):
    """Обработка подтверждения плана"""
    user_choice = message.text.lower()

    if any(word in user_choice for word in ['да', 'yes', 'покажи', 'детал']):
        # Показываем детали плана
        data = await state.get_data()
        plan_data = data.get('plan_data', {})

        detailed_response = format_detailed_plan(plan_data)

        # Обрезаем если слишком длинно
        if len(detailed_response) > 4000:
            detailed_response = detailed_response[:4000] + "...\n\n<i>(план сокращен для отображения)</i>"

        # Создаем клавиатуру для сохранения
        builder = ReplyKeyboardBuilder()
        builder.button(text="💾 Сохранить план")
        builder.button(text="🔄 Создать новый")
        keyboard = builder.as_markup(resize_keyboard=True)

        await state.set_state(PlanStates.save_plan)

        await message.answer(
            detailed_response,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )

    elif any(word in user_choice for word in ['нет', 'no', 'заново', 'новый']):
        # Начинаем заново
        await state.clear()
        await cmd_plan(message, state)

    else:
        await message.answer("Пожалуйста, выберите вариант из кнопок ниже")


async def process_save_plan(
        message: Message,
        state: FSMContext,
        agents: dict,
        use_rag: bool,
        get_or_create_user
):
    """Сохранение плана"""
    user_choice = message.text

    if "сохран" in user_choice.lower():
        try:
            from db.models import SessionLocal
            from db.repository import PlanRepository

            data = await state.get_data()
            plan_data = data.get('plan_data', {})
            user_goal = data.get('plan_goal', 'План обучения')

            with SessionLocal() as db:
                user, db = get_or_create_user(message, db)

                # Сохраняем план
                plan_to_save = {
                    'title': f'План: {user_goal}',
                    'description': plan_data.get('summary', f'План изучения {user_goal}'),
                    'track': user.current_track or 'backend',
                    'level': data.get('plan_level', 'Средний'),
                    'duration_weeks': plan_data.get('total_weeks', 6),
                    'plan_data': plan_data,
                    'progress': 0.0
                }

                PlanRepository.save_learning_plan(db, message.from_user.id, plan_to_save)

                await message.answer(
                    "✅ <b>План успешно сохранен!</b>\n\n"
                    "Вы можете посмотреть его в любой момент через команду /progress",
                    parse_mode=ParseMode.HTML,
                    reply_markup=ReplyKeyboardRemove()
                )

        except Exception as e:
            logger.error(f"Ошибка сохранения плана: {e}")
            await message.answer(
                f"❌ <b>Не удалось сохранить план:</b> {str(e)}",
                parse_mode=ParseMode.HTML
            )

    elif "новый" in user_choice.lower():
        await state.clear()
        await cmd_plan(message, state)
        return

    await state.clear()


# ===================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====================

def create_fallback_plan(goal: str, level: str, time: str) -> dict:
    """Создание fallback плана при ошибке"""
    return {
        'total_weeks': 6,
        'focus_areas': [goal, 'Практические навыки', 'Теория'],
        'summary': f'6-недельный план изучения {goal} для уровня {level}',
        'plan': [
            {'week': 1, 'title': 'Основные концепции', 'topics': ['Введение', 'Базовые понятия'],
             'tasks': ['Изучить теорию'], 'estimated_hours': 5},
            {'week': 2, 'title': 'Углубленное изучение', 'topics': ['Детали', 'Примеры'],
             'tasks': ['Практическое задание'], 'estimated_hours': 7},
            {'week': 3, 'title': 'Практика', 'topics': ['Реальные кейсы'], 'tasks': ['Создать проект'],
             'estimated_hours': 10},
            {'week': 4, 'title': 'Продвинутые темы', 'topics': ['Оптимизация', 'Best practices'],
             'tasks': ['Улучшить проект'], 'estimated_hours': 8},
            {'week': 5, 'title': 'Интеграция', 'topics': ['Связь с другими технологиями'],
             'tasks': ['Интеграционное задание'], 'estimated_hours': 9},
            {'week': 6, 'title': 'Финальный проект', 'topics': ['Завершение'], 'tasks': ['Завершить проект'],
             'estimated_hours': 12}
        ],
        'resources': ['Официальная документация', 'Книги по теме', 'Онлайн-курсы']
    }


def format_plan_response(plan_data: dict, goal: str, level: str, time: str) -> str:
    """Форматирование ответа с планом"""
    weeks = plan_data.get('total_weeks', 6)
    focus_areas = ', '.join(plan_data.get('focus_areas', ['Основные концепции'])[:3])

    return f"""
✅ <b>План обучения создан!</b>

🎯 <b>Тема:</b> {goal}
📊 <b>Уровень:</b> {level}
⏱️ <b>Время:</b> {time}
📅 <b>Длительность:</b> {weeks} недель

📋 <b>Основные направления:</b>
{focus_areas}

📝 <b>Краткое описание:</b>
{plan_data.get('summary', 'Персонализированный план обучения')[:200]}...

<b>Показать детальный план по неделям?</b>
"""


def format_detailed_plan(plan_data: dict) -> str:
    """Форматирование детального плана"""
    response = "📋 <b>Детальный план обучения:</b>\n\n"

    plan_items = plan_data.get('plan', [])

    if not plan_items:
        response += "⚠️ Детали плана не указаны\n"
        return response

    for item in plan_items:
        week_num = item.get('week', 1)
        title = item.get('title', f'Неделя {week_num}')
        topics = ', '.join(item.get('topics', ['Темы не указаны'])[:3])
        tasks = item.get('tasks', ['Задачи не указаны'])
        hours = item.get('estimated_hours', 'N/A')

        response += f"<b>Неделя {week_num}: {title}</b>\n"
        response += f"📚 <i>Темы:</i> {topics}\n"

        if tasks and len(tasks) > 0:
            response += f"✅ <i>Задача:</i> {tasks[0]}\n"

        response += f"⏰ <i>Часов:</i> {hours}\n\n"

    # Добавляем ресурсы если есть
    resources = plan_data.get('resources', [])
    if resources:
        response += "📚 <b>Рекомендуемые ресурсы:</b>\n"
        for i, resource in enumerate(resources[:5], 1):
            response += f"{i}. {resource}\n"

    return response


# ===================== РЕГИСТРАЦИЯ ХЭНДЛЕРОВ =====================

def register_planning_handlers(dp: Router, agents: dict, use_rag: bool, get_or_create_user):
    """Регистрация хэндлеров планирования - ИСПРАВЛЕННАЯ"""

    # Команда /plan
    dp.message.register(cmd_plan, Command("plan"))

    # Обработка цели (что изучать)
    dp.message.register(
        lambda m: process_plan_goal(m, m.bot.state, agents, use_rag, get_or_create_user),
        PlanStates.waiting_goal
    )

    # Обработка уровня
    dp.message.register(
        lambda m: process_plan_level(m, m.bot.state, agents, use_rag, get_or_create_user),
        PlanStates.waiting_level
    )

    # Обработка времени и создание плана
    dp.message.register(
        lambda m: process_plan_time(m, m.bot.state, agents, use_rag, get_or_create_user),
        PlanStates.waiting_time
    )

    # Подтверждение и показ деталей
    dp.message.register(
        lambda m: process_plan_confirmation(m, m.bot.state, agents, use_rag, get_or_create_user),
        PlanStates.confirm_details
    )

    # Сохранение плана
    dp.message.register(
        lambda m: process_save_plan(m, m.bot.state, agents, use_rag, get_or_create_user),
        PlanStates.save_plan
    )