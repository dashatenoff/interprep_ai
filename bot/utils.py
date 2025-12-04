# bot/utils.py
import logging
from pathlib import Path
from typing import Dict, Any, Tuple
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def setup_database() -> bool:
    """Инициализация базы данных"""
    try:
        from db.models import init_db
        engine = init_db()

        # Проверяем подключение
        from db.models import SessionLocal
        with SessionLocal() as db:
            from db.models import User
            user_count = db.query(User).count()
            logger.info(f"👥 Пользователей в БД: {user_count}")

        return True
    except Exception as e:
        logger.error(f"❌ Ошибка БД: {e}")
        return False


def setup_rag() -> Dict[str, Any]:
    """Проверка и настройка RAG"""
    try:
        from rag.retriever import check_database_status
        status = check_database_status()
        return status
    except ImportError:
        logger.warning("RAG модуль не найден")
        return {"status": "not_found", "error": "Module not found"}
    except Exception as e:
        logger.error(f"Ошибка RAG: {e}")
        return {"status": "error", "error": str(e)}


def setup_agents(use_rag: bool = False) -> Dict[str, Any]:
    """Инициализация всех агентов"""
    agents = {}

    try:
        # Пробуем импортировать всех агентов
        try:
            from agents.coordinator import CoordinatorAgent
            from agents.assessor_agent import AssessorAgent
            from agents.planner_agent import PlannerAgent
            from agents.interviewer_agent import InterviewerAgent
            from agents.reviewer import ReviewerAgent

            agents["coordinator"] = CoordinatorAgent(use_rag=use_rag)
            agents["assessor"] = AssessorAgent(use_rag=use_rag)
            agents["planner"] = PlannerAgent(use_rag=use_rag)
            agents["interviewer"] = InterviewerAgent(use_rag=use_rag)
            agents["reviewer"] = ReviewerAgent(use_rag=use_rag)

            # Проверяем, создались ли агенты
            for name, agent in agents.items():
                if not agent:
                    logger.warning(f"⚠️  Агент {name} не создан")
                    agents[name] = None

            logger.info(f"✅ Агенты созданы (RAG: {'ВКЛ' if use_rag else 'ВЫКЛ'})")

        except ImportError as import_error:
            logger.warning(f"⚠️  Не все агенты доступны: {import_error}")

            # Создаем заглушки для отсутствующих агентов
            class StubAgent:
                def __init__(self, name):
                    self.name = name

                def route(self, *args, **kwargs):
                    return type('obj', (object,), {
                        'agent': 'ASSESSOR',
                        'context': 'Недоступно',
                        'metadata': {}
                    })()

                def assess(self, *args, **kwargs):
                    return type('obj', (object,), {
                        'scores': {},
                        'follow_up': 'Агент временно недоступен',
                        'context_used': False
                    })()

            if "coordinator" not in agents:
                agents["coordinator"] = StubAgent("coordinator")
            if "assessor" not in agents:
                agents["assessor"] = StubAgent("assessor")
            if "planner" not in agents:
                agents["planner"] = StubAgent("planner")
            if "interviewer" not in agents:
                agents["interviewer"] = StubAgent("interviewer")
            if "reviewer" not in agents:
                agents["reviewer"] = StubAgent("reviewer")

        return agents

    except Exception as e:
        logger.error(f"❌ Ошибка создания агентов: {e}")
        # Возвращаем пустой словарь, чтобы бот мог работать в базовом режиме
        return {}


def get_or_create_user(message, db: Session = None) -> Tuple[Any, Session]:
    """Получает или создает пользователя"""
    from db.models import SessionLocal
    from db.repository import UserRepository

    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        # Используем метод из UserRepository
        user = UserRepository.get_or_create_user(
            db=db,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name
        )

        logger.info(f"👤 Пользователь получен/создан: {user.username or user.telegram_id}")
        return user, db

    except Exception as e:
        logger.error(f"❌ Ошибка работы с пользователем: {e}")
        db.rollback()
        raise
    finally:
        if close_db:
            db.close()


def get_bot_commands() -> list:
    """Возвращает список команд для бота"""
    from aiogram import types

    return [
        types.BotCommand(command="start", description="Запуск бота"),
        types.BotCommand(command="help", description="Помощь"),
        types.BotCommand(command="begin", description="Начать подготовку"),
        types.BotCommand(command="assess", description="Оценка навыков"),
        types.BotCommand(command="interview", description="Собеседование"),
        types.BotCommand(command="plan", description="План обучения"),
        types.BotCommand(command="review", description="Проверка кода"),
        types.BotCommand(command="progress", description="Мой прогресс"),
        types.BotCommand(command="status", description="Статус системы"),
        types.BotCommand(command="rag_status", description="Статус RAG"),
    ]