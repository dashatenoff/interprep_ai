# agents/interviewer_agent.py
import json
import sys
from pathlib import Path
from pydantic import BaseModel
from gigachat import GigaChat
from dotenv import load_dotenv
import os
from typing import List, Optional, Dict, Any
from datetime import datetime

# Загружаем токены
load_dotenv()

# Импортируем RAG (с обработкой ошибок)
try:
    from rag.retriever import retrieve_context

    RAG_AVAILABLE = True
except ImportError:
    print("⚠️  RAG модуль не найден. Interviewer будет работать без базы знаний.")
    RAG_AVAILABLE = False


    def retrieve_context(query: str, k: int = 4) -> List[str]:
        return []


# ===============================
#  Модели данных
# ===============================
class InterviewQuestion(BaseModel):
    topic: str
    question: str
    expected_concepts: list
    difficulty: str
    hints: Optional[List[str]] = None
    similar_questions: Optional[List[str]] = None
    rag_context_used: bool = False


class InterviewScore(BaseModel):
    score: int
    comment: str
    strong_points: Optional[List[str]] = None
    weak_points: Optional[List[str]] = None
    recommended_resources: Optional[List[str]] = None


class InterviewSession(BaseModel):
    id: str
    topic: str
    level: str
    questions: List[InterviewQuestion]
    current_question_index: int = 0
    scores: List[InterviewScore] = []
    started_at: str
    user_context: Optional[Dict] = None  # ← ДОБАВИЛ: контекст пользователя


