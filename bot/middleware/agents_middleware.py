# bot/middleware/agents_middleware.py
import logging
import traceback
from aiogram import BaseMiddleware
from typing import Callable, Dict, Any, Awaitable
from aiogram.types import Message, Update

logger = logging.getLogger(__name__)


class AgentsMiddleware(BaseMiddleware):
    def __init__(self, coordinator, agents, use_rag: bool = True):
        self.coordinator = coordinator
        self.agents = agents
        self.use_rag = use_rag

    async def __call__(
            self,
            handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],  # ← Update, не Message!
            event: Update,  # ← Update, не Message!
            data: Dict[str, Any]
    ) -> Any:

        # ========== ОТЛАДКА ==========
        print("=" * 60)

        # Получаем message из event
        message = None
        if hasattr(event, 'message'):
            message = event.message
        elif hasattr(event, 'callback_query'):
            message = event.callback_query.message

        message_text = message.text[:50] if message and hasattr(message, 'text') and message.text else 'Нет текста'

        print(f"🔴 MIDDLEWARE START для: {message_text}")
        print(f"🔴 Тип event: {type(event)}")
        print(f"🔴 self.use_rag type: {type(self.use_rag)}, value: {self.use_rag}")
        print(f"🔴 self.agents type: {type(self.agents)}")
        if isinstance(self.agents, dict):
            print(f"🔴 self.agents keys: {list(self.agents.keys())}")
        # =============================

        # ВСЕГДА передаем agents и use_rag в data
        data['agents'] = self.agents
        data['use_rag'] = self.use_rag

        # Получаем состояние пользователя
        state = data.get("state")

        # Если это сообщение и у нас есть состояние
        if message and state:
            try:
                current_state = await state.get_state()
                print(f"🔴 Текущее состояние: {current_state}")

                # Пропускаем координатор для состояний планирования
                planning_states = [
                    'UserStates:waiting_goal',
                    'UserStates:creating_plan',
                    'UserStates:customizing_plan',
                    'UserStates:waiting_for_days',
                    'UserStates:waiting_for_hours',
                    None  # тоже пропускаем координатор если нет состояния
                ]

                if current_state in planning_states:
                    print(f"🔴 Пропускаем координатор, передаем напрямую хендлеру")
                    # ВАЖНО: передаем данные для хендлера
                    data['agent_type'] = 'PLANNER'
                    data['route_result'] = None

                    print(f"🔴 Передаю в хендлер:")
                    print(f"   agents: {type(data['agents'])}")
                    print(f"   use_rag: {type(data['use_rag'])} = {data['use_rag']}")
                    print("=" * 60)

                    try:
                        return await handler(event, data)
                    except Exception as e:
                        print(f"🔴 ОШИБКА в хендлере: {e}")
                        traceback.print_exc()
                        raise

            except Exception as e:
                print(f"🔴 Ошибка получения состояния: {e}")
                traceback.print_exc()
                # Если ошибка - продолжаем обычную логику

        # Оригинальная логика координатора (для обычных сообщений)
        if message:  # только для сообщений
            try:
                # Получаем данные пользователя
                user_data = await state.get_data() if state else {}

                # Маршрутизируем через координатор
                route_result = self.coordinator.route(
                    user_text=message.text or "",
                    user_context={
                        'level': user_data.get('level', 'junior'),
                        'track': user_data.get('track', 'backend'),
                        'current_mode': user_data.get('current_mode', 'general')
                    }
                )

                print(f"🔴 Координатор определил агента: {route_result.agent}")

                # Сохраняем результат в data
                data['agent_type'] = route_result.agent
                data['route_result'] = route_result

            except Exception as e:
                print(f"🔴 Ошибка в координаторе: {e}")
                traceback.print_exc()
                data['agent_type'] = 'INTERVIEWER'
                data['route_result'] = None

        print(f"🔴 MIDDLEWARE END, передаю agent_type: {data.get('agent_type')}")
        print("=" * 60)
        return await handler(event, data)