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
    from rag.retriever import retrieve_context

    RAG_AVAILABLE = True
except ImportError:
    print("⚠️  RAG модуль не найден. Assessor будет работать без базы знаний.")
    RAG_AVAILABLE = False


    def retrieve_context(query: str, k: int = 4) -> List[str]:
        return []

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
        self.llm = GigaChat(
            credentials=os.getenv("GIGACHAT_CLIENT_SECRET"),
            verify_ssl_certs=False,
            model="GigaChat"
        )
        self.use_rag = use_rag and RAG_AVAILABLE

        # Сохраняем оригинальные промпты
        self.prompt_without_rag = """
        Ты — эксперт по техническим собеседованиям и оценке знаний.

        Темы для оценки: {topics}

        Ответ пользователя: {answer}

        Всегда:
        - давай явный вердикт по готовности к собеседованиям;
        - объясняй, что означают выставленные баллы и какие темы проседают;
        - предлагай конкретные следующие шаги.

        Даже если запрос сформулирован общо, всё равно сделай разумное предположение и дай вердикт по готовности.

        Верни строго JSON:
        {{
          "scores": {{
            "theory": int,            # теоретическая база (0-100)
            "practice": int,          # практический опыт (0-100)
            "interview_readiness": int # готовность к собеседованию (0-100)
          }},
          "weak_topics": ["конкретные слабые темы"],
          "follow_up": "уточняющий вопрос для следующего шага",
          "feedback": "конструктивный разбор: что уже ок, что мешает собеседованиям и что делать дальше"
        }}
        """

        self.prompt_with_rag = """
        Ты — эксперт по техническим собеседованиям. Используй информацию из базы знаний, но не цитируй её дословно.

        КОНТЕКСТ ПОЛЬЗОВАТЕЛЯ:
        - Уровень: {level}
        - Направление: {track}
        - Текущий вопрос: {question}

        КОНТЕКСТ ИЗ БАЗЫ ЗНАНИЙ (примеры вопросов и тем):
        {rag_context}

        Темы для оценки: {topics}

        Ответ пользователя: {answer}

        Всегда:
        - давай явный вердикт по готовности к собеседованиям;
        - используй контекст только как подсказку, но отвечай применительно к пользователю;
        - объясняй, что означают выставленные баллы и какие темы проседают;
        - предлагай конкретные следующие шаги.

        Верни строго JSON:
        {{
          "scores": {{
            "theory": int,            # теоретическая база (0-100)
            "practice": int,          # практический опыт (0-100)
            "interview_readiness": int # готовность к собеседованию (0-100)
          }},
          "weak_topics": ["конкретные слабые темы"],
          "follow_up": "уточняющий вопрос для следующего шага",
          "feedback": "конструктивный разбор: что уже ок, что мешает собеседованиям и что делать дальше"
        }}
        """

    def _get_rag_context(self, topics: List[str], answer: str) -> Dict[str, str]:
        """Получает контекст из RAG базы знаний (оригинальная функция)"""
        if not self.use_rag:
            return {"context": "", "example_topics": ""}

        try:
            # Поиск по темам
            query = f"{' '.join(topics)} техническое собеседование оценка ответов"
            context_chunks = retrieve_context(query, k=3)

            # Поиск по ответу пользователя
            if answer and len(answer) > 10:
                answer_query = f"ответ на вопрос о {topics[0] if topics else 'программировании'}"
                answer_context = retrieve_context(answer_query, k=1)
                context_chunks.extend(answer_context)

            # Извлекаем темы из контекста для примера
            example_topics = []
            if context_chunks:
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

    def assess(self, answer: str, topics: list, user_context: dict = None) -> AssessResult:
        """Оценивает ответ пользователя с использованием RAG (улучшенная)"""

        # Устанавливаем контекст по умолчанию
        if user_context is None:
            user_context = {}

        level = user_context.get('level', 'junior')
        track = user_context.get('track', 'general')
        question = user_context.get('current_question', 'Общие знания')

        # Получаем контекст из RAG
        rag_context = self._get_rag_context(topics, answer)

        # Выбираем промпт в зависимости от наличия RAG
        if self.use_rag and rag_context["context"]:
            text = self.prompt_with_rag.format(
                level=level,
                track=track,
                question=question,
                rag_context=rag_context["context"],
                topics=topics,
                answer=answer
            )
            context_used = True
        else:
            text = self.prompt_without_rag.format(
                topics=topics,
                answer=answer
            )
            context_used = False

        # Отправляем в GigaChat
        try:
            response = self.llm.chat(text)

            content = response.choices[0].message.content

            # Чистим JSON от возможных меток кода
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
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
            print(f"Ответ модели: {content[:200] if 'content' in locals() else 'Нет ответа'}...")

            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL) if 'content' in locals() else None

            if json_match:
                try:
                    data = json.loads(json_match.group())
                    return AssessResult(
                        scores=data.get("scores", {}),
                        weak_topics=data.get("weak_topics", []),
                        follow_up=data.get("follow_up", ""),
                        feedback=data.get("feedback", ""),
                        context_used=context_used
                    )
                except Exception as inner_e:
                    print(f"⚠️ Повторная ошибка парсинга JSON: {inner_e}")

            # Fallback
            return AssessResult(
                scores={
                    "theory": 60,
                    "practice": 60,
                    "interview_readiness": 60
                },
                weak_topics=topics[:2] if topics else ["алгоритмы", "системный дизайн"],
                follow_up="Расскажите, какие задачи вы уже решали на собеседованиях или в проектах?",
                feedback=(
                    "Ответ выглядит в целом неплохо, чтобы начинать пробовать собеседования, "
                    "но для более точной оценки лучше пройти полноценный тест через команду /assess."
                ),
                context_used=context_used
            )

        except Exception as e:
            print(f"❌ Ошибка в assess: {e}")
            return AssessResult(
                scores={
                    "theory": 50,
                    "practice": 50,
                    "interview_readiness": 50
                },
                weak_topics=["технические вопросы", "алгоритмы"],
                follow_up="Хочется ли вам сейчас получить подробный план подготовки или пройти мини‑тест?",
                feedback=(
                    "Произошла техническая ошибка при анализе ответа. "
                    "Попробуйте ещё раз или воспользуйтесь командой /assess."
                ),
                context_used=False
            )

    def assess_with_feedback(self, question: str, user_answer: str,
                             correct_answer: str = None, user_context: dict = None) -> Dict:
        """Расширенная оценка с учетом правильного ответа (улучшенная)"""

        if user_context is None:
            user_context = {}

        level = user_context.get('level', 'junior')
        track = user_context.get('track', 'general')

        # Ищем контекст по вопросу
        context = ""
        if self.use_rag:
            try:
                context_chunks = retrieve_context(question, k=2)
                if context_chunks:
                    context = "\n".join(context_chunks)
            except Exception as e:
                print(f"⚠️  Ошибка RAG в assess_with_feedback: {e}")

        prompt = f"""
Оцени ответ на технический вопрос.

КОНТЕКСТ:
- Уровень: {level}
- Направление: {track}

Вопрос: {question}
Ответ пользователя: {user_answer}
{f'Правильный ответ (справочно): {correct_answer}' if correct_answer else ''}
{f'Дополнительный контекст: {context}' if context else ''}

Проанализируй ответ по критериям:
1. Техническая точность (0-40)
2. Полнота ответа (0-30)  
3. Структура и ясность (0-20)
4. Примеры и детали (0-10)

Верни строго JSON:
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

        try:
            response = self.llm.chat(prompt)
            content = response.choices[0].message.content

            # Очистка JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.strip("`").strip()

            return json.loads(content)
        except Exception as e:
            print(f"❌ Ошибка в assess_with_feedback: {e}")
            return {
                "total_score": 50,
                "criteria_scores": {"accuracy": 20, "completeness": 15, "clarity": 10, "examples": 5},
                "strengths": ["Базовое понимание темы"],
                "improvements": ["Нужно больше деталей и примеров"],
                "recommended_resources": ["Документация, LeetCode, YouTube уроки"]
            }