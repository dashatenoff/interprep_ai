from gigachat import GigaChat
from pydantic import BaseModel
from dotenv import load_dotenv
import os, json

load_dotenv()


class InterviewQuestion(BaseModel):
    topic: str
    question: str
    expected_concepts: list
    difficulty: str


class InterviewScore(BaseModel):
    score: int
    comment: str


class InterviewerAgent:
    def __init__(self):
        self.llm = GigaChat(credentials=os.getenv("GIGACHAT_CLIENT_SECRET"), verify_ssl_certs=False)

        # === Промпт для генерации вопросов ===
        self.q_prompt = """
        Ты — опытный технический интервьюер.
        Твоя задача — составить ровно 3 вопроса по теме {topic} для собеседования уровня junior/middle.

        Важно:
        - Всегда давай РОВНО 3 вопроса (не меньше и не больше)
        - Каждый вопрос должен быть коротким и конкретным
        - Ответь строго в JSON формате (без лишнего текста или комментариев)

        Пример правильного формата:
        {{
          "questions": [
            {{"topic": "{topic}", "question": "Что такое GIL в Python?", "expected_concepts": ["GIL", "многопоточность"], "difficulty": "medium"}},
            {{"topic": "{topic}", "question": "Объясните разницу между списком и кортежем.", "expected_concepts": ["list", "tuple"], "difficulty": "easy"}},
            {{"topic": "{topic}", "question": "Что делает оператор with?", "expected_concepts": ["context manager"], "difficulty": "easy"}}
          ]
        }}

        Теперь сформируй новые 3 вопроса по теме {topic}.
        Ответ — строго JSON, без пояснений.
        """

        # === Промпт для оценки ответов ===
        self.s_prompt = """
        Ты — технический интервьюер.
        Оцени ответ кандидата: "{answer}"

        Выдай результат строго в формате JSON:
        {{
          "score": число от 0 до 100,
          "comment": "краткий комментарий (одно предложение)"
        }}

        Пример:
        {{
          "score": 85,
          "comment": "Хорошо объяснил GIL, но не упомянул влияние на многопоточность."
        }}
        """

    def _extract_json(self, text: str) -> dict:
        """Безопасно достаёт JSON из ответа GigaChat"""
        if text.startswith("```"):
            text = text.strip("`")
            if "json" in text[:10].lower():
                text = text[text.find("{"):]
        json_start = text.find("{")
        json_end = text.rfind("}") + 1
        cleaned = text[json_start:json_end]
        return json.loads(cleaned)

    def generate_questions(self, topic: str) -> list[InterviewQuestion]:
        """Генерирует 3 вопроса по теме"""
        response = self.llm.chat(self.q_prompt.format(topic=topic))
        try:
            text = response.choices[0].message.content
            data = self._extract_json(text)
            return [InterviewQuestion(**q) for q in data["questions"]]
        except Exception as e:
            print("Ошибка парсинга вопросов:", e)
            print("Ответ модели:", response)
            return [
                InterviewQuestion(
                    topic=topic,
                    question="Расскажите, что такое GIL в Python.",
                    expected_concepts=["многопоточность", "интерпретатор CPython"],
                    difficulty="medium",
                )
            ]

    def evaluate_answer(self, answer: str) -> InterviewScore:
        """Оценивает ответ пользователя"""
        response = self.llm.chat(self.s_prompt.format(answer=answer))
        try:
            text = response.choices[0].message.content
            data = self._extract_json(text)
            return InterviewScore(**data)
        except Exception as e:
            print("Ошибка парсинга оценки:", e)
            print("Ответ модели:", response)
            return InterviewScore(score=60, comment="Ответ принят, но можно добавить конкретики.")
