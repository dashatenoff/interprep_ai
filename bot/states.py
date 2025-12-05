# bot/states.py
from aiogram.fsm.state import State, StatesGroup


class UserStates(StatesGroup):
    # План
    waiting_goal = State()  # ← ОБЯЗАТЕЛЬНО должно быть
    creating_plan = State()  # ← ОБЯЗАТЕЛЬНО должно быть

    # Остальные состояния
    waiting_for_level = State()
    waiting_for_track = State()
    waiting_for_plan_data = State()
    customizing_plan = State()
    waiting_for_days = State()
    waiting_for_hours = State()