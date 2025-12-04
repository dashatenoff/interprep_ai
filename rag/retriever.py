# rag/retriever.py
from pathlib import Path
import chromadb
from chromadb.config import Settings
from typing import List, Dict, Any, Optional
import json

BASE_DIR = Path(__file__).resolve().parent.parent
PERSIST_DIR = BASE_DIR / "chroma_db"
COLLECTION_NAME = "interprep_knowledge"

# Кэш для быстродействия
_vectorstore = None


def get_vectorstore():
    """Получает векторное хранилище"""
    global _vectorstore

    if _vectorstore is None:
        if not PERSIST_DIR.exists():
            raise FileNotFoundError(
                f"База знаний не найдена в {PERSIST_DIR}.\n"
                f"Запустите: python rag/ingest.py"
            )

        client = chromadb.PersistentClient(
            path=str(PERSIST_DIR),
            settings=Settings(anonymized_telemetry=False)
        )

        try:
            _vectorstore = client.get_collection(COLLECTION_NAME)
        except:
            raise ValueError(
                f"Коллекция '{COLLECTION_NAME}' не найдена.\n"
                f"Запустите: python rag/ingest.py"
            )

    return _vectorstore


def retrieve_context(
        query: str,
        k: int = 3,
        filter_by: Optional[Dict] = None,
        agent: Optional[str] = None
) -> List[str]:
    """
    Ищет релевантные документы

    Args:
        query: Поисковый запрос
        k: Количество результатов
        filter_by: Дополнительные фильтры
        agent: Имя агента для фильтрации

    Returns:
        Список текстов документов
    """
    try:
        vs = get_vectorstore()

        # Добавляем фильтр по агенту если указан
        where_filter = filter_by or {}
        if agent:
            where_filter["agent"] = agent

        results = vs.query(
            query_texts=[query],
            n_results=k,
            where=where_filter if where_filter else None,
            include=["documents", "metadatas"]
        )

        if results and results['documents']:
            return results['documents'][0]
        return []

    except Exception as e:
        print(f"⚠️  Ошибка поиска в базе знаний: {e}")
        return []


def retrieve_for_agent(agent_name: str, query: str, k: int = 3) -> List[str]:
    """
    Ищет контекст для конкретного агента
    """
    # Маппинг агентов к типам документов
    agent_to_type = {
        "interviewer": "interview_question",
        "reviewer": "code_example",
        "planner": "learning_plan",
        "assessor": "interview_question",  # assessor тоже использует вопросы
    }

    doc_type = agent_to_type.get(agent_name)
    filter_by = {"type": doc_type} if doc_type else None

    return retrieve_context(query, k, filter_by, agent_name)


def get_questions_by_topic(topic: str, difficulty: Optional[str] = None, limit: int = 5) -> List[Dict]:
    """Получает вопросы по теме и сложности"""
    try:
        vs = get_vectorstore()

        where_filter = {
            "type": "interview_question",
            "topic": topic
        }

        if difficulty:
            where_filter["difficulty"] = difficulty

        results = vs.query(
            query_texts=[topic],
            n_results=limit,
            where=where_filter,
            include=["documents", "metadatas"]
        )

        questions = []
        if results and results['documents']:
            for doc, meta in zip(results['documents'][0], results['metadatas'][0]):
                # Парсим вопрос и ответ из текста
                lines = doc.split('\n')
                question = ""
                answer = ""

                for line in lines:
                    if line.startswith("Вопрос:"):
                        question = line.replace("Вопрос:", "").strip()
                    elif line.startswith("Ответ:"):
                        answer = line.replace("Ответ:", "").strip()

                if question and answer:
                    questions.append({
                        "question": question,
                        "answer": answer,
                        "topic": meta.get("topic", ""),
                        "difficulty": meta.get("difficulty", ""),
                        "level": meta.get("level", ""),
                        "metadata": meta
                    })

        return questions

    except Exception as e:
        print(f"⚠️  Ошибка получения вопросов: {e}")
        return []


