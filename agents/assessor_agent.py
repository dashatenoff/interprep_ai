# agents/assessor.py
import json
import sys
from pathlib import Path
from pydantic import BaseModel
from gigachat import GigaChat
import os
from dotenv import load_dotenv
from typing import List, Dict, Optional

# Добавляем путь для импорта RAG
sys.path.append(str(Path(__file__).resolve().parent.parent))

# Импортируем RAG (с обработкой ошибок)
try:
    from rag.retriever import retrieve_context, build_prompt

    RAG_AVAILABLE = True
except ImportError:
    print("⚠️  RAG модуль не найден. Assessor будет работать без базы знаний.")
    RAG_AVAILABLE = False


    # Заглушки для совместимости
    def retrieve_context(query: str, k: int = 4) -> List[str]:
        return []


    def build_prompt(question: str, context_chunks: List[str]) -> str:
        return question

# Загружаем токен из .env
load_dotenv()


# ===============================
#  Модель данных для результата
# ===============================
class AssessResult(BaseModel):
    scores: dict
    weak_topics: list
    follow_up: str
    feedback: Optional[str] = None
    context_used: Optional[bool] = False


# ===============================
#  Основной класс агента с RAG
# ===============================
class AssessorAgent:
    def __init__(self, use_rag: bool = True):
        # ✅ Правильная инициализация клиента
        self.llm = GigaChat(
            credentials=os.getenv("GIGACHAT_CLIENT_SECRET"),
            verify_ssl_certs=False
        )

        self.use_rag = use_rag and RAG_AVAILABLE

        # Два варианта промпта: с RAG и без
        self.prompt_without_rag = """
        Ты — Assessor AI. Твоя задача — оценить знания пользователя по темам {topics}.

        Ответ пользователя: {answer}

        Ответь строго в JSON формате:
        {{
          "scores": {{"Python": int, "Algorithms": int, "System Design": int}},
          "weak_topics": [список слабых тем],
          "follow_up": "следующий вопрос для уточнения",
          "feedback": "детальная обратная связь по ответу"
        }}
        """

        self.prompt_with_rag = """
        Ты — эксперт по техническим собеседованиям. Используй информацию из базы знаний для точной оценки.

        КОНТЕКСТ ИЗ БАЗЫ ЗНАНИЙ (примеры вопросов и правильных ответов):
        {context}

        Твоя задача — оценить знания пользователя по темам: {topics}

        Ответ пользователя: {answer}

        Проанализируй ответ с учетом контекста выше и верни строго в JSON:
        {{
          "scores": {{"Теория": int, "Практика": int, "Архитектура": int}},
          "weak_topics": [список конкретных слабых тем],
          "follow_up": "уточняющий вопрос для проверки понимания",
          "feedback": "конструктивный фидбек с примерами из контекста"
        }}

        Примеры тем из контекста: {example_topics}
        """

    def _get_rag_context(self, topics: List[str], answer: str) -> Dict[str, str]:
        """Получает контекст из RAG базы знаний"""
        if not self.use_rag:
            return {"context": "", "example_topics": ""}

        try:
            # Поиск по темам
            query = f"{' '.join(topics)} техническое собеседование оценка ответов"
            context_chunks = retrieve_context(query, k=3)

            # Поиск по ответу пользователя (для понимания контекста)
            if answer and len(answer) > 10:
                answer_query = f"ответ на вопрос о {topics[0] if topics else 'программировании'}"
                answer_context = retrieve_context(answer_query, k=1)
                context_chunks.extend(answer_context)

            # Извлекаем темы из контекста для примера
            example_topics = []
            if context_chunks:
                # Простой парсинг для демонстрации
                for chunk in context_chunks[:2]:
                    if "Python" in chunk:
                        example_topics.append("Python")
                    if "алгоритм" in chunk.lower():
                        example_topics.append("Алгоритмы")
                    if "база данных" in chunk.lower():
                        example_topics.append("Базы данных")

            return {
                "context": "\n".join([f"- {chunk[:300]}..." for chunk in context_chunks]),
                "example_topics": ", ".join(set(example_topics)) if example_topics else "нет примеров"
            }

        except Exception as e:
            print(f"⚠️  Ошибка RAG в Assessor: {e}")
            return {"context": "", "example_topics": ""}

    def assess(self, answer: str, topics: list) -> AssessResult:
        """Оценивает ответ пользователя с использованием RAG"""

        # Получаем контекст из RAG
        rag_context = self._get_rag_context(topics, answer)

        # Выбираем промпт в зависимости от наличия RAG
        if self.use_rag and rag_context["context"]:
            text = self.prompt_with_rag.format(
                context=rag_context["context"],
                topics=topics,
                answer=answer,
                example_topics=rag_context["example_topics"]
            )
            context_used = True
        else:
            text = self.prompt_without_rag.format(
                topics=topics,
                answer=answer
            )
            context_used = False

        # ✅ Отправляем в GigaChat
        try:
            response = self.llm.chat(
                model="GigaChat:latest",
                messages=[{"role": "user", "content": text}],
            )

            content = response.choices[0].message.content

            # Чистим JSON от возможных меток кода
            if "```json" in content:
                content = content.replace("```json", "").replace("```", "").strip()
            elif "```" in content:
                content = content.strip("`").strip()

            data = json.loads(content)

            return AssessResult(
                scores=data.get("scores", {}),
                weak_topics=data.get("weak_topics", []),
                follow_up=data.get("follow_up", ""),
                feedback=data.get("feedback", ""),
                context_used=context_used
            )

        except json.JSONDecodeError as e:
            print(f"❌ Ошибка парсинга JSON: {e}")
            print(f"Ответ модели: {content[:200]}...")

            # Пытаемся извлечь JSON из текста
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                try:
                    data = json.loads(json_match.group())
                    return AssessResult(**data, context_used=context_used)
                except:
                    pass

            return AssessResult(
                scores={topic: 50 for topic in topics},
                weak_topics=topics[:2],
                follow_up="Можешь подробнее рассказать о своем опыте?",
                feedback="Не удалось проанализировать ответ. Попробуйте ответить более развернуто.",
                context_used=context_used
            )

        except Exception as e:
            print(f"❌ Ошибка в assess: {e}")
            return AssessResult(
                scores={topic: 50 for topic in topics},
                weak_topics=["технические вопросы"],
                follow_up="Что именно вы хотите оценить?",
                feedback="Произошла ошибка при оценке. Попробуйте снова.",
                context_used=context_used
            )

    def assess_with_feedback(self, question: str, user_answer: str,
                             correct_answer: str = None) -> Dict:
        """Расширенная оценка с учетом правильного ответа"""
        # Ищем контекст по вопросу
        if self.use_rag:
            context_chunks = retrieve_context(question, k=2)
            context = "\n".join(context_chunks) if context_chunks else ""
        else:
            context = ""

        prompt = f"""
        Оцени ответ на технический вопрос.

        Вопрос: {question}
        Ответ пользователя: {user_answer}
        {f'Правильный ответ (справочно): {correct_answer}' if correct_answer else ''}
        {f'Дополнительный контекст: {context}' if context else ''}

        Проанализируй ответ по критериям:
        1. Техническая точность (0-40)
        2. Полнота ответа (0-30)  
        3. Структура и ясность (0-20)
        4. Примеры и детали (0-10)

        Верни JSON:
        {{
            "total_score": 0-100,
            "criteria_scores": {{
                "accuracy": 0-40,
                "completeness": 0-30,
                "clarity": 0-20,
                "examples": 0-10
            }},
            "strengths": ["сильные стороны"],
            "improvements": ["что улучшить"],
            "recommended_resources": ["ресурсы для изучения"]
        }}
        """

        response = self.llm.chat(prompt)
        return json.loads(response.choices[0].message.content)