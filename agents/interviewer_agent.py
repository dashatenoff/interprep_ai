# agents/interviewer_agent.py
import json
import sys
from pathlib import Path
from pydantic import BaseModel
from gigachat import GigaChat
from dotenv import load_dotenv
import os
from typing import List, Optional, Dict
from datetime import datetime

# Добавляем путь для импорта RAG
sys.path.append(str(Path(__file__).resolve().parent.parent))

# Импортируем RAG (с обработкой ошибок)
try:
    from rag.retriever import retrieve_context, build_prompt, search_similar

    RAG_AVAILABLE = True
except ImportError:
    print("⚠️  RAG модуль не найден. Interviewer будет работать без базы знаний.")
    RAG_AVAILABLE = False


    def retrieve_context(query: str, k: int = 4) -> List[str]:
        return []


    def build_prompt(question: str, context_chunks: List[str]) -> str:
        return question


    def search_similar(query: str, k: int = 5) -> List[Dict]:
        return []

load_dotenv()


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


# ===============================
#  Основной класс Interviewer с RAG
# ===============================
class InterviewerAgent:
    def __init__(self, use_rag: bool = True):
        self.llm = GigaChat(
            credentials=os.getenv("GIGACHAT_CLIENT_SECRET"),
            verify_ssl_certs=False
        )

        self.use_rag = use_rag and RAG_AVAILABLE
        self.active_sessions: Dict[str, InterviewSession] = {}

        # Промпты
        self.question_generation_prompt_without_rag = """
        Ты — опытный технический интервьюер.
        Сгенерируй ровно 3 вопроса по теме {topic} для уровня {level}.

        Формат ответа строго JSON:
        {{
          "questions": [
            {{
              "topic": "{topic}",
              "question": "текст вопроса",
              "expected_concepts": ["концепция1", "концепция2"],
              "difficulty": "easy/medium/hard",
              "hints": ["подсказка1", "подсказка2"]
            }}
          ]
        }}
        """

        self.question_generation_prompt_with_rag = """
        Ты — опытный технический интервьюер с доступом к базе реальных вопросов.

        КОНТЕКСТ ИЗ БАЗЫ ЗНАНИЙ (реальные вопросы с собеседований):
        {rag_context}

        Сгенерируй 3 новых, уникальных вопроса по теме {topic} для уровня {level}.
        Используй контекст как источник вдохновения, но не копируй вопросы напрямую.

        Формат ответа строго JSON:
        {{
          "questions": [
            {{
              "topic": "{topic}",
              "question": "текст вопроса",
              "expected_concepts": ["концепция1", "концепция2", "концепция3"],
              "difficulty": "easy/medium/hard",
              "hints": ["подсказка при затруднении", "дополнительная подсказка"],
              "similar_questions": ["похожий вопрос 1", "похожий вопрос 2"]
            }}
          ]
        }}

        Сложность распредели так: 1 easy, 1 medium, 1 hard.
        """

        self.evaluation_prompt_without_rag = """
        Ты — технический интервьюер.
        Оцени ответ кандидата на вопрос: "{question}"

        Ответ кандидата: "{answer}"

        Формат ответа строго JSON:
        {{
          "score": число от 0 до 100,
          "comment": "конструктивный комментарий",
          "strong_points": ["сильная сторона 1", "сильная сторона 2"],
          "weak_points": ["слабая сторона 1", "слабая сторона 2"]
        }}
        """

        self.evaluation_prompt_with_rag = """
        Ты — технический интервьюер с доступом к базе знаний.

        КОНТЕКСТ (правильные ответы и ожидаемые концепции):
        {rag_context}

        Вопрос: {question}
        Ожидаемые концепции: {expected_concepts}

        Ответ кандидата: {answer}

        Оцени ответ кандидата с учетом контекста выше.

        Формат ответа строго JSON:
        {{
          "score": число от 0 до 100,
          "comment": "детальный фидбек с примерами",
          "strong_points": ["что кандидат понял правильно"],
          "weak_points": ["что упущено или неверно"],
          "recommended_resources": ["ресурсы для изучения слабых тем"]
        }}
        """

    def _get_rag_context_for_questions(self, topic: str, level: str) -> Dict[str, str]:
        """Получает контекст из RAG для генерации вопросов"""
        if not self.use_rag:
            return {"rag_context": "", "similar_questions": ""}

        try:
            # Поиск реальных вопросов по теме и уровню
            query = f"{topic} {level} собеседование вопросы"
            context_chunks = retrieve_context(query, k=4)

            # Поиск похожих вопросов для референса
            similar_results = search_similar(query, k=3)
            similar_questions = []
            for result in similar_results:
                # Извлекаем вопросы из текста
                text = result.get('text', '')
                if "Вопрос:" in text:
                    question_part = text.split("Вопрос:")[1].split("Ответ:")[0].strip()
                    similar_questions.append(question_part[:100] + "...")

            return {
                "rag_context": "\n".join([
                    f"📋 Пример {i + 1}: {chunk[:300]}..."
                    for i, chunk in enumerate(context_chunks)
                ]),
                "similar_questions": "\n".join(similar_questions) if similar_questions else "Нет похожих вопросов"
            }

        except Exception as e:
            print(f"⚠️  Ошибка RAG в Interviewer (генерация вопросов): {e}")
            return {"rag_context": "", "similar_questions": ""}

    def _get_rag_context_for_evaluation(self, question: str, expected_concepts: List[str]) -> Dict[str, str]:
        """Получает контекст из RAG для оценки ответов"""
        if not self.use_rag:
            return {"rag_context": ""}

        try:
            # Ищем информацию по ожидаемым концепциям
            context_chunks = []
            for concept in expected_concepts[:3]:  # Берем первые 3 концепции
                concept_context = retrieve_context(f"{concept} объяснение пример", k=1)
                context_chunks.extend(concept_context)

            # Ищем похожие вопросы и ответы
            question_context = retrieve_context(question[:100], k=2)
            context_chunks.extend(question_context)

            return {
                "rag_context": "\n".join([
                    f"📘 По концепции '{concept}': {chunk[:200]}..."
                    for chunk in context_chunks
                ]) if context_chunks else "Нет дополнительного контекста"
            }

        except Exception as e:
            print(f"⚠️  Ошибка RAG в Interviewer (оценка): {e}")
            return {"rag_context": ""}

    def _extract_json(self, text: str) -> dict:
        """Безопасно достаёт JSON из ответа GigaChat"""
        # Очистка от Markdown блоков
        if text.startswith("```json"):
            text = text[7:].strip()
        elif text.startswith("```"):
            text = text[3:].strip()

        if text.endswith("```"):
            text = text[:-3].strip()

        # Поиск JSON в тексте
        import re
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            cleaned = json_match.group()
            return json.loads(cleaned)

        # Если не нашли JSON, пробуем распарсить весь текст
        try:
            return json.loads(text)
        except:
            raise ValueError("Не удалось извлечь JSON из ответа")

    def start_interview(self, topic: str, level: str = "middle", session_id: str = None) -> InterviewSession:
        """Начинает новое интервью по теме"""
        if not session_id:
            session_id = f"interview_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{topic}"

        # Получаем контекст из RAG
        rag_context = self._get_rag_context_for_questions(topic, level)

        # Выбираем промпт
        if self.use_rag and rag_context["rag_context"]:
            prompt = self.question_generation_prompt_with_rag.format(
                topic=topic,
                level=level,
                rag_context=rag_context["rag_context"]
            )
            rag_used = True
        else:
            prompt = self.question_generation_prompt_without_rag.format(
                topic=topic,
                level=level
            )
            rag_used = False

        # Генерируем вопросы
        try:
            response = self.llm.chat(prompt)
            data = self._extract_json(response.choices[0].message.content)

            questions = []
            for q_data in data["questions"][:3]:  # Берем максимум 3 вопроса
                questions.append(InterviewQuestion(
                    topic=q_data.get("topic", topic),
                    question=q_data.get("question", f"Расскажите о {topic}"),
                    expected_concepts=q_data.get("expected_concepts", [topic]),
                    difficulty=q_data.get("difficulty", "medium"),
                    hints=q_data.get("hints", []),
                    similar_questions=q_data.get("similar_questions", []),
                    rag_context_used=rag_used
                ))

            # Создаем сессию
            session = InterviewSession(
                id=session_id,
                topic=topic,
                level=level,
                questions=questions,
                started_at=datetime.now().isoformat()
            )

            self.active_sessions[session_id] = session
            return session

        except Exception as e:
            print(f"❌ Ошибка генерации вопросов: {e}")
            # Fallback вопросы
            fallback_questions = [
                InterviewQuestion(
                    topic=topic,
                    question=f"Расскажите, что вы знаете о {topic}?",
                    expected_concepts=[topic, "базовые принципы"],
                    difficulty="easy",
                    rag_context_used=False
                ),
                InterviewQuestion(
                    topic=topic,
                    question=f"Приведите пример использования {topic} в реальном проекте",
                    expected_concepts=["практическое применение", "примеры"],
                    difficulty="medium",
                    rag_context_used=False
                )
            ]

            session = InterviewSession(
                id=session_id,
                topic=topic,
                level=level,
                questions=fallback_questions,
                started_at=datetime.now().isoformat()
            )

            self.active_sessions[session_id] = session
            return session

    def get_current_question(self, session_id: str) -> Optional[InterviewQuestion]:
        """Получает текущий вопрос из сессии"""
        if session_id not in self.active_sessions:
            return None

        session = self.active_sessions[session_id]
        if session.current_question_index < len(session.questions):
            return session.questions[session.current_question_index]
        return None

    def evaluate_answer(self, session_id: str, answer: str) -> InterviewScore:
        """Оценивает ответ на текущий вопрос"""
        if session_id not in self.active_sessions:
            return InterviewScore(
                score=0,
                comment="Сессия не найдена",
                strong_points=[],
                weak_points=["Сессия устарела или не существует"]
            )

        session = self.active_sessions[session_id]
        if session.current_question_index >= len(session.questions):
            return InterviewScore(
                score=0,
                comment="Все вопросы пройдены",
                strong_points=[],
                weak_points=[]
            )

        current_question = session.questions[session.current_question_index]

        # Получаем контекст из RAG для оценки
        rag_context = self._get_rag_context_for_evaluation(
            current_question.question,
            current_question.expected_concepts
        )

        # Выбираем промпт
        if self.use_rag and rag_context["rag_context"]:
            prompt = self.evaluation_prompt_with_rag.format(
                question=current_question.question,
                expected_concepts=", ".join(current_question.expected_concepts),
                answer=answer,
                rag_context=rag_context["rag_context"]
            )
        else:
            prompt = self.evaluation_prompt_without_rag.format(
                question=current_question.question,
                answer=answer
            )

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

            # Сохраняем оценку и переходим к следующему вопросу
            session.scores.append(score)
            session.current_question_index += 1

            return score

        except Exception as e:
            print(f"❌ Ошибка оценки ответа: {e}")
            return InterviewScore(
                score=50,
                comment="Произошла ошибка при оценке ответа",
                strong_points=[],
                weak_points=["Техническая ошибка"],
                recommended_resources=[]
            )

    def get_interview_summary(self, session_id: str) -> Dict:
        """Получает итоговую статистику по интервью"""
        if session_id not in self.active_sessions:
            return {"error": "Сессия не найдена"}

        session = self.active_sessions[session_id]

        if not session.scores:
            return {
                "status": "active",
                "completed_questions": session.current_question_index,
                "total_questions": len(session.questions)
            }

        # Рассчитываем статистику
        total_score = sum(s.score for s in session.scores)
        average_score = total_score / len(session.scores) if session.scores else 0

        # Определяем уровень по среднему баллу
        if average_score >= 80:
            level = "Отлично"
        elif average_score >= 60:
            level = "Хорошо"
        elif average_score >= 40:
            level = "Удовлетворительно"
        else:
            level = "Требует улучшений"

        # Собираем все слабые и сильные стороны
        all_strong = []
        all_weak = []
        for score in session.scores:
            all_strong.extend(score.strong_points or [])
            all_weak.extend(score.weak_points or [])

        # Удаляем дубликаты
        all_strong = list(set(all_strong))
        all_weak = list(set(all_weak))

        # Определяем, использовался ли RAG
        rag_used = any(q.rag_context_used for q in session.questions)

        return {
            "session_id": session_id,
            "topic": session.topic,
            "level": session.level,
            "total_questions": len(session.questions),
            "completed_questions": len(session.scores),
            "average_score": round(average_score, 1),
            "performance_level": level,
            "strong_points": all_strong[:5],  # Топ-5 сильных сторон
            "weak_points": all_weak[:5],  # Топ-5 слабых сторон
            "rag_used": rag_used,
            "started_at": session.started_at,
            "duration_minutes": round(
                (datetime.now() - datetime.fromisoformat(session.started_at)).total_seconds() / 60,
                1
            )
        }

    def get_hints(self, session_id: str) -> List[str]:
        """Получает подсказки для текущего вопроса"""
        current_question = self.get_current_question(session_id)
        if current_question and current_question.hints:
            return current_question.hints

        # Генерируем подсказки на лету, если их нет
        if current_question:
            prompt = f"""
            Вопрос: {current_question.question}

            Дай 2 подсказки для этого вопроса, которые помогут кандидату, если он затрудняется.

            Формат: ["подсказка 1", "подсказка 2"]
            """

            try:
                response = self.llm.chat(prompt)
                text = response.choices[0].message.content

                # Извлекаем список из текста
                import re
                list_match = re.search(r'\[.*\]', text, re.DOTALL)
                if list_match:
                    hints = json.loads(list_match.group())
                    current_question.hints = hints[:2]
                    return hints[:2]
            except:
                pass

        return ["Подумайте об основных концепциях темы", "Приведите конкретный пример"]

    def end_interview(self, session_id: str) -> Dict:
        """Завершает интервью и возвращает финальные результаты"""
        summary = self.get_interview_summary(session_id)

        # Генерируем рекомендации
        if "weak_points" in summary and summary["weak_points"]:
            prompt = f"""
            На основе слабых сторон кандидата: {', '.join(summary['weak_points'])}
            Сгенерируй 3 конкретные рекомендации для улучшения.

            Формат: ["рекомендация 1", "рекомендация 2", "рекомендация 3"]
            """

            try:
                response = self.llm.chat(prompt)
                text = response.choices[0].message.content

                import re
                list_match = re.search(r'\[.*\]', text, re.DOTALL)
                if list_match:
                    summary["recommendations"] = json.loads(list_match.group())
            except:
                summary["recommendations"] = [
                    "Практиковаться на LeetCode",
                    "Изучать документацию по теме",
                    "Проходить mock интервью"
                ]

        # Удаляем сессию
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]

        return summary