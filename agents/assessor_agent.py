# agents/assessor.py
import json
from pydantic import BaseModel
from gigachat import GigaChat
import os
from dotenv import load_dotenv

# Загружаем токен из .env
load_dotenv()

# ===============================
#  Модель данных для результата
# ===============================
class AssessResult(BaseModel):
    scores: dict
    weak_topics: list
    follow_up: str

# ===============================
#  Основной класс агента
# ===============================
class AssessorAgent:
    def __init__(self):
        # ✅ Правильная инициализация клиента
        self.llm = GigaChat(
            credentials=os.getenv("GIGACHAT_CLIENT_SECRET"),
            verify_ssl_certs=False  # можно убрать, если не нужно
        )

        # Промпт (инструкция модели)
        self.prompt_template = """
        Ты — Assessor AI. Твоя задача — оценить знания пользователя по темам {topics}.
        Ответь строго в JSON формате:
        {{
          "scores": {{"Python": int, "Algorithms": int}},
          "weak_topics": [список слабых тем],
          "follow_up": "вопрос для уточнения"
        }}

        Пример:
        {{
          "scores": {{"Python": 70, "Algorithms": 40}},
          "weak_topics": ["recursion", "time complexity"],
          "follow_up": "Explain what recursion depth means in Python"
        }}

        Ответ пользователя:
        {answer}
        """

    def assess(self, answer: str, topics: list) -> AssessResult:
        """Отправляет ответ пользователя в GigaChat и возвращает JSON"""
        text = self.prompt_template.format(answer=answer, topics=topics)

        # ✅ Правильный вызов для клиента GigaChat
        response = self.llm.chat(
            model="GigaChat:latest",
            messages=[{"role": "user", "content": text}],
        )

        try:
            content = response.choices[0].message.content
            data = json.loads(content)
            return AssessResult(**data)
        except Exception as e:
            print("Ошибка парсинга:", e)
            print("Ответ модели:", response)
            return AssessResult(
                scores={"Python": 50, "Algorithms": 50},
                weak_topics=["unknown"],
                follow_up="Можешь уточнить свой опыт подробнее?"
            )
