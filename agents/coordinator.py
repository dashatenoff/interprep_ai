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

        self.llm = GigaChat(
            credentials=self.client_secret,
            verify_ssl_certs=False,
            model="GigaChat"
        )
        self.use_rag = use_rag and RAG_AVAILABLE

        # Сохраняем оригинальные промпты
        self.prompt_without_rag = """
Ты — координатор (Coordinator) для бота подготовки к собеседованиям.

КОНТЕКСТ ПОЛЬЗОВАТЕЛЯ:
{user_context}

ЗАПРОС ПОЛЬЗОВАТЕЛЯ: {user_text}

ДОСТУПНЫЕ АГЕНТЫ:
1. INTERVIEWER — для проведения интервью, вопросов-ответов, mock интервью
2. ASSESSOR — для оценки знаний, тестов, диагностики уровня, советы по собеседованиям, поведенческие вопросы, переговоры
3. PLANNER — для создания планов развития, roadmap, рекомендаций
4. REVIEWER — для разбора кода, ревью решений задач

Верни результат строго в формате JSON:
{{
  "agent": "НАЗВАНИЕ_АГЕНТА",
  "context": "краткое описание контекста запроса",
  "metadata": {{
    "topic": "основная тема",
    "urgency": "high/medium/low",
    "complexity": "beginner/intermediate/advanced",
    "experience_level": "junior/middle/senior"
  }},
  "confidence": 0.95,
  "suggested_topics": ["тема1", "тема2"]
}}
"""

        self.prompt_with_rag = """
Ты — умный координатор с доступом к базе знаний о собеседованиях.

КОНТЕКСТ ПОЛЬЗОВАТЕЛЯ:
{user_context}

КОНТЕКСТ ИЗ БАЗЫ ЗНАНИЙ (релевантные вопросы и темы):
{rag_context}

Определи наиболее подходящего агента для запроса пользователя.

ДОСТУПНЫЕ АГЕНТЫ:
1. INTERVIEWER — вопросы с собеседований, mock интервью, технические вопросы
2. ASSESSOR — оценка уровня, диагностика пробелов, тестирование знаний, советы по собеседованиям, поведенческие вопросы, переговоры
3. PLANNER — план обучения, roadmap, рекомендации по подготовке
4. REVIEWER — разбор кода, оптимизация решений, code review

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
        """Получает контекст из RAG для помощи в маршрутизации (оригинальная)"""
        if not self.use_rag:
            return ""

        try:
            context_chunks = retrieve_context(user_text, k=2)

            if not context_chunks:
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
        """Извлекает ключевые слова из текста (оригинальная)"""
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

    def route(self, user_text: str, user_context: dict = None) -> RouteResult:
        """Маршрутизирует запрос пользователя с использованием RAG (улучшенная)"""

        if user_context is None:
            user_context = {}

        # Формируем контекст пользователя
        context_parts = []
        if 'level' in user_context:
            context_parts.append(f"Уровень: {user_context['level']}")
        if 'track' in user_context:
            context_parts.append(f"Направление: {user_context['track']}")
        if 'current_mode' in user_context:
            context_parts.append(f"Текущий режим: {user_context['current_mode']}")

        user_context_str = "\n".join(context_parts) if context_parts else "Нет дополнительного контекста"

        # Получаем контекст из RAG
        rag_context = self._get_rag_context_for_routing(user_text)

        # Выбираем промпт
        if self.use_rag and rag_context and "Контекст" in rag_context:
            prompt = self.prompt_with_rag.format(
                user_context=user_context_str,
                user_text=user_text,
                rag_context=rag_context
            )
            rag_context_used = True
        else:
            prompt = self.prompt_without_rag.format(
                user_context=user_context_str,
                user_text=user_text
            )
            rag_context_used = False

        if user_text.lower().startswith(('/plan', 'план', 'планирование', 'learning plan')):
            # Явно возвращаем PLANNER для таких запросов
            return RouteResult(
                agent="PLANNER",
                context="Пользователь явно запрашивает создание плана обучения",
                metadata={"topic": "planning", "urgency": "medium"},
                confidence=0.95,
                suggested_topics=["обучение", "развитие"],
                rag_context_used=False
            )

        try:
            response = self.llm.chat(prompt)
            text = response.choices[0].message.content.strip()

            # Очистка ответа
            text = self._clean_response(text)

            # ДОБАВЛЕНО: Исправляем проблемные символы в JSON
            text = self._fix_json_problems(text)

            # ДОБАВЛЕНО: Логируем что получаем для отладки
            print(f"📥 Coordinator получил: {text[:100]}...")

            # Парсим JSON
            data = json.loads(text)

            # Нормализуем имя агента
            agent_name = data.get("agent", "INTERVIEWER").upper()
            agent_name = self._normalize_agent_name(agent_name)

            return RouteResult(
                agent=agent_name,
                context=data.get("context", "Общий запрос"),
                metadata=data.get("metadata", {}),
                confidence=min(max(data.get("confidence", 0.5), 0.0), 1.0),
                suggested_topics=data.get("suggested_topics", []),
                rag_context_used=rag_context_used
            )

        except json.JSONDecodeError as e:
            print(f"❌ Ошибка парсинга JSON в Coordinator: {e}")
            print(f"Ответ модели: {text[:200] if 'text' in locals() else 'Нет ответа'}")

            # ДОБАВЛЕНО: Пытаемся восстановить JSON
            try:
                data = self._recover_json(text)
                agent_name = data.get("agent", "INTERVIEWER").upper()
                agent_name = self._normalize_agent_name(agent_name)

                return RouteResult(
                    agent=agent_name,
                    context=data.get("context", "Общий запрос"),
                    metadata=data.get("metadata", {}),
                    confidence=data.get("confidence", 0.3),
                    suggested_topics=data.get("suggested_topics", []),
                    rag_context_used=rag_context_used
                )
            except:
                # Если восстановить не удалось, используем fallback
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
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip() if text.count("```") >= 2 else text.strip("`").strip()

        # Удаляем пояснительный текст до JSON
        import re
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            text = json_match.group()

        return text.strip()

    def _fallback_agent_detection(self, user_text: str) -> str:
        """Fallback определение агента по ключевым словам - ИСПРАВЛЕННАЯ"""
        text_lower = user_text.lower()

        keyword_mapping = {
            "interviewer": ["интервью", "опрос", "вопрос", "задай", "проведи", "mock",
                            "собеседование", "interview", "собеседовани", "экзамен"],
            "assessor": ["оцен", "тест", "провер", "уровень", "насколько", "диагнос",
                         "сильные", "слабые", "знания", "скиллы", "компетенции"],
            "planner": ["план", "roadmap", "программа", "расписан", "рекомендац",
                        "изуч", "осво", "науч", "подготовк", "обучен",
                        "микросервис", "архитектур", "docker", "kubernetes",
                        "хочу изучать", "хочу научиться", "хочу освоить"],
            "reviewer": ["код", "решение", "задача", "оптимиз", "ревью", "разбор",
                         "алгоритм", "синтаксис", "паттерн", "рефакторинг"],
            "helper": ["совет", "как", "подготов", "что делать", "помощь",
                       "объясни", "расскажи", "что такое", "зачем"]
        }

        # Проверяем ВСЕ ключевые слова
        for agent, keywords in keyword_mapping.items():
            if any(keyword in text_lower for keyword in keywords):
                return agent.upper()

        # По умолчанию - если непонятно, то спрашиваем уточнение
        return "ASK_CLARIFICATION"

    def route_with_history(self, user_text: str, history: list = None,
                           user_context: dict = None) -> RouteResult:
        """Маршрутизация с учетом истории диалога (улучшенная)"""
        if not history:
            return self.route(user_text, user_context)

        # Формируем контекст из истории
        history_context = "\n".join([
            f"{'Пользователь' if msg.get('role') == 'user' else 'Бот'}: {msg.get('content', '')[:100]}..."
            for msg in history[-3:]  # Последние 3 сообщения
        ])

        # Ключевое улучшение: проверяем если в истории была команда /plan
        # то следующий ответ пользователя - это тема для плана!
        for msg in history[-2:]:  # Смотрим последние 2 сообщения
            if msg.get('role') == 'bot' and '/plan' in msg.get('content', ''):
                # Если бот только что отправил запрос на тему плана
                # значит следующий ответ пользователя - это тема для планера!
                return RouteResult(
                    agent="PLANNER",
                    context=f"Пользователь указал тему для плана обучения: {user_text}",
                    confidence=0.9
                )

        # Также проверяем если пользователь только что сказал что хочет что-то изучить
        user_last_msg = next((msg for msg in reversed(history)
                              if msg.get('role') == 'user'), None)

        if user_last_msg:
            last_text = user_last_msg.get('content', '').lower()
            if any(word in last_text for word in ['изуч', 'осво', 'науч', 'хочу изучать']):
                # Пользователь только что сказал что хочет что-то изучить
                return RouteResult(
                    agent="PLANNER",
                    context=f"Пользователь хочет изучать тему: {user_text}",
                    confidence=0.9
                )

        # Обновляем контекст пользователя
        if user_context is None:
            user_context = {}

        full_context = {
            **user_context,
            "history_preview": history_context
        }

        # Используем основной route с расширенным контекстом
        return self.route(
            user_text=f"{user_text} [контекст из истории: {history_context[:50]}...]",
            user_context=full_context
        )

    def _fix_json_problems(self, text: str) -> str:
        """Исправляет типичные проблемы в JSON от GigaChat"""
        # 1. Заменяем неправильные кавычки
        replacements = {
            '«': '"',
            '»': '"',
            '“': '"',  # умные открывающие
            '”': '"',  # умные закрывающие
            '‘': "'",
            '’': "'",
            '\u201c': '"',  # Unicode для умных кавычек
            '\u201d': '"',
            '\u2018': "'",
            '\u2019': "'",
        }

        for wrong, correct in replacements.items():
            text = text.replace(wrong, correct)

        # 2. Удаляем невидимые символы
        import re
        text = re.sub(r'[\x00-\x1F\x7F]', '', text)

        # 3. Исправляем запятые в конце объектов и массивов
        text = re.sub(r',\s*}', '}', text)
        text = re.sub(r',\s*]', ']', text)

        return text

    def _recover_json(self, text: str) -> dict:
        """Пытается восстановить сломанный JSON"""
        import re

        # Пытаемся найти JSON в тексте
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            json_str = json_match.group()
            try:
                return json.loads(json_str)
            except:
                pass

        # Если не нашли JSON, ищем отдельные поля
        result = {}

        # Ищем agent
        agent_match = re.search(r'"agent"\s*:\s*"([^"]+)"', text, re.IGNORECASE)
        if agent_match:
            result['agent'] = agent_match.group(1)

        # Ищем context
        context_match = re.search(r'"context"\s*:\s*"([^"]+)"', text, re.IGNORECASE)
        if context_match:
            result['context'] = context_match.group(1)

        # Ищем confidence
        confidence_match = re.search(r'"confidence"\s*:\s*([0-9.]+)', text, re.IGNORECASE)
        if confidence_match:
            try:
                result['confidence'] = float(confidence_match.group(1))
            except:
                result['confidence'] = 0.5

        # Добавляем metadata по умолчанию
        if 'metadata' not in result:
            result['metadata'] = {}

        return result

    def _normalize_agent_name(self, agent_name: str) -> str:
        """Нормализует имя агента"""
        agent_name = agent_name.upper()

        if "ASSESS" in agent_name:
            return "ASSESSOR"
        elif "INTERVIEW" in agent_name:
            return "INTERVIEWER"
        elif "PLAN" in agent_name:
            return "PLANNER"
        elif "REVIEW" in agent_name:
            return "REVIEWER"
        else:
            return agent_name  # возвращаем как есть