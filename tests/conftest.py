# tests/conftest.py
import os
import sys
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from pathlib import Path

# Добавляем корень проекта в путь
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Импорты из вашего проекта
from agents.assessor_agent import AssessorAgent
from agents.coordinator import CoordinatorAgent
from agents.interviewer_agent import InterviewerAgent
from agents.planner_agent import PlannerAgent
from agents.reviewer import ReviewerAgent
from rag.retriever import (
    retrieve_context,
    retrieve_for_agent,
    get_questions_by_topic,
    build_prompt_with_context,
    check_database_status
)


@pytest.fixture(scope="session")
def event_loop():
    """Создаем event loop для асинхронных тестов."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_data_dir():
    """Путь к тестовым данным."""
    return project_root / "tests" / "fixtures"


@pytest.fixture
def mock_vectorstore():
    """Мок векторного хранилища ChromaDB."""
    mock_vs = Mock()

    # Мокаем методы, которые использует ваш RAG
    mock_vs.query = Mock(return_value={
        'documents': [['Пример документа 1', 'Пример документа 2']],
        'metadatas': [[
            {'type': 'interview_question', 'topic': 'Python', 'difficulty': 'easy'},
            {'type': 'code_example', 'topic': 'Python', 'agent': 'reviewer'}
        ]]
    })

    mock_vs.count = Mock(return_value=100)
    mock_vs.get = Mock(return_value={
        'metadatas': [
            {'type': 'interview_question', 'agent': 'interviewer'},
            {'type': 'code_example', 'agent': 'reviewer'},
            {'type': 'learning_plan', 'agent': 'planner'}
        ]
    })

    return mock_vs


@pytest.fixture(autouse=True)
def mock_rag_dependencies(mock_vectorstore):
    """Мокаем зависимости RAG системы для тестов."""
    # 1. Мокаем get_vectorstore чтобы возвращать наш mock
    with patch('rag.retriever.get_vectorstore', return_value=mock_vectorstore):
        # 2. Мокаем проверку директории
        with patch('pathlib.Path.exists', return_value=True):
            # 3. Мокаем client
            mock_client = Mock()
            mock_client.get_collection = Mock(return_value=mock_vectorstore)

            with patch('chromadb.PersistentClient', return_value=mock_client):
                yield


@pytest.fixture
def sample_questions():
    """Пример вопросов для тестов."""
    return [
        {
            "question": "Что такое инкапсуляция в ООП?",
            "answer": "Инкапсуляция - это механизм языка, позволяющий объединить данные и методы, работающие с ними, в единый объект.",
            "topic": "Python",
            "difficulty": "easy",
            "level": "junior"
        },
        {
            "question": "Чем отличается list от tuple в Python?",
            "answer": "List изменяемый, tuple неизменяемый. List использует квадратные скобки [], tuple - круглые ().",
            "topic": "Python",
            "difficulty": "easy",
            "level": "junior"
        }
    ]


@pytest.fixture
def assessor_agent():
    """Фикстура для агента-оценщика."""
    # Создаем мок без реального агента
    agent = Mock()
    agent.name = "Assessor"
    agent.assess_answer = Mock(return_value={
        "feedback": "Хороший ответ! Вы правильно объяснили концепцию.",
        "score": 8,
        "recommendations": ["Изучите паттерн Repository"]
    })
    return agent


@pytest.fixture
def interviewer_agent(sample_questions):
    """Фикстура для интервьюера."""
    agent = Mock()
    agent.name = "Interviewer"
    agent.generate_questions = Mock(return_value=[
        "Что такое инкапсуляция в ООП?",
        "Объясните принцип полиморфизма"
    ])
    return agent


@pytest.fixture
def coordinator_agent():
    """Фикстура для координатора."""
    agent = Mock()
    agent.name = "Coordinator"
    agent.process_query = Mock(return_value={
        "response": "Я помогу вам подготовиться. Начнем с вопросов по Python ООП.",
        "next_agent": "interviewer"
    })
    return agent


@pytest.fixture
def planner_agent():
    """Фикстура для планировщика."""
    agent = Mock()
    agent.name = "Planner"
    agent.create_plan = Mock(return_value={
        "plan": "План на неделю:\nДень 1: Основы Python\nДень 2: ООП\nДень 3: Алгоритмы",
        "duration_days": 7,
        "topics": ["Python", "ООП", "Алгоритмы"]
    })
    return agent


@pytest.fixture
def rag_retriever():
    """Фикстура для тестирования RAG модуля напрямую."""
    return sys.modules['rag.retriever']


# Дополнительные фикстуры для тестов метрик
@pytest.fixture
def mock_test_scenarios():
    """Мок тестовых сценариев для метрики точности."""
    return [
        {
            "id": "test_1",
            "agent": "Coordinator",
            "relevant": True,
            "response": "Начнем собеседование по Python ООП"
        },
        {
            "id": "test_2",
            "agent": "Interviewer",
            "relevant": True,
            "response": "Что такое инкапсуляция?"
        }
    ]


@pytest.fixture
def mock_feedback_data():
    """Мок данных для теста качества фидбэка."""
    return {
        "total_recommendations": 40,
        "useful_recommendations": 33,
        "usefulness_percentage": 82.5
    }