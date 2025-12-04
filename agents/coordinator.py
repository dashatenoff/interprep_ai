# agents/coordinator.py
import json
import sys
from pathlib import Path
from pydantic import BaseModel
from gigachat import GigaChat
from dotenv import load_dotenv
import os
from typing import Dict, Any, Optional

# Добавляем путь для импорта RAG
sys.path.append(str(Path(__file__).resolve().parent.parent))

# Импортируем RAG (с обработкой ошибок)
try:
    from rag.retriever import retrieve_context

    RAG_AVAILABLE = True
except ImportError:
    print("⚠️  RAG модуль не найден. Coordinator будет работать без базы знаний.")
    RAG_AVAILABLE = False


    def retrieve_context(query: str, k: int = 4) -> list:
        return []

# Загружаем токен из .env
load_dotenv()


# ===============================
#  Модель данных для маршрутизации
# ===============================
class RouteResult(BaseModel):
    agent: str
    context: str
    metadata: dict
    confidence: float
    suggested_topics: Optional[list] = None
    rag_context_used: Optional[bool] = False


# ===============================
#  Класс координатора с RAG
# ===============================
class CoordinatorAgent:
    def __init__(self, use_rag: bool = True):
        load_dotenv()
        self.client_secret = os.getenv("GIGACHAT_CLIENT_SECRET")
        if not self.client_secret:
            raise ValueError("❌ Не найден GIGACHAT_CLIENT_SECRET в .env")

        # Инициализация клиента GigaChat
        self.llm = GigaChat(credentials=self.client_secret, verify_ssl_certs=False)

        self.use_rag = use_rag and RAG_AVAILABLE

        # Промпты с RAG и без
        self.prompt_without_rag = """
        Ты — координатор (Coordinator) для бота подготовки к собеседованиям.

        Определи, какой агент должен обработать запрос пользователя.

        ДОСТУПНЫЕ АГЕНТЫ:
        1. INTERVIEWER — для проведения интервью, вопросов-ответов, mock интервью
        2. ASSESSOR — для оценки знаний, тестов, диагностики уровня
        3. PLANNER — для создания планов развития, roadmap, рекомендаций
        4. REVIEWER — для разбора кода, ревью решений задач
        5. HELPER — для общих вопросов о собеседованиях, советы

        ЗАПРОС ПОЛЬЗОВАТЕЛЯ: {user_text}

        Верни результат строго в формате JSON:
        {{
          "agent": "НАЗВАНИЕ_АГЕНТА",
          "context": "краткое описание контекста запроса",
          "metadata": {{
            "topic": "основная тема",
            "urgency": "high/medium/low",
            "complexity": "beginner/intermediate/advanced"
          }},
          "confidence": 0.95,
          "suggested_topics": ["тема1", "тема2"]
        }}
        """

        self.prompt_with_rag = """
        Ты — умный координатор с доступом к базе знаний о собеседованиях.

        КОНТЕКСТ ИЗ БАЗЫ ЗНАНИЙ (релевантные вопросы и темы):
        {rag_context}

        Определи наиболее подходящего агента для запроса пользователя.

        ДОСТУПНЫЕ АГЕНТЫ:
        1. INTERVIEWER — вопросы с собеседований, mock интервью, технические вопросы
        2. ASSESSOR — оценка уровня, диагностика пробелов, тестирование знаний
        3. PLANNER — план обучения, roadmap, рекомендации по подготовке
        4. REVIEWER — разбор кода, оптимизация решений, code review
        5. HELPER — советы по собеседованиям, поведенческие вопросы, переговоры

        Анализируй запрос с учетом контекста из базы знаний.

        ЗАПРОС ПОЛЬЗОВАТЕЛЯ: {user_text}

        Верни результат строго в формате JSON:
        {{
          "agent": "НАЗВАНИЕ_АГЕНТА",
          "context": "анализ запроса с учетом контекста",
          "metadata": {{
            "primary_topic": "главная тема",
            "secondary_topics": ["дополнительные темы"],
            "interview_type": "technical/behavioral/system_design",
            "experience_level": "junior/middle/senior"
          }},
          "confidence": 0.0-1.0,
          "suggested_topics": ["конкретные темы из контекста"],
          "rag_context_used": true
        }}
        """

    def _get_rag_context_for_routing(self, user_text: str) -> str:
        """Получает контекст из RAG для помощи в маршрутизации"""
        if not self.use_rag:
            return ""

        try:
            # Ищем похожие запросы в базе знаний
            context_chunks = retrieve_context(user_text, k=2)

            # Дополнительный поиск по ключевым словам
            if not context_chunks:
                # Извлекаем ключевые слова из запроса
                keywords = self._extract_keywords(user_text)
                for keyword in keywords[:3]:
                    keyword_context = retrieve_context(keyword, k=1)
                    context_chunks.extend(keyword_context)

            if context_chunks:
                formatted_context = "\n".join([
                    f"📚 Контекст {i + 1}: {chunk[:200]}..."
                    for i, chunk in enumerate(context_chunks)
                ])
                return formatted_context
            return "Нет релевантного контекста в базе знаний."

        except Exception as e:
            print(f"⚠️  Ошибка RAG в Coordinator: {e}")
            return ""

    def _extract_keywords(self, text: str) -> list:
        """Извлекает ключевые слова из текста (упрощенная версия)"""
        # Список технических терминов
        tech_keywords = [
            "python", "java", "javascript", "алгоритм", "база данных", "sql",
            "ооп", "интервью", "собеседование", "оценка", "план", "код",
            "junior", "middle", "senior", "backend", "frontend", "devops",
            "docker", "kubernetes", "микросервис", "api", "rest", "graphql"
        ]

        text_lower = text.lower()
        found_keywords = []

        for keyword in tech_keywords:
            if keyword in text_lower:
                found_keywords.append(keyword)

        return found_keywords[:5]

    def route(self, user_text: str) -> RouteResult:
        """Маршрутизирует запрос пользователя с использованием RAG"""

        # Получаем контекст из RAG
        rag_context = self._get_rag_context_for_routing(user_text)

        # Выбираем промпт
        if self.use_rag and rag_context and "Контекст" in rag_context:
            prompt = self.prompt_with_rag.format(
                user_text=user_text,
                rag_context=rag_context
            )
            rag_context_used = True
        else:
            prompt = self.prompt_without_rag.format(user_text=user_text)
            rag_context_used = False

        # Отправляем в GigaChat
        try:
            response = self.llm.chat(prompt)
            text = response.choices[0].message.content.strip()

            # 🧹 Очистка ответа от Markdown и лишнего текста
            text = self._clean_response(text)

            # Парсим JSON
            data = json.loads(text)

            return RouteResult(
                agent=data.get("agent", "INTERVIEWER"),
                context=data.get("context", "Общий запрос"),
                metadata=data.get("metadata", {}),
                confidence=data.get("confidence", 0.5),
                suggested_topics=data.get("suggested_topics", []),
                rag_context_used=rag_context_used
            )

        except json.JSONDecodeError as e:
            print(f"❌ Ошибка парсинга JSON в Coordinator: {e}")
            print(f"Ответ модели: {text[:200] if 'text' in locals() else 'Нет ответа'}")

            # Пытаемся определить агента по ключевым словам
            agent = self._fallback_agent_detection(user_text)

            return RouteResult(
                agent=agent,
                context="Ошибка парсинга, использовано fallback определение",
                metadata={"error": str(e), "fallback": True},
                confidence=0.3,
                rag_context_used=rag_context_used
            )

        except Exception as e:
            print(f"❌ Общая ошибка в Coordinator.route: {e}")

            return RouteResult(
                agent="INTERVIEWER",
                context=f"Ошибка обработки: {str(e)[:100]}",
                metadata={"error": str(e)},
                confidence=0.1,
                rag_context_used=rag_context_used
            )

    def _clean_response(self, text: str) -> str:
        """Очищает ответ от Markdown и лишнего текста"""
        # Удаляем Markdown блоки
        if text.startswith("```json"):
            text = text[7:]  # Убираем ```json
        elif text.startswith("```"):
            text = text[3:]  # Убираем ```

        if text.endswith("```"):
            text = text[:-3]

        # Находим JSON в тексте
        import re
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            return json_match.group()

        return text.strip()

    def _fallback_agent_detection(self, user_text: str) -> str:
        """Fallback определение агента по ключевым словам"""
        text_lower = user_text.lower()

        keyword_mapping = {
            "interviewer": ["интервью", "опрос", "вопрос", "задай", "проведи", "mock"],
            "assessor": ["оцен", "тест", "провер", "уровень", "насколько", "диагнос"],
            "planner": ["план", "roadmap", "программа", "расписан", "рекомендац"],
            "reviewer": ["код", "решение", "задача", "оптимиз", "ревью", "разбор"],
            "helper": ["совет", "как", "подготов", "что делать", "помощь"]
        }

        for agent, keywords in keyword_mapping.items():
            if any(keyword in text_lower for keyword in keywords):
                return agent.upper()

        return "INTERVIEWER"  # Агент по умолчанию

    def route_with_history(self, user_text: str, history: list = None) -> RouteResult:
        """Маршрутизация с учетом истории диалога"""
        if not history:
            return self.route(user_text)

        # Формируем контекст из истории
        history_context = "\n".join([
            f"{'Пользователь' if msg['role'] == 'user' else 'Бот'}: {msg['content'][:100]}..."
            for msg in history[-3:]  # Последние 3 сообщения
        ])

        prompt = f"""
        История диалога:
        {history_context}

        Новый запрос пользователя: {user_text}

        Определи агента с учетом контекста диалога.
        """

        response = self.llm.chat(prompt)
        return self.route(f"{user_text} [контекст: {response.choices[0].message.content[:100]}]")