def build_prompt_with_context(question: str, context_chunks: List[str], agent: str = None) -> str:
    """
    Строит промпт с контекстом

    Args:
        question: Вопрос пользователя
        context_chunks: Найденные документы
        agent: Имя агента для кастомизации промпта

    Returns:
        Готовый промпт
    """
    if not context_chunks:
        return question

    # Формируем контекст
    context_lines = []
    for i, chunk in enumerate(context_chunks, 1):
        context_lines.append(f"[Контекст {i}]")
        context_lines.append(chunk)
        context_lines.append("")  # Пустая строка между контекстами

    context = "\n".join(context_lines).strip()

    # Базовый промпт для всех агентов
    base_prompt = f"""Используй информацию ниже для ответа на вопрос.

КОНТЕКСТ:
{context}

ВОПРОС ПОЛЬЗОВАТЕЛЯ: {question}

ОТВЕТ:"""

    # Специфичные промпты для агентов
    agent_prompts = {
        "interviewer": f"""Ты — технический интервьюер. Используй контекст для создания вопросов или оценки ответов.

КОНТЕКСТ (реальные вопросы и ответы с собеседований):
{context}

ВОПРОС: {question}

ОТВЕТ ИНТЕРВЬЮЕРА:""",

        "reviewer": f"""Ты — code reviewer. Используй контекст для анализа кода.

КОНТЕКСТ (лучшие практики и примеры кода):
{context}

КОД ДЛЯ АНАЛИЗА: {question}

РЕВЬЮ:""",

        "planner": f"""Ты — планировщик обучения. Используй контекст для создания планов.

КОНТЕКСТ (планы обучения и ресурсы):
{context}

ЗАПРОС ПОЛЬЗОВАТЕЛЯ: {question}

ПЛАН ОБУЧЕНИЯ:""",

        "assessor": f"""Ты — оценщик знаний. Используй контекст для оценки ответов.

КОНТЕКСТ (правильные ответы и критерии оценки):
{context}

ОТВЕТ КАНДИДАТА: {question}

ОЦЕНКА:"""
    }

    return agent_prompts.get(agent, base_prompt)


def check_database_status() -> Dict[str, Any]:
    """Проверяет статус базы знаний"""
    try:
        vs = get_vectorstore()
        count = vs.count()

        # Получаем статистику по типам
        results = vs.get(include=["metadatas"])
        types_count = {}
        agents_count = {}

        if results and results["metadatas"]:
            for meta in results["metadatas"]:
                doc_type = meta.get("type", "unknown")
                agent = meta.get("agent", "unknown")

                types_count[doc_type] = types_count.get(doc_type, 0) + 1
                agents_count[agent] = agents_count.get(agent, 0) + 1

        return {
            "status": "ready",
            "documents_count": count,
            "types": types_count,
            "agents": agents_count,
            "path": str(PERSIST_DIR)
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "path": str(PERSIST_DIR),
            "exists": PERSIST_DIR.exists()
        }


# Быстрый тест
if __name__ == "__main__":
    print("🔍 Тестирую RAG систему...")

    status = check_database_status()
    print(f"Статус: {status.get('status', 'unknown')}")

    if status["status"] == "ready":
        print(f"📊 Документов: {status['documents_count']}")

        # Тест для каждого агента
        agents = ["interviewer", "reviewer", "planner", "assessor"]

        for agent in agents:
            print(f"\n🧠 {agent.upper()}:")
            test_query = "Python" if agent != "planner" else "обучение"
            results = retrieve_for_agent(agent, test_query, k=1)

            if results:
                print(f"   ✅ Найдено: {results[0][:80]}...")
            else:
                print(f"   ⚠️  Не найдено")
    else:
        print(f"❌ Ошибка: {status.get('error', 'Неизвестная ошибка')}")
        print("Запустите: python rag/ingest.py")