# ===============================
#  Основной класс Interviewer с RAG
# ===============================
class InterviewerAgent:
    def __init__(self, use_rag: bool = True):
        self.llm = GigaChat(
            credentials=os.getenv("GIGACHAT_CLIENT_SECRET"),
            verify_ssl_certs=False,
            model="GigaChat"  # ← ДОБАВИЛ: явное указание модели
        )

        self.use_rag = use_rag and RAG_AVAILABLE
        self.active_sessions: Dict[str, InterviewSession] = {}

    def _get_rag_context_for_questions(self, topic: str, level: str, track: str = None) -> str:
        """Получает контекст из RAG для генерации вопросов"""
        if not self.use_rag:
            return ""

        try:
            # Формируем запрос с учетом направления
            query_parts = [topic, level]
            if track:
                query_parts.append(track)
            query = " ".join(query_parts) + " собеседование вопросы"

            context_chunks = retrieve_context(query, k=3)

            if context_chunks:
                return "\n".join([
                    f"Пример {i + 1}: {chunk[:300]}..."
                    for i, chunk in enumerate(context_chunks)
                ])
            return ""

        except Exception as e:
            print(f"⚠️  Ошибка RAG в Interviewer: {e}")
            return ""

    def _extract_json(self, text: str) -> dict:
        """Безопасно достаёт JSON из ответа"""
        # Очистка от Markdown блоков
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.strip("`").strip()

        # Поиск JSON в тексте
        import re
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except:
                pass

        # Если не нашли JSON, пробуем распарсить весь текст
        try:
            return json.loads(text)
        except:
            raise ValueError(f"Не удалось извлечь JSON из ответа: {text[:200]}")

    def start_interview(self, topic: str, level: str = "middle",
                        user_context: Dict = None, session_id: str = None) -> InterviewSession:
        """Начинает новое интервью по теме"""

        if user_context is None:
            user_context = {}

        track = user_context.get('track', 'general')
        user_level = user_context.get('level', level)

        if not session_id:
            session_id = f"interview_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{topic[:20]}"

        # Получаем контекст из RAG
        rag_context = self._get_rag_context_for_questions(topic, user_level, track)

        # Промпт для генерации вопросов
        if rag_context:
            prompt = f"""
Ты — опытный технический интервьюер. У тебя есть доступ к базе вопросов.

КОНТЕКСТ ИЗ БАЗЫ ЗНАНИЙ:
{rag_context}

КОНТЕКСТ ПОЛЬЗОВАТЕЛЯ:
- Уровень: {user_level}
- Направление: {track}

Сгенерируй 3 уникальных вопроса по теме: {topic}
Вопросы должны соответствовать уровню {user_level}.

Формат строго JSON:
{{
  "questions": [
    {{
      "topic": "конкретная подтема",
      "question": "текст вопроса",
      "expected_concepts": ["концепция1", "концепция2", "концепция3"],
      "difficulty": "easy/medium/hard",
      "hints": ["подсказка 1", "подсказка 2"]
    }}
  ]
}}

Создай 1 легкий, 1 средний и 1 сложный вопрос.
"""
            rag_used = True
        else:
            prompt = f"""
Ты — опытный технический интервьюер.

КОНТЕКСТ ПОЛЬЗОВАТЕЛЯ:
- Уровень: {user_level}
- Направление: {track}

Сгенерируй 3 вопроса по теме: {topic}
Вопросы должны соответствовать уровню {user_level}.

Формат строго JSON:
{{
  "questions": [
    {{
      "topic": "конкретная подтема",
      "question": "текст вопроса",
      "expected_concepts": ["концепция1", "концепция2"],
      "difficulty": "easy/medium/hard",
      "hints": ["подсказка при затруднении"]
    }}
  ]
}}
"""
            rag_used = False

        # Генерируем вопросы
        try:
            response = self.llm.chat(prompt)
            data = self._extract_json(response.choices[0].message.content)

            questions = []
            for q_data in data.get("questions", [])[:3]:  # Берем максимум 3 вопроса
                questions.append(InterviewQuestion(
                    topic=q_data.get("topic", topic),
                    question=q_data.get("question", f"Расскажите о {topic}"),
                    expected_concepts=q_data.get("expected_concepts", [topic]),
                    difficulty=q_data.get("difficulty", "medium"),
                    hints=q_data.get("hints", []),
                    rag_context_used=rag_used
                ))

        except Exception as e:
            print(f"❌ Ошибка генерации вопросов: {e}")
            # Fallback вопросы
            questions = [
                InterviewQuestion(
                    topic=topic,
                    question=f"Что вы знаете о {topic}?",
                    expected_concepts=[topic, "базовые принципы"],
                    difficulty="easy",
                    rag_context_used=False
                ),
                InterviewQuestion(
                    topic=topic,
                    question=f"Приведите пример использования {topic}",
                    expected_concepts=["практическое применение"],
                    difficulty="medium",
                    rag_context_used=False
                ),
                InterviewQuestion(
                    topic=topic,
                    question=f"Какие проблемы могут возникнуть при работе с {topic} и как их решить?",
                    expected_concepts=["проблемы", "решения"],
                    difficulty="hard",
                    rag_context_used=False
                )
            ]

        # Создаем сессию
        session = InterviewSession(
            id=session_id,
            topic=topic,
            level=user_level,
            questions=questions,
            started_at=datetime.now().isoformat(),
            user_context=user_context  # ← СОХРАНЯЕМ контекст
        )

        self.active_sessions[session_id] = session
        return session

    def get_current_question(self, session_id: str) -> Optional[InterviewQuestion]:
        """Получает текущий вопрос из сессии"""
        session = self.active_sessions.get(session_id)
        if not session:
            return None

        if session.current_question_index < len(session.questions):
            return session.questions[session.current_question_index]
        return None

    def evaluate_answer(self, session_id: str, answer: str) -> InterviewScore:
        """Оценивает ответ на текущий вопрос"""
        session = self.active_sessions.get(session_id)
        if not session:
            return InterviewScore(
                score=0,
                comment="Сессия не найдена",
                strong_points=[],
                weak_points=["Перезапустите интервью"]
            )

        if session.current_question_index >= len(session.questions):
            return InterviewScore(
                score=0,
                comment="Все вопросы пройдены",
                strong_points=[],
                weak_points=[]
            )

        current_question = session.questions[session.current_question_index]
        user_level = session.user_context.get('level', 'middle') if session.user_context else 'middle'

        # Получаем RAG контекст для оценки
        rag_context = ""
        if self.use_rag and current_question.expected_concepts:
            try:
                query = f"{current_question.topic} {user_level} правильный ответ"
                context_chunks = retrieve_context(query, k=2)
                if context_chunks:
                    rag_context = "\n".join([f"- {chunk[:200]}" for chunk in context_chunks])
            except Exception as e:
                print(f"⚠️  Ошибка RAG при оценке: {e}")

        # Промпт для оценки
        if rag_context:
            prompt = f"""
Ты — технический интервьюер.

КОНТЕКСТ ПОЛЬЗОВАТЕЛЯ:
- Уровень: {user_level}

ИНФОРМАЦИЯ ДЛЯ ОЦЕНКИ:
{rag_context}

ВОПРОС: {current_question.question}
ОЖИДАЕМЫЕ КОНЦЕПЦИИ: {', '.join(current_question.expected_concepts)}

ОТВЕТ КАНДИДАТА: {answer}

Оцени ответ кандидата уровня {user_level} по шкале 0-100.
Учти, что для уровня {user_level} требования соответствующие.

Формат строго JSON:
{{
  "score": число от 0 до 100,
  "comment": "детальный фидбек, что правильно, что можно улучшить",
  "strong_points": ["сильные стороны ответа"],
  "weak_points": ["что нужно улучшить"],
  "recommended_resources": ["рекомендации по изучению"]
}}
"""
        else:
            prompt = f"""
Ты — технический интервьюер.

КОНТЕКСТ:
- Уровень кандидата: {user_level}

ВОПРОС: {current_question.question}
ОЖИДАЕМЫЕ КОНЦЕПЦИИ: {', '.join(current_question.expected_concepts)}

ОТВЕТ КАНДИДАТА: {answer}

Оцени ответ кандидата уровня {user_level} по шкале 0-100.

Формат строго JSON:
{{
  "score": число от 0 до 100,
  "comment": "конструктивный фидбек",
  "strong_points": ["что хорошо в ответе"],
  "weak_points": ["что нужно доработать"]
}}
"""

        try:
            response = self.llm.chat(prompt)
            data = self._extract_json(response.choices[0].message.content)

            score = InterviewScore(
                score=data.get("score", 50),
                comment=data.get("comment", "Ответ принят"),
                strong_points=data.get("strong_points", []),
                weak_points=data.get("weak_points", []),
                recommended_resources=data.get("recommended_resources", [])
            )

            # Сохраняем и переходим дальше
            session.scores.append(score)
            session.current_question_index += 1

            return score

        except Exception as e:
            print(f"❌ Ошибка оценки ответа: {e}")
            return InterviewScore(
                score=50,
                comment="Техническая ошибка при оценке",
                strong_points=["Ответ предоставлен"],
                weak_points=["Требуется более детальный разбор"],
                recommended_resources=[]
            )

    def get_interview_summary(self, session_id: str) -> Dict:
        """Получает итоговую статистику по интервью"""
        session = self.active_sessions.get(session_id)
        if not session:
            return {"error": "Сессия не найдена"}

        if not session.scores:
            return {
                "status": "active",
                "current_question": session.current_question_index + 1,
                "total_questions": len(session.questions)
            }

        # Рассчитываем статистику
        total_score = sum(s.score for s in session.scores)
        average_score = total_score / len(session.scores)

        # Определяем результат
        if average_score >= 80:
            level = "Отлично"
        elif average_score >= 60:
            level = "Хорошо"
        elif average_score >= 40:
            level = "Удовлетворительно"
        else:
            level = "Требует улучшений"

        # Собираем все сильные/слабые стороны
        all_strong = []
        all_weak = []
        for score in session.scores:
            all_strong.extend(score.strong_points or [])
            all_weak.extend(score.weak_points or [])

        # Удаляем дубликаты
        all_strong = list(set(all_strong))
        all_weak = list(set(all_weak))

        return {
            "session_id": session_id,
            "topic": session.topic,
            "user_level": session.level,
            "total_questions": len(session.questions),
            "completed": len(session.scores),
            "average_score": round(average_score, 1),
            "performance": level,
            "strong_points": all_strong[:5],
            "weak_points": all_weak[:5],
            "started_at": session.started_at
        }

    def get_hints(self, session_id: str) -> List[str]:
        """Получает подсказки для текущего вопроса"""
        session = self.active_sessions.get(session_id)
        if not session:
            return ["Сессия не найдена"]

        current_question = self.get_current_question(session_id)
        if not current_question:
            return ["Интервью завершено"]

        # Если есть готовые подсказки, возвращаем их
        if current_question.hints:
            return current_question.hints

        # Генерируем на лету
        prompt = f"""
Вопрос для интервью: {current_question.question}
Тема: {current_question.topic}
Уровень кандидата: {session.level}

Дай 2 подсказки, которые помогут кандидату уровня {session.level} ответить на вопрос.
Подсказки должны быть конкретными и полезными.

Формат: ["подсказка 1", "подсказка 2"]
"""

        try:
            response = self.llm.chat(prompt)
            content = response.choices[0].message.content

            # Извлекаем список
            import re
            list_match = re.search(r'\[.*\]', content, re.DOTALL)
            if list_match:
                hints = json.loads(list_match.group())
                current_question.hints = hints[:2]
                return hints[:2]
        except:
            pass

        return ["Подумайте о ключевых концепциях", "Приведите практический пример"]

    def end_interview(self, session_id: str) -> Dict:
        """Завершает интервью"""
        summary = self.get_interview_summary(session_id)

        if "error" not in summary:
            # Генерируем рекомендации
            weak_points = summary.get("weak_points", [])
            if weak_points:
                prompt = f"""
На основе слабых сторон: {', '.join(weak_points[:3])}
Дай 3 конкретные рекомендации для улучшения.

Формат: ["рекомендация 1", "рекомендация 2", "рекомендация 3"]
"""
                try:
                    response = self.llm.chat(prompt)
                    content = response.choices[0].message.content

                    import re
                    list_match = re.search(r'\[.*\]', content, re.DOTALL)
                    if list_match:
                        summary["recommendations"] = json.loads(list_match.group())
                except:
                    summary["recommendations"] = [
                        "Практиковаться на LeetCode/HackerRank",
                        "Изучать документацию и best practices",
                        "Проходить больше mock интервью"
                    ]

            # Удаляем сессию
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]

        return summary