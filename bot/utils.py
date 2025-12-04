# bot/utils.py
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)

def setup_database():
    """Инициализация базы данных"""
    from db.init_db import setup_database as init_db
    return init_db()

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
        from agents.coordinator import CoordinatorAgent
        from agents.assessor import AssessorAgent
        from agents.planner import PlannerAgent
        from agents.interviewer import InterviewerAgent
        from agents.reviewer import ReviewerAgent

        agents["coordinator"] = CoordinatorAgent(use_rag=use_rag)
        agents["assessor"] = AssessorAgent(use_rag=use_rag)
        agents["planner"] = PlannerAgent(use_rag=use_rag)
        agents["interviewer"] = InterviewerAgent(use_rag=use_rag)
        agents["reviewer"] = ReviewerAgent(use_rag=use_rag)

        logger.info(f"✅ Агенты созданы (RAG: {'ВКЛ' if use_rag else 'ВЫКЛ'})")
        return agents

    except ImportError as e:
        logger.error(f"Ошибка импорта агентов: {e}")
        raise
    except Exception as e:
        logger.error(f"Ошибка создания агентов: {e}")
        raise

def get_or_create_user(message):
    """Получает или создает пользователя"""
    from db.models import SessionLocal
    from db.repository import UserRepository

    with SessionLocal() as db:
        user = UserRepository.get_or_create_user(
            db=db,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name
        )
        return user